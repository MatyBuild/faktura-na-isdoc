"""Testy sestavování ISDOC XML z ExtractionResult."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import xml.etree.ElementTree as ET
import pytest
from pdf_extractor import ExtractionResult, ExtractedLine
from isdoc_builder import build_isdoc

_NS = "http://isdoc.cz/namespace/2013"
_P  = f"{{{_NS}}}"


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def _find(root: ET.Element, path: str) -> ET.Element | None:
    return root.find("/".join(f"{_P}{p}" for p in path.split("/")))


def _findall(root: ET.Element, path: str) -> list:
    return root.findall("/".join(f"{_P}{p}" for p in path.split("/")))


def _text(root: ET.Element, path: str) -> str | None:
    el = _find(root, path)
    return el.text.strip() if el is not None and el.text else None


# ---------------------------------------------------------------------------
# Základní faktura
# ---------------------------------------------------------------------------

def _basic_result(**kwargs) -> ExtractionResult:
    defaults = dict(
        is_machine_pdf=True, confidence=0.95,
        document_type="faktura",
        doc_number="FV2024001",
        supplier_name="Acme s.r.o.",
        registration_no="25596641",
        issued_on="2024-03-15",
        currency="CZK",
        amount_without_vat=1000.0,
        amount_vat=210.0,
        amount_total=1210.0,
        vat_rate=21.0,
    )
    defaults.update(kwargs)
    return ExtractionResult(**defaults)


class TestBasicFields:
    def test_document_type_faktura(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "DocumentType") == "1"

    def test_document_type_zaloha(self):
        root = _parse(build_isdoc(_basic_result(document_type="zaloha")))
        assert _text(root, "DocumentType") == "2"

    def test_document_type_dobropis(self):
        root = _parse(build_isdoc(_basic_result(document_type="dobropis")))
        assert _text(root, "DocumentType") == "3"

    def test_document_type_vrubopis(self):
        root = _parse(build_isdoc(_basic_result(document_type="vrubopis")))
        assert _text(root, "DocumentType") == "3"   # stejný ISDOC kód

    def test_document_type_uctenka(self):
        root = _parse(build_isdoc(_basic_result(document_type="uctenka")))
        assert _text(root, "DocumentType") == "5"

    def test_invoice_id(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "ID") == "FV2024001"

    def test_issue_date(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "IssueDate") == "2024-03-15"

    def test_local_currency(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "LocalCurrencyCode") == "CZK"

    def test_foreign_currency(self):
        root = _parse(build_isdoc(_basic_result(currency="EUR")))
        assert _text(root, "CurrencyCode") == "EUR"

    def test_no_currency_code_for_czk(self):
        root = _parse(build_isdoc(_basic_result(currency="CZK")))
        assert _find(root, "CurrencyCode") is None

    def test_supplier_name(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "AccountingSupplierParty/Party/PartyName/Name") == "Acme s.r.o."

    def test_supplier_ico(self):
        root = _parse(build_isdoc(_basic_result()))
        assert _text(root, "AccountingSupplierParty/Party/PartyIdentification/ID") == "25596641"


# ---------------------------------------------------------------------------
# Více sazeb DPH
# ---------------------------------------------------------------------------

class TestMultipleVatRates:
    def _result_with_lines(self, doc_type="faktura") -> ExtractionResult:
        return ExtractionResult(
            is_machine_pdf=True, confidence=0.95,
            document_type=doc_type,
            currency="CZK",
            vat_rate=21.0,
            lines=[
                ExtractedLine(name="Zboží 21%",  quantity=1.0, unit_price=1000.0, vat_rate=21.0),
                ExtractedLine(name="Potraviny",  quantity=2.0, unit_price=500.0,  vat_rate=12.0),
                ExtractedLine(name="Osvobozeno", quantity=1.0, unit_price=200.0,  vat_rate=0.0),
            ],
        )

    def test_three_tax_subtotals(self):
        root = _parse(build_isdoc(self._result_with_lines()))
        subtotals = _findall(root, "TaxTotal/TaxSubTotal")
        assert len(subtotals) == 3

    def test_vat_rates_in_subtotals(self):
        root = _parse(build_isdoc(self._result_with_lines()))
        rates = set()
        for st in _findall(root, "TaxTotal/TaxSubTotal"):
            pct = st.find(f"{_P}TaxCategory/{_P}Percent")
            if pct is not None:
                rates.add(pct.text)
        assert rates == {"0", "12", "21"}

    def test_21pct_tax_amount(self):
        root = _parse(build_isdoc(self._result_with_lines()))
        # 21% ze základu 1000 = 210
        for st in _findall(root, "TaxTotal/TaxSubTotal"):
            pct = st.find(f"{_P}TaxCategory/{_P}Percent")
            if pct is not None and pct.text == "21":
                taxable = st.find(f"{_P}TaxableAmount")
                tax_amt = st.find(f"{_P}TaxAmount")
                assert float(taxable.text) == 1000.0
                assert float(tax_amt.text) == 210.0

    def test_12pct_tax_amount(self):
        root = _parse(build_isdoc(self._result_with_lines()))
        # 12% ze základu 1000 (2×500) = 120
        for st in _findall(root, "TaxTotal/TaxSubTotal"):
            pct = st.find(f"{_P}TaxCategory/{_P}Percent")
            if pct is not None and pct.text == "12":
                taxable = st.find(f"{_P}TaxableAmount")
                tax_amt = st.find(f"{_P}TaxAmount")
                assert float(taxable.text) == 1000.0
                assert float(tax_amt.text) == 120.0

    def test_invoice_line_count(self):
        root = _parse(build_isdoc(self._result_with_lines()))
        lines = _findall(root, "InvoiceLine")
        assert len(lines) == 3

    def test_single_vat_rate_one_subtotal(self):
        r = ExtractionResult(
            is_machine_pdf=True, confidence=0.9,
            document_type="faktura", currency="CZK", vat_rate=21.0,
            lines=[
                ExtractedLine(name="A", quantity=1.0, unit_price=500.0, vat_rate=21.0),
                ExtractedLine(name="B", quantity=2.0, unit_price=250.0, vat_rate=21.0),
            ],
        )
        root = _parse(build_isdoc(r))
        assert len(_findall(root, "TaxTotal/TaxSubTotal")) == 1


# ---------------------------------------------------------------------------
# Dobropis – záporné částky
# ---------------------------------------------------------------------------

class TestDobropis:
    def _dobropis(self) -> ExtractionResult:
        return ExtractionResult(
            is_machine_pdf=True, confidence=0.9,
            document_type="dobropis", currency="CZK", vat_rate=21.0,
            lines=[
                ExtractedLine(name="Vrácené zboží", quantity=1.0, unit_price=500.0, vat_rate=21.0),
            ],
        )

    def test_line_extension_negative(self):
        root = _parse(build_isdoc(self._dobropis()))
        line = _findall(root, "InvoiceLine")[0]
        ext = line.find(f"{_P}LineExtensionAmount")
        assert float(ext.text) == -500.0

    def test_taxable_amount_negative(self):
        root = _parse(build_isdoc(self._dobropis()))
        taxable = _find(root, "TaxTotal/TaxSubTotal/TaxableAmount")
        assert float(taxable.text) == -500.0

    def test_tax_amount_negative(self):
        root = _parse(build_isdoc(self._dobropis()))
        tax_amt = _find(root, "TaxTotal/TaxSubTotal/TaxAmount")
        assert float(tax_amt.text) == -105.0


# ---------------------------------------------------------------------------
# Vrubopis – kladné částky
# ---------------------------------------------------------------------------

class TestVrubopis:
    def _vrubopis(self) -> ExtractionResult:
        return ExtractionResult(
            is_machine_pdf=True, confidence=0.9,
            document_type="vrubopis", currency="CZK", vat_rate=21.0,
            lines=[
                ExtractedLine(name="Doplatek", quantity=1.0, unit_price=300.0, vat_rate=21.0),
            ],
        )

    def test_line_extension_positive(self):
        root = _parse(build_isdoc(self._vrubopis()))
        line = _findall(root, "InvoiceLine")[0]
        ext = line.find(f"{_P}LineExtensionAmount")
        assert float(ext.text) == 300.0

    def test_taxable_amount_positive(self):
        root = _parse(build_isdoc(self._vrubopis()))
        taxable = _find(root, "TaxTotal/TaxSubTotal/TaxableAmount")
        assert float(taxable.text) == 300.0


# ---------------------------------------------------------------------------
# Fallback (žádné položky) – aggregate line
# ---------------------------------------------------------------------------

class TestFallbackNoLines:
    def test_single_line_created(self):
        r = _basic_result()  # no lines
        root = _parse(build_isdoc(r))
        lines = _findall(root, "InvoiceLine")
        assert len(lines) == 1

    def test_fallback_description(self):
        r = _basic_result()
        root = _parse(build_isdoc(r))
        desc = _find(root, "InvoiceLine/Item/Description")
        assert desc is not None and desc.text == "Zboží / Služby"

    def test_fallback_amount(self):
        r = _basic_result(amount_without_vat=1000.0)
        root = _parse(build_isdoc(r))
        ext = _find(root, "InvoiceLine/LineExtensionAmount")
        assert float(ext.text) == 1000.0
