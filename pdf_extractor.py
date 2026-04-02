"""
Code-based field extractor for machine-generated PDFs.

Uses PyMuPDF to get clean text, then regex patterns to extract invoice fields.
Returns an ExtractionResult with a confidence score (0.0–1.0).

Only called for .pdf files; images always fall through to Claude.
Confidence threshold for skipping Claude: 0.85
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

@dataclass
class ExtractedLine:
    name: str
    quantity: float = 1.0
    unit_price: float = 0.0    # bez DPH
    vat_rate: float = 21.0
    unit_name: Optional[str] = None


@dataclass
class ExtractionResult:
    is_machine_pdf: bool          # False → caller should skip this path
    confidence: float             # 0.0–1.0
    document_type: str = "faktura"
    doc_number: Optional[str] = None
    supplier_name: Optional[str] = None
    registration_no: Optional[str] = None
    vat_no: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    supplier_country: str = "CZ"
    issued_on: Optional[str] = None
    taxable_fulfillment_due: Optional[str] = None
    due_on: Optional[str] = None
    variable_symbol: Optional[str] = None
    payment_method: str = "bank"
    currency: str = "CZK"
    amount_without_vat: Optional[float] = None
    amount_vat: Optional[float] = None
    amount_total: Optional[float] = None
    vat_rate: float = 21.0
    lines: list = field(default_factory=list)   # list[ExtractedLine]


# ---------------------------------------------------------------------------
# IČO validation (Czech mod-11 checksum)
# ---------------------------------------------------------------------------

def _valid_ico(ico: str) -> bool:
    if not re.fullmatch(r"\d{8}", ico):
        return False
    a = sum(int(ico[i]) * (8 - i) for i in range(7))
    return int(ico[7]) == (11 - a % 11) % 10


# ---------------------------------------------------------------------------
# Amount parsing  (handles CZ "1 234,56", EU "1.234,56", plain "1234.56")
# ---------------------------------------------------------------------------

def _parse_amount(s: str) -> Optional[float]:
    s = re.sub(r"[\s\xa0]", "", s)   # strip spaces & nbsp
    try:
        if "," in s and "." in s:
            if s.rindex(",") > s.rindex("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Date normalisation  (DD.MM.YYYY | D.M.YYYY | YYYY-MM-DD) → YYYY-MM-DD
# ---------------------------------------------------------------------------

_DATE_DMY = re.compile(r"\b(\d{1,2})[.\-\s]+(\d{1,2})[.\-\s]+(\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _parse_date(text: str, hint: str = "") -> Optional[str]:
    """Return first date found near `hint` keyword, or first date in text."""
    search_area = text
    if hint:
        idx = text.lower().find(hint.lower())
        if idx >= 0:
            search_area = text[idx: idx + 60]

    m = _DATE_ISO.search(search_area) or _DATE_DMY.search(search_area)
    if not m:
        # Fall back to whole text
        m = _DATE_ISO.search(text) or _DATE_DMY.search(text)
    if not m:
        return None

    groups = m.groups()
    if len(groups[0]) == 4:   # ISO: YYYY-MM-DD
        return f"{groups[0]}-{int(groups[1]):02d}-{int(groups[2]):02d}"
    # DMY
    return f"{groups[2]}-{int(groups[1]):02d}-{int(groups[0]):02d}"


# ---------------------------------------------------------------------------
# Text extraction via PyMuPDF
# ---------------------------------------------------------------------------

_MIN_MACHINE_CHARS = 100


def _pdf_text(file_path: str) -> tuple[str, bool]:
    """Return (text, is_machine_pdf)."""
    import fitz
    doc = fitz.open(file_path)
    pages = [page.get_text() for page in doc]
    text = "\n\n".join(pages)
    return text, len(text.strip()) >= _MIN_MACHINE_CHARS


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_ico(text: str) -> Optional[str]:
    # Labelled IČO first
    for pat in [
        r"(?:IČO|IČ|IC)[:\s#]*(\d{8})\b",
        r"\b(\d{8})\b",                     # bare 8-digit fallback (validated)
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            candidate = m.group(1)
            if _valid_ico(candidate):
                return candidate
    return None


def _extract_vat_no(text: str) -> Optional[str]:
    m = re.search(r"(?:DIČ|DIC|VAT(?:\s*ID)?|UID)[:\s]*([A-Z]{2}\d{6,12})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_doc_number(text: str) -> Optional[str]:
    for pat in [
        r"(?:faktura\s*č\.?|číslo\s*dokladu|invoice\s*no\.?|č\.\s*dokladu)[:\s]*([A-Z0-9/_\-]{3,25})",
        r"(?:VS|variabilní\s*symbol)[:\s]*(\d{4,15})",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_variable_symbol(text: str) -> Optional[str]:
    m = re.search(
        r"(?:variabilní\s*symbol|var\.?\s*sym\.?|VS)[:\s]*(\d{4,15})",
        text, re.IGNORECASE
    )
    return m.group(1) if m else None


def _extract_currency(text: str) -> str:
    for cur in ("EUR", "USD", "GBP", "CHF", "PLN", "HUF"):
        if re.search(rf"\b{cur}\b", text):
            return cur
    return "CZK"


def _extract_amounts(text: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (without_vat, vat_amount, total)."""
    without_vat = vat_amount = total = None

    # Total / k úhradě
    for pat in [
        r"(?:celkem\s*k\s*úhradě|k\s*úhradě|celková\s*cena|total)[:\s]*([\d\s.,]+)",
        r"(?:payable\s*amount|amount\s*due)[:\s]*([\d\s.,]+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            total = _parse_amount(m.group(1))
            break

    # Základ DPH (without VAT)
    for pat in [
        r"(?:základ\s*daně|základ\s*DPH|tax(?:able)?\s*base)[:\s]*([\d\s.,]+)",
        r"(?:bez\s*DPH|without\s*VAT)[:\s]*([\d\s.,]+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            without_vat = _parse_amount(m.group(1))
            break

    # DPH částka
    for pat in [
        r"(?:DPH\s*(?:celkem)?|VAT\s*amount)[:\s]*([\d\s.,]+)",
        r"(?:daň\s*celkem)[:\s]*([\d\s.,]+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            vat_amount = _parse_amount(m.group(1))
            break

    # Derive missing values
    if total and without_vat and vat_amount is None:
        vat_amount = round(total - without_vat, 2)
    if total and vat_amount and without_vat is None:
        without_vat = round(total - vat_amount, 2)
    if without_vat and vat_amount and total is None:
        total = round(without_vat + vat_amount, 2)

    return without_vat, vat_amount, total


def _extract_vat_rate(text: str) -> float:
    m = re.search(r"\b(21|12|15|10|0)\s*%", text)
    if m:
        return float(m.group(1))
    return 21.0


def _extract_payment_method(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ("karta", "card", "platba kartou")):
        return "card"
    if any(w in text_lower for w in ("hotovost", "cash", "v hotovosti")):
        return "cash"
    if any(w in text_lower for w in ("dobírka", "cod")):
        return "cod"
    return "bank"


def _extract_document_type(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ("vrubopis", "debit note", "debit memo")):
        return "vrubopis"
    if any(w in text_lower for w in ("dobropis", "opravný daňový doklad", "credit note", "credit memo")):
        return "dobropis"
    if any(w in text_lower for w in ("paragon", "účtenka", "pokladní doklad")):
        return "uctenka"
    if any(w in text_lower for w in ("zálohová faktura", "zálohový daňový doklad",
                                      "proforma", "pro forma", "záloha č", "záloha na")):
        return "zaloha"
    return "faktura"


def _extract_supplier_block(text: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Return (name, street, city, zip, country)."""
    name = street = city = zip_code = None
    country = "CZ"

    # Supplier section heuristic: look for block before IČO
    ico_m = re.search(r"(?:IČO|IČ)[:\s]*\d{8}", text, re.IGNORECASE)
    if ico_m:
        block = text[max(0, ico_m.start() - 300): ico_m.start()]
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if lines:
            name = lines[-1] if len(lines) >= 1 else None

    # ZIP + city
    m = re.search(r"\b(\d{3}\s?\d{2})\s+([A-ZÁ-Ža-zá-ž][^\n,]{2,30})", text)
    if m:
        zip_code = re.sub(r"\s", "", m.group(1))
        city = m.group(2).strip()

    # Street (heuristic: line with street number pattern)
    m = re.search(r"([A-ZÁ-Ža-zá-ž][^\n,]{3,40}\s+\d+[a-z]?)\s*[,\n]", text)
    if m:
        street = m.group(1).strip()

    # Country from VAT prefix or explicit mention
    vat_m = re.search(r"(?:DIČ|VAT)[:\s]*([A-Z]{2})\d", text, re.IGNORECASE)
    if vat_m:
        country = vat_m.group(1).upper()
    elif re.search(r"\b(Deutschland|Germany|Polska|Slovakia|Österreich)\b", text, re.IGNORECASE):
        country = "DE"   # rough; Claude handles the rest

    return name, street, city, zip_code, country


# ---------------------------------------------------------------------------
# Line item extraction
# ---------------------------------------------------------------------------

_SKIP_ROW_RE = re.compile(
    r"^\s*(?:celkem|základ|zákadem|DPH\s+celkem|k\s+úhradě|total|součet|suma|mezisoučet"
    r"|subtotal|tax|vat|invoice\s+total|amount\s+due)\b",
    re.IGNORECASE,
)
_HEADER_WORDS = {
    "popis", "název", "položka", "text", "description",
    "množství", "qty", "quantity", "počet",
    "cena", "price", "amount", "částka",
    "dph", "vat", "tax", "sazba",
}


def _is_header_row(row: list) -> bool:
    text = " ".join(str(c or "").lower() for c in row)
    return sum(1 for w in _HEADER_WORDS if w in text) >= 2


def _is_skip_row(row: list) -> bool:
    first = str(row[0] or "").strip() if row else ""
    return bool(_SKIP_ROW_RE.match(first))


def _parse_table_rows(rows: list, vat_rate_default: float, currency: str,
                      is_dobropis: bool) -> list:
    """Convert raw table rows (list of list) into ExtractedLine items."""
    items = []
    for row in rows:
        if not row:
            continue
        cells = [str(c).strip() if c is not None else "" for c in row]
        if all(c == "" for c in cells):
            continue
        if _is_header_row(row) or _is_skip_row(row):
            continue

        # Find description: first cell that is NOT a pure number
        desc = None
        numeric_vals: list[float] = []
        for cell in cells:
            if not cell:
                continue
            val = _parse_amount(cell)
            if val is not None:
                numeric_vals.append(val)
            elif desc is None and len(cell) > 1:
                desc = cell[:100]

        if not desc or not numeric_vals:
            continue

        # Detect VAT rate column: value is 0, 12, 15, 21 (typical rates)
        vat_rate = vat_rate_default
        rate_candidates = [v for v in numeric_vals if v in (0, 5, 10, 12, 15, 21, 25)]
        if rate_candidates:
            vat_rate = float(rate_candidates[0])
            numeric_vals = [v for v in numeric_vals if v not in rate_candidates]

        if not numeric_vals:
            continue

        # Detect quantity: small positive integer ≤ 1000 that appears before prices
        # Heuristic: if ≥ 2 amounts left, first might be quantity
        quantity = 1.0
        if len(numeric_vals) >= 2 and 0 < numeric_vals[0] <= 1000 and numeric_vals[0] == int(numeric_vals[0]):
            quantity = numeric_vals[0]
            numeric_vals = numeric_vals[1:]

        # unit_price = smallest remaining amount (per-unit price < total)
        # or the first one if only one left
        if not numeric_vals:
            continue
        unit_price = min(numeric_vals, key=abs) if len(numeric_vals) > 1 else numeric_vals[0]

        if is_dobropis and unit_price > 0:
            unit_price = -unit_price

        if unit_price == 0.0:
            continue

        items.append(ExtractedLine(
            name=desc,
            quantity=quantity,
            unit_price=round(unit_price, 4),
            vat_rate=vat_rate,
        ))

    return items


def _extract_lines(file_path: str, vat_rate: float, currency: str,
                   is_dobropis: bool) -> list:
    """
    Extract invoice line items from a PDF using PyMuPDF table detection.
    Falls back to empty list if tables not found or fitz version too old.
    """
    try:
        import fitz
        doc = fitz.open(file_path)
        for page in doc:
            try:
                finder = page.find_tables()
            except AttributeError:
                return []   # fitz < 1.23 — no table support
            for table in finder.tables:
                rows = table.extract()
                items = _parse_table_rows(rows, vat_rate, currency, is_dobropis)
                if items:
                    return items
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score(result: ExtractionResult) -> float:
    score = 0.0
    if result.registration_no:   score += 0.30   # IČO validated
    if result.supplier_name:     score += 0.20
    if result.amount_total:      score += 0.25
    if result.issued_on:         score += 0.15
    if result.doc_number:        score += 0.10
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def try_extract(file_path: str) -> Optional[ExtractionResult]:
    """
    Attempt code-based extraction from a machine PDF.
    Returns None if the file is not a PDF or is a scan.
    Returns ExtractionResult (check .confidence before using).
    """
    if Path(file_path).suffix.lower() != ".pdf":
        return None

    text, is_machine = _pdf_text(file_path)
    if not is_machine:
        return ExtractionResult(is_machine_pdf=False, confidence=0.0)

    ico  = _extract_ico(text)
    vno  = _extract_vat_no(text)
    name, street, city, zip_code, country = _extract_supplier_block(text)

    without_vat, vat_amount, total = _extract_amounts(text)
    vat_rate = _extract_vat_rate(text)

    # Reverse charge: foreign supplier
    reverse = country != "CZ"
    if reverse:
        vat_rate = 21.0

    doc_type = _extract_document_type(text)
    is_dobropis = doc_type == "dobropis"
    currency = _extract_currency(text)

    result = ExtractionResult(
        is_machine_pdf=True,
        confidence=0.0,
        document_type=doc_type,
        doc_number=_extract_doc_number(text),
        supplier_name=name,
        registration_no=ico,
        vat_no=vno,
        street=street,
        city=city,
        zip_code=zip_code,
        supplier_country=country,
        issued_on=_parse_date(text, "vystavení") or _parse_date(text, "vydáno") or _parse_date(text),
        taxable_fulfillment_due=_parse_date(text, "DUZP") or _parse_date(text, "plnění"),
        due_on=_parse_date(text, "splatnost"),
        variable_symbol=_extract_variable_symbol(text),
        payment_method=_extract_payment_method(text),
        currency=currency,
        amount_without_vat=without_vat,
        amount_vat=vat_amount,
        amount_total=total,
        vat_rate=vat_rate,
        lines=_extract_lines(file_path, vat_rate, currency, is_dobropis),
    )

    # DUZP fallback
    if not result.taxable_fulfillment_due:
        result.taxable_fulfillment_due = result.issued_on

    result.confidence = _score(result)
    return result
