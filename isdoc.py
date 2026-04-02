"""
ISDOC 6.0.2 intermediate layer.

Pipeline:
  OCR text → LLM (Claude nebo OpenAI) → ISDOC XML → ExtractedDocument

Provider se volí přes env proměnnou LLM_PROVIDER (claude / openai).
The ISDOC XML is persisted to output/{item_id}.xml so it can be
reused or exported independently of this application.

Namespace: http://isdoc.cz/namespace/2013
Spec:       https://mv.gov.cz/isdoc/clanek/aktualni-verze.aspx
"""
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as _safe_fromstring
from pathlib import Path
from typing import Optional

from config import ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_MODEL, LLM_PROVIDER
from models import DocumentType, ExtractedDocument, LineItem, PaymentMethod

_OUTPUT_DIR = Path("output")
_NS = "http://isdoc.cz/namespace/2013"
_NSP = f"{{{_NS}}}"   # Clark-notation prefix for ElementTree lookups

# Lazy clients
_anthropic_client = None
_openai_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ---------------------------------------------------------------------------
# DocumentType mapping  (ISDOC → our model)
# ---------------------------------------------------------------------------
_ISDOC_DOCTYPE: dict[str, DocumentType] = {
    "1": DocumentType.faktura,   # Daňový doklad
    "2": DocumentType.zaloha,    # Zálohový daňový doklad
    "3": DocumentType.dobropis,  # Opravný daňový doklad (dobropis/vrubopis)
    "4": DocumentType.faktura,   # Souhrnný daňový doklad
    "5": DocumentType.uctenka,   # Zjednodušený daňový doklad (paragon)
    "6": DocumentType.faktura,   # Doklad o zaplacení DPH při dovozu
}

# PaymentMeansCode mapping  (ISDOC → our model)
_ISDOC_PAYMENT: dict[str, PaymentMethod] = {
    "10": PaymentMethod.cash,
    "42": PaymentMethod.bank,
    "48": PaymentMethod.card,
    "97": PaymentMethod.cod,
}

# ---------------------------------------------------------------------------
# Claude prompt for ISDOC extraction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Jsi expert na zpracování českých a zahraničních účetních dokladů.
Z OCR textu extrahuj data a vrať POUZE validní ISDOC 6.0.2 XML (bez markdown, bez komentářů, bez nic navíc).
Začni přímo <?xml ... a nesmaž žádný povinný element.

Pravidla:
- DocumentType: 1=faktura, 2=zálohová faktura (s DPH), 3=opravný daňový doklad (dobropis/vrubopis), 5=paragon/účtenka (max 10 000 Kč)
- ID: číslo dokladu DODAVATELE (nikoli naše interní číslo)
- IssueDate: datum vystavení (YYYY-MM-DD)
- TaxPointDate: DUZP – datum zdanitelného plnění; pokud není, použij IssueDate
- DueDate: datum splatnosti (YYYY-MM-DD); pokud není, vynech element
- LocalCurrencyCode: vždy CZK
- CurrencyCode: měna dokladu (CZK, EUR, USD…); pokud jen CZK, neuvádět
- ExchangeRate: kurz pokud je uvedený; jinak vynechat
- AccountingSupplierParty/Party/PartyIdentification/ID: IČO dodavatele
- AccountingSupplierParty/Party/PartyTaxScheme/CompanyID: DIČ (s prefixem země, např. CZ12345678)
- AccountingSupplierParty/Party/PostalAddress/Country/IdentificationCode: ISO-2 (CZ, DE, US…)
- PaymentMeans/Payment/PaymentMeansCode: 10=hotovost, 42=bankovní převod, 48=karta, 97=dobírka
- PaymentMeans/Payment/VariableSymbol: variabilní symbol, pokud uveden
- InvoiceLine: každá řádková položka; LineExtensionAmount = cena bez DPH v měně dokladu
- ClassifiedTaxCategory/Percent: sazba DPH (0, 12 nebo 21); pro zahraniční samovyměření také 21
- Dobropis (DocumentType=3, snížení): LineExtensionAmount musí být záporné číslo
- Vrubopis (DocumentType=3, zvýšení): LineExtensionAmount musí být kladné číslo
- Pokud hodnota chybí a element není povinný, element vynech (nepiš prázdné tagy)
"""

_ISDOC_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>1</DocumentType>
  <ID></ID>
  <IssueDate></IssueDate>
  <TaxPointDate></TaxPointDate>
  <DueDate></DueDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <CurrencyCode>CZK</CurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PartyIdentification><ID></ID></PartyIdentification>
      <PartyTaxScheme>
        <CompanyID></CompanyID>
        <TaxScheme>VAT</TaxScheme>
      </PartyTaxScheme>
      <PartyName><Name></Name></PartyName>
      <PostalAddress>
        <StreetName></StreetName>
        <CityName></CityName>
        <PostalZone></PostalZone>
        <Country><IdentificationCode>CZ</IdentificationCode></Country>
      </PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans>
    <Payment>
      <PaymentMeansCode>42</PaymentMeansCode>
      <VariableSymbol></VariableSymbol>
    </Payment>
  </PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="CZK">0.00</TaxableAmount>
      <TaxAmount currencyID="CZK">0.00</TaxAmount>
      <TaxCategory>
        <Percent>21</Percent>
        <TaxScheme>VAT</TaxScheme>
      </TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="CZK">0.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="CZK">0.00</TaxInclusiveAmount>
    <PayableAmount currencyID="CZK">0.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">0.00</LineExtensionAmount>
    <Item><Description></Description></Item>
    <Price><PriceAmount currencyID="CZK">0.00</PriceAmount></Price>
    <ClassifiedTaxCategory>
      <Percent>21</Percent>
      <TaxScheme>VAT</TaxScheme>
    </ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


# ---------------------------------------------------------------------------
# Step 1: OCR text → ISDOC XML  (via LLM)
# ---------------------------------------------------------------------------

def _strip_markdown(raw: str) -> str:
    """Odstraní případné markdown fences z odpovědi LLM."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.lower().startswith("xml"):
            raw = raw[3:]
    return raw.strip()


def _extract_to_isdoc_claude(ocr_text: str) -> str:
    """Volá Claude Sonnet a vrátí ISDOC 6.0.2 XML string."""
    user_msg = (
        "Zpracuj tento OCR text a vyplň ISDOC šablonu:\n\n"
        f"ŠABLONA:\n{_ISDOC_TEMPLATE}\n\n"
        f"OCR TEXT:\n{ocr_text}"
    )
    response = _get_anthropic().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return _strip_markdown(response.content[0].text.strip())


def _extract_to_isdoc_openai(ocr_text: str) -> str:
    """Volá OpenAI a vrátí ISDOC 6.0.2 XML string."""
    user_msg = (
        "Zpracuj tento OCR text a vyplň ISDOC šablonu:\n\n"
        f"ŠABLONA:\n{_ISDOC_TEMPLATE}\n\n"
        f"OCR TEXT:\n{ocr_text}"
    )
    response = _get_openai().chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    return _strip_markdown(response.choices[0].message.content.strip())


def extract_to_isdoc(ocr_text: str, provider: str | None = None) -> str:
    """
    Převede OCR text na ISDOC 6.0.2 XML pomocí zvoleného LLM.
    provider: "claude" | "openai" | None  → použije LLM_PROVIDER z env
    Raises on API failure.
    """
    p = (provider or LLM_PROVIDER).lower()
    if p == "openai":
        return _extract_to_isdoc_openai(ocr_text)
    return _extract_to_isdoc_claude(ocr_text)


# ---------------------------------------------------------------------------
# Step 2: ISDOC XML → ExtractedDocument
# ---------------------------------------------------------------------------

def _txt(el: Optional[ET.Element]) -> Optional[str]:
    """Return stripped text of element, or None if element is None or empty."""
    if el is None:
        return None
    t = (el.text or "").strip()
    return t if t else None


def _float(el: Optional[ET.Element]) -> Optional[float]:
    t = _txt(el)
    if t is None:
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def isdoc_to_extracted(xml: str) -> ExtractedDocument:
    """Parse ISDOC 6.0.2 XML string into ExtractedDocument."""
    try:
        root = _safe_fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"Neplatné ISDOC XML: {exc}") from exc

    def find(path: str) -> Optional[ET.Element]:
        ns_path = "/".join(f"{_NSP}{p}" for p in path.split("/"))
        el = root.find(ns_path)
        if el is None:
            el = root.find(path)
        return el

    def findall(path: str) -> list:
        ns_path = "/".join(f"{_NSP}{p}" for p in path.split("/"))
        els = root.findall(ns_path)
        if not els:
            els = root.findall(path)
        return els

    # Document type
    doc_type_code = _txt(find("DocumentType")) or "1"
    document_type = _ISDOC_DOCTYPE.get(doc_type_code, DocumentType.unknown)

    # Supplier
    supplier_name    = _txt(find("AccountingSupplierParty/Party/PartyName/Name"))
    registration_no  = _txt(find("AccountingSupplierParty/Party/PartyIdentification/ID"))
    vat_no           = _txt(find("AccountingSupplierParty/Party/PartyTaxScheme/CompanyID"))
    street           = _txt(find("AccountingSupplierParty/Party/PostalAddress/StreetName"))
    city             = _txt(find("AccountingSupplierParty/Party/PostalAddress/CityName"))
    zip_code         = _txt(find("AccountingSupplierParty/Party/PostalAddress/PostalZone"))
    country_el       = find("AccountingSupplierParty/Party/PostalAddress/Country/IdentificationCode")
    supplier_country = (_txt(country_el) or "CZ").upper()

    # Dates
    issued_on  = _txt(find("IssueDate"))
    tax_point  = _txt(find("TaxPointDate")) or issued_on
    due_on     = _txt(find("DueDate"))

    # Currency & exchange rate
    currency      = (_txt(find("CurrencyCode")) or "CZK").upper()
    exchange_rate = _float(find("ExchangeRate"))

    # Payment
    pm_code         = _txt(find("PaymentMeans/Payment/PaymentMeansCode")) or "42"
    payment_method  = _ISDOC_PAYMENT.get(pm_code, PaymentMethod.bank)
    variable_symbol = _txt(find("PaymentMeans/Payment/VariableSymbol"))

    # Reverse charge: foreign supplier always triggers it
    reverse_charge = supplier_country != "CZ"

    # Line items
    lines: list[LineItem] = []
    for line_el in findall("InvoiceLine"):
        def lf(path: str) -> Optional[ET.Element]:
            ns_path = "/".join(f"{_NSP}{p}" for p in path.split("/"))
            el = line_el.find(ns_path)
            if el is None:
                el = line_el.find(path)
            return el

        name       = _txt(lf("Item/Description")) or "Položka"
        quantity   = _float(lf("InvoicedQuantity")) or 1.0
        unit_price = _float(lf("LineExtensionAmount")) or 0.0
        vat_rate   = _float(lf("ClassifiedTaxCategory/Percent")) or (21.0 if reverse_charge else 0.0)
        unit_name  = _txt(lf("Item/SellersItemIdentification/ID"))

        # Dobropis: ensure negative prices
        if document_type == DocumentType.dobropis and unit_price > 0:
            unit_price = -unit_price

        # Reverse charge: force 21 % VAT
        if reverse_charge:
            vat_rate = 21.0

        lines.append(LineItem(
            name=name,
            quantity=quantity,
            unit_price=unit_price,
            vat_rate=vat_rate,
            unit_name=unit_name,
        ))

    amount_total = _float(find("LegalMonetaryTotal/PayableAmount"))

    return ExtractedDocument(
        document_type=document_type,
        confidence=0.85,
        amount_total=amount_total,
        supplier_name=supplier_name,
        registration_no=registration_no,
        vat_no=vat_no,
        street=street,
        city=city,
        zip=zip_code,
        supplier_country=supplier_country,
        original_number=_txt(find("ID")),
        issued_on=issued_on,
        taxable_fulfillment_due=tax_point or issued_on,
        due_on=due_on,
        variable_symbol=variable_symbol,
        payment_method=payment_method,
        currency=currency,
        exchange_rate=exchange_rate,
        reverse_charge=reverse_charge,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_isdoc(name: str, xml: str) -> Path:
    """Persist the ISDOC XML. Returns the saved file path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / f"{name}.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def load_isdoc(name: str) -> Optional[str]:
    """Return persisted ISDOC XML, or None if not found."""
    path = _OUTPUT_DIR / f"{name}.xml"
    return path.read_text(encoding="utf-8") if path.exists() else None


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def extract_document(ocr_text: str, save_as: Optional[str] = None,
                     provider: str | None = None) -> ExtractedDocument:
    """
    Full ISDOC pipeline:
      1. LLM (Claude nebo OpenAI) převede OCR text → ISDOC XML
      2. XML se uloží do output/ (pokud je zadáno save_as)
      3. XML se naparsuje → ExtractedDocument
    Raises ValueError if LLM returns unparseable XML.
    """
    xml = extract_to_isdoc(ocr_text, provider=provider)
    if save_as:
        save_isdoc(save_as, xml)
    return isdoc_to_extracted(xml)
