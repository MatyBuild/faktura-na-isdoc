"""
Builds ISDOC 6.0.2 XML from an ExtractionResult without calling Claude.

Produces the same XML structure that isdoc.py expects from Claude,
so isdoc_to_extracted() works identically on both paths.
"""
import xml.etree.ElementTree as ET
from typing import Optional

from pdf_extractor import ExtractionResult

_NS = "http://isdoc.cz/namespace/2013"

# DocumentType code mapping  (ISDOC 6.0.2 spec)
_DOCTYPE_CODE = {
    "faktura":  "1",
    "zaloha":   "2",   # Zálohový daňový doklad
    "dobropis": "3",   # Opravný daňový doklad (snížení)
    "vrubopis": "3",   # Opravný daňový doklad (zvýšení) – stejný kód, jiné znaménko
    "uctenka":  "5",   # Zjednodušený daňový doklad
    "unknown":  "1",
}

# PaymentMeansCode mapping
_PM_CODE = {
    "bank":  "42",
    "cash":  "10",
    "card":  "48",
    "cod":   "97",
    "other": "42",
}


def _el(parent: ET.Element, tag: str, text: Optional[str] = None,
        **attrs) -> ET.Element:
    el = ET.SubElement(parent, f"{{{_NS}}}{tag}", **attrs)
    if text is not None:
        el.text = str(text)
    return el


def _fmt_rate(rate: float) -> str:
    """Format VAT rate as integer string when possible (21.0 → '21')."""
    return str(int(rate)) if rate == int(rate) else str(rate)


def build_isdoc(r: ExtractionResult) -> str:
    """Return ISDOC 6.0.2 XML string built from ExtractionResult."""
    ET.register_namespace("", _NS)
    root = ET.Element(f"{{{_NS}}}Invoice", version="6.0.2")

    _el(root, "DocumentType", _DOCTYPE_CODE.get(r.document_type, "1"))
    if r.doc_number:
        _el(root, "ID", r.doc_number)
    if r.issued_on:
        _el(root, "IssueDate", r.issued_on)
    if r.taxable_fulfillment_due:
        _el(root, "TaxPointDate", r.taxable_fulfillment_due)
    if r.due_on:
        _el(root, "DueDate", r.due_on)

    _el(root, "LocalCurrencyCode", "CZK")
    if r.currency and r.currency != "CZK":
        _el(root, "CurrencyCode", r.currency)

    # ── Supplier party ────────────────────────────────────────────────────
    asp   = _el(root, "AccountingSupplierParty")
    party = _el(asp, "Party")

    if r.registration_no:
        pid = _el(party, "PartyIdentification")
        _el(pid, "ID", r.registration_no)

    if r.vat_no:
        pts = _el(party, "PartyTaxScheme")
        _el(pts, "CompanyID", r.vat_no)
        _el(pts, "TaxScheme", "VAT")

    if r.supplier_name:
        pn = _el(party, "PartyName")
        _el(pn, "Name", r.supplier_name)

    addr = _el(party, "PostalAddress")
    if r.street:
        _el(addr, "StreetName", r.street)
    if r.city:
        _el(addr, "CityName", r.city)
    if r.zip_code:
        _el(addr, "PostalZone", r.zip_code)
    ctr = _el(addr, "Country")
    _el(ctr, "IdentificationCode", r.supplier_country or "CZ")

    # ── Payment means ─────────────────────────────────────────────────────
    pm  = _el(root, "PaymentMeans")
    pay = _el(pm, "Payment")
    _el(pay, "PaymentMeansCode", _PM_CODE.get(r.payment_method, "42"))
    if r.variable_symbol:
        _el(pay, "VariableSymbol", r.variable_symbol)

    # ── Tax total (one TaxSubTotal per unique VAT rate) ────────────────────
    cur         = r.currency or "CZK"
    is_dobropis = r.document_type == "dobropis"

    if r.lines:
        # Group by VAT rate to produce correct multi-rate TaxTotal
        vat_groups: dict[float, list] = {}
        for li in r.lines:
            vat_groups.setdefault(li.vat_rate, []).append(li)

        tt              = _el(root, "TaxTotal")
        calc_base_total = 0.0
        calc_vat_total  = 0.0

        for rate in sorted(vat_groups):
            group_lines = vat_groups[rate]
            group_base  = sum(round(li.unit_price * li.quantity, 2) for li in group_lines)
            if is_dobropis and group_base > 0:
                group_base = -group_base
            group_vat = round(group_base * rate / 100, 2)
            calc_base_total += group_base
            calc_vat_total  += group_vat

            tst = _el(tt, "TaxSubTotal")
            _el(tst, "TaxableAmount", f"{group_base:.2f}", currencyID=cur)
            _el(tst, "TaxAmount",     f"{group_vat:.2f}",  currencyID=cur)
            tc  = _el(tst, "TaxCategory")
            _el(tc, "Percent",   _fmt_rate(rate))
            _el(tc, "TaxScheme", "VAT")

        base  = round(calc_base_total, 2)
        vat_a = round(calc_vat_total,  2)
        total = r.amount_total or round(base + vat_a, 2)

    else:
        # Fallback: header totals, single rate
        base  = r.amount_without_vat or 0.0
        vat_a = r.amount_vat or 0.0
        total = r.amount_total or (base + vat_a)

        tt  = _el(root, "TaxTotal")
        tst = _el(tt, "TaxSubTotal")
        _el(tst, "TaxableAmount", f"{base:.2f}", currencyID=cur)
        _el(tst, "TaxAmount",     f"{vat_a:.2f}", currencyID=cur)
        tc  = _el(tst, "TaxCategory")
        _el(tc, "Percent",   _fmt_rate(r.vat_rate))
        _el(tc, "TaxScheme", "VAT")

    # ── Legal monetary total ──────────────────────────────────────────────
    lmt = _el(root, "LegalMonetaryTotal")
    _el(lmt, "TaxExclusiveAmount", f"{base:.2f}",  currencyID=cur)
    _el(lmt, "TaxInclusiveAmount", f"{total:.2f}", currencyID=cur)
    _el(lmt, "PayableAmount",      f"{total:.2f}", currencyID=cur)

    # ── Invoice lines ─────────────────────────────────────────────────────
    if r.lines:
        for idx, li in enumerate(r.lines, start=1):
            up = li.unit_price
            if is_dobropis and up > 0:
                up = -up
            ext  = round(up * li.quantity, 2)
            line = _el(root, "InvoiceLine")
            _el(line, "ID", str(idx))
            unit_code = "ZZ" if not li.unit_name else li.unit_name[:3].upper()
            _el(line, "InvoicedQuantity", str(li.quantity), unitCode=unit_code)
            _el(line, "LineExtensionAmount", f"{ext:.2f}", currencyID=cur)
            item_el = _el(line, "Item")
            _el(item_el, "Description", li.name)
            price_el = _el(line, "Price")
            _el(price_el, "PriceAmount", f"{up:.2f}", currencyID=cur)
            ctc = _el(line, "ClassifiedTaxCategory")
            _el(ctc, "Percent",   _fmt_rate(li.vat_rate))
            _el(ctc, "TaxScheme", "VAT")
    else:
        # Fallback: single aggregate line
        unit_price = base
        if is_dobropis and unit_price > 0:
            unit_price = -unit_price
        line = _el(root, "InvoiceLine")
        _el(line, "ID", "1")
        _el(line, "InvoicedQuantity", "1", unitCode="ZZ")
        _el(line, "LineExtensionAmount", f"{unit_price:.2f}", currencyID=cur)
        item_el = _el(line, "Item")
        _el(item_el, "Description", "Zboží / Služby")
        price_el = _el(line, "Price")
        _el(price_el, "PriceAmount", f"{unit_price:.2f}", currencyID=cur)
        ctc = _el(line, "ClassifiedTaxCategory")
        _el(ctc, "Percent",   _fmt_rate(r.vat_rate))
        _el(ctc, "TaxScheme", "VAT")

    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
