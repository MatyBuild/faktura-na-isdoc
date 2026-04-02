"""Testy kódového extraktoru (bez API, bez OCR)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pdf_extractor import (
    _parse_amount, _parse_date, _valid_ico,
    _extract_vat_rate, _extract_document_type,
    _extract_currency, _extract_ico, _extract_vat_no,
    _extract_amounts,
)


# ---------------------------------------------------------------------------
# _parse_amount
# ---------------------------------------------------------------------------

class TestParseAmount:
    def test_czech_format(self):
        assert _parse_amount("1 234,56") == 1234.56

    def test_eu_format(self):
        assert _parse_amount("1.234,56") == 1234.56

    def test_plain_decimal(self):
        assert _parse_amount("1234.56") == 1234.56

    def test_integer(self):
        assert _parse_amount("1000") == 1000.0

    def test_nbsp(self):
        assert _parse_amount("10\xa0000,00") == 10000.0

    def test_invalid(self):
        assert _parse_amount("abc") is None

    def test_zero(self):
        assert _parse_amount("0,00") == 0.0


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_dmy(self):
        assert _parse_date("Datum: 15.03.2024") == "2024-03-15"

    def test_iso(self):
        assert _parse_date("2024-03-15") == "2024-03-15"

    def test_short_day_month(self):
        assert _parse_date("1.3.2024") == "2024-03-01"

    def test_no_date(self):
        assert _parse_date("žádné datum tady") is None

    def test_hint_issued(self):
        text = "Datum vystavení: 10.01.2024 Datum splatnosti: 20.01.2024"
        assert _parse_date(text, hint="vystavení") == "2024-01-10"

    def test_hint_due(self):
        text = "Datum vystavení: 10.01.2024 Datum splatnosti: 20.01.2024"
        assert _parse_date(text, hint="splatnost") == "2024-01-20"


# ---------------------------------------------------------------------------
# _valid_ico
# ---------------------------------------------------------------------------

class TestValidIco:
    def test_valid(self):
        assert _valid_ico("27082440") is True   # Škoda Auto

    def test_valid_2(self):
        assert _valid_ico("25596641") is True

    def test_invalid_checksum(self):
        assert _valid_ico("27082441") is False

    def test_too_short(self):
        assert _valid_ico("1234567") is False

    def test_non_numeric(self):
        assert _valid_ico("1234567X") is False


# ---------------------------------------------------------------------------
# _extract_vat_rate
# ---------------------------------------------------------------------------

class TestExtractVatRate:
    def test_21(self):
        assert _extract_vat_rate("DPH 21 %") == 21.0

    def test_12(self):
        assert _extract_vat_rate("sazba daně 12%") == 12.0

    def test_zero(self):
        assert _extract_vat_rate("osvobozeno 0 %") == 0.0

    def test_default_21(self):
        assert _extract_vat_rate("žádná sazba") == 21.0


# ---------------------------------------------------------------------------
# _extract_document_type
# ---------------------------------------------------------------------------

class TestExtractDocumentType:
    def test_faktura_default(self):
        assert _extract_document_type("Faktura č. 2024001") == "faktura"

    def test_dobropis(self):
        assert _extract_document_type("DOBROPIS č. D2024001") == "dobropis"

    def test_dobropis_credit_note(self):
        assert _extract_document_type("Credit Note 2024/01") == "dobropis"

    def test_vrubopis(self):
        assert _extract_document_type("VRUBOPIS č. V2024001") == "vrubopis"

    def test_vrubopis_debit_note(self):
        assert _extract_document_type("Debit Note 123") == "vrubopis"

    def test_uctenka(self):
        assert _extract_document_type("PARAGON č. 123") == "uctenka"

    def test_uctenka_pokladni(self):
        assert _extract_document_type("Pokladní doklad") == "uctenka"

    def test_zaloha(self):
        assert _extract_document_type("Zálohová faktura č. Z001") == "zaloha"

    def test_proforma(self):
        assert _extract_document_type("PROFORMA INVOICE") == "zaloha"

    def test_proforma_with_space(self):
        assert _extract_document_type("Pro Forma Invoice 2024") == "zaloha"


# ---------------------------------------------------------------------------
# _extract_currency
# ---------------------------------------------------------------------------

class TestExtractCurrency:
    def test_czk_default(self):
        assert _extract_currency("Celkem: 1 000 Kč") == "CZK"

    def test_eur(self):
        assert _extract_currency("Total: 100 EUR") == "EUR"

    def test_usd(self):
        assert _extract_currency("Amount: 50 USD") == "USD"


# ---------------------------------------------------------------------------
# _extract_amounts
# ---------------------------------------------------------------------------

class TestExtractAmounts:
    def test_all_present(self):
        text = "Základ daně: 1000,00 DPH celkem: 210,00 Celkem k úhradě: 1210,00"
        base, vat, total = _extract_amounts(text)
        assert base  == 1000.0
        assert vat   == 210.0
        assert total == 1210.0

    def test_derive_vat(self):
        text = "Základ daně: 1000,00 Celkem k úhradě: 1210,00"
        base, vat, total = _extract_amounts(text)
        assert base  == 1000.0
        assert vat   == 210.0
        assert total == 1210.0

    def test_derive_total(self):
        text = "Základ daně: 1000,00 DPH celkem: 210,00"
        base, vat, total = _extract_amounts(text)
        assert total == 1210.0

    def test_none_when_missing(self):
        base, vat, total = _extract_amounts("žádné částky")
        assert base  is None
        assert vat   is None
        assert total is None
