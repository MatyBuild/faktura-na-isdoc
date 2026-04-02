"""Testy parsování ISDOC XML → ExtractedDocument."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from isdoc import isdoc_to_extracted
from models import DocumentType, PaymentMethod


_BASIC_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>1</DocumentType>
  <ID>FV2024001</ID>
  <IssueDate>2024-03-15</IssueDate>
  <TaxPointDate>2024-03-15</TaxPointDate>
  <DueDate>2024-03-29</DueDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PartyIdentification><ID>25596641</ID></PartyIdentification>
      <PartyTaxScheme>
        <CompanyID>CZ25596641</CompanyID>
        <TaxScheme>VAT</TaxScheme>
      </PartyTaxScheme>
      <PartyName><Name>Acme s.r.o.</Name></PartyName>
      <PostalAddress>
        <StreetName>Testovací 1</StreetName>
        <CityName>Praha</CityName>
        <PostalZone>11000</PostalZone>
        <Country><IdentificationCode>CZ</IdentificationCode></Country>
      </PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans>
    <Payment>
      <PaymentMeansCode>42</PaymentMeansCode>
      <VariableSymbol>2024001</VariableSymbol>
    </Payment>
  </PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="CZK">1000.00</TaxableAmount>
      <TaxAmount currencyID="CZK">210.00</TaxAmount>
      <TaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="CZK">1000.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="CZK">1210.00</TaxInclusiveAmount>
    <PayableAmount currencyID="CZK">1210.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">1000.00</LineExtensionAmount>
    <Item><Description>Vývojové práce</Description></Item>
    <Price><PriceAmount currencyID="CZK">1000.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


_DOBROPIS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>3</DocumentType>
  <ID>D2024001</ID>
  <IssueDate>2024-03-20</IssueDate>
  <TaxPointDate>2024-03-20</TaxPointDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PostalAddress>
        <Country><IdentificationCode>CZ</IdentificationCode></Country>
      </PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans><Payment><PaymentMeansCode>42</PaymentMeansCode></Payment></PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="CZK">-500.00</TaxableAmount>
      <TaxAmount currencyID="CZK">-105.00</TaxAmount>
      <TaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="CZK">-500.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="CZK">-605.00</TaxInclusiveAmount>
    <PayableAmount currencyID="CZK">-605.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">-500.00</LineExtensionAmount>
    <Item><Description>Vrácené zboží</Description></Item>
    <Price><PriceAmount currencyID="CZK">-500.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


_FOREIGN_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>1</DocumentType>
  <ID>INV-001</ID>
  <IssueDate>2024-03-15</IssueDate>
  <TaxPointDate>2024-03-15</TaxPointDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <CurrencyCode>EUR</CurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PartyName><Name>Foreign GmbH</Name></PartyName>
      <PostalAddress>
        <Country><IdentificationCode>DE</IdentificationCode></Country>
      </PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans><Payment><PaymentMeansCode>42</PaymentMeansCode></Payment></PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="EUR">100.00</TaxableAmount>
      <TaxAmount currencyID="EUR">21.00</TaxAmount>
      <TaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="EUR">100.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="EUR">121.00</TaxInclusiveAmount>
    <PayableAmount currencyID="EUR">121.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="EUR">100.00</LineExtensionAmount>
    <Item><Description>Service</Description></Item>
    <Price><PriceAmount currencyID="EUR">100.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


_MULTILINE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="http://isdoc.cz/namespace/2013" version="6.0.2">
  <DocumentType>1</DocumentType>
  <ID>FV2024002</ID>
  <IssueDate>2024-03-15</IssueDate>
  <TaxPointDate>2024-03-15</TaxPointDate>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <AccountingSupplierParty>
    <Party>
      <PostalAddress><Country><IdentificationCode>CZ</IdentificationCode></Country></PostalAddress>
    </Party>
  </AccountingSupplierParty>
  <PaymentMeans><Payment><PaymentMeansCode>42</PaymentMeansCode></Payment></PaymentMeans>
  <TaxTotal>
    <TaxSubTotal>
      <TaxableAmount currencyID="CZK">2000.00</TaxableAmount>
      <TaxAmount currencyID="CZK">420.00</TaxAmount>
      <TaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></TaxCategory>
    </TaxSubTotal>
  </TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="CZK">2000.00</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="CZK">2420.00</TaxInclusiveAmount>
    <PayableAmount currencyID="CZK">2420.00</PayableAmount>
  </LegalMonetaryTotal>
  <InvoiceLine>
    <ID>1</ID>
    <InvoicedQuantity unitCode="ZZ">2</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">1000.00</LineExtensionAmount>
    <Item><Description>Položka A</Description></Item>
    <Price><PriceAmount currencyID="CZK">500.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
  <InvoiceLine>
    <ID>2</ID>
    <InvoicedQuantity unitCode="ZZ">1</InvoicedQuantity>
    <LineExtensionAmount currencyID="CZK">1000.00</LineExtensionAmount>
    <Item><Description>Položka B</Description></Item>
    <Price><PriceAmount currencyID="CZK">1000.00</PriceAmount></Price>
    <ClassifiedTaxCategory><Percent>21</Percent><TaxScheme>VAT</TaxScheme></ClassifiedTaxCategory>
  </InvoiceLine>
</Invoice>"""


_ZALOHA_XML = _BASIC_XML.replace("<DocumentType>1</DocumentType>",
                                  "<DocumentType>2</DocumentType>")


# ---------------------------------------------------------------------------
# Testy
# ---------------------------------------------------------------------------

class TestBasicParsing:
    def test_document_type(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.document_type == DocumentType.faktura

    def test_original_number(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.original_number == "FV2024001"

    def test_issued_on(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.issued_on == "2024-03-15"

    def test_due_on(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.due_on == "2024-03-29"

    def test_supplier_name(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.supplier_name == "Acme s.r.o."

    def test_registration_no(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.registration_no == "25596641"

    def test_vat_no(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.vat_no == "CZ25596641"

    def test_variable_symbol(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.variable_symbol == "2024001"

    def test_payment_method_bank(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.payment_method == PaymentMethod.bank

    def test_currency_czk(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.currency == "CZK"

    def test_amount_total(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.amount_total == 1210.0

    def test_reverse_charge_false(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.reverse_charge is False

    def test_confidence(self):
        doc = isdoc_to_extracted(_BASIC_XML)
        assert doc.confidence == 0.85


class TestDobropisParsing:
    def test_document_type(self):
        doc = isdoc_to_extracted(_DOBROPIS_XML)
        assert doc.document_type == DocumentType.dobropis

    def test_line_negative(self):
        doc = isdoc_to_extracted(_DOBROPIS_XML)
        assert len(doc.lines) == 1
        assert doc.lines[0].unit_price == -500.0


class TestForeignSupplier:
    def test_reverse_charge(self):
        doc = isdoc_to_extracted(_FOREIGN_XML)
        assert doc.reverse_charge is True

    def test_supplier_country(self):
        doc = isdoc_to_extracted(_FOREIGN_XML)
        assert doc.supplier_country == "DE"

    def test_currency_eur(self):
        doc = isdoc_to_extracted(_FOREIGN_XML)
        assert doc.currency == "EUR"

    def test_vat_rate_forced_21(self):
        doc = isdoc_to_extracted(_FOREIGN_XML)
        assert all(li.vat_rate == 21.0 for li in doc.lines)


class TestMultipleLines:
    def test_line_count(self):
        doc = isdoc_to_extracted(_MULTILINE_XML)
        assert len(doc.lines) == 2

    def test_line_names(self):
        doc = isdoc_to_extracted(_MULTILINE_XML)
        names = [li.name for li in doc.lines]
        assert "Položka A" in names
        assert "Položka B" in names

    def test_line_quantity(self):
        doc = isdoc_to_extracted(_MULTILINE_XML)
        assert doc.lines[0].quantity == 2.0


class TestZaloha:
    def test_document_type(self):
        doc = isdoc_to_extracted(_ZALOHA_XML)
        assert doc.document_type == DocumentType.zaloha


class TestInvalidXml:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Neplatné ISDOC XML"):
            isdoc_to_extracted("<neplatny xml>")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            isdoc_to_extracted("")

    def test_partial_xml_raises(self):
        with pytest.raises(ValueError):
            isdoc_to_extracted("<?xml version='1.0'?><Invoice>")
