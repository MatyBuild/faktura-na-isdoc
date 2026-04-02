"""Testy datových modelů."""
import pytest
from models import DocumentType, PaymentMethod, LineItem, ExtractedDocument


def test_document_type_values():
    assert DocumentType.faktura  == "faktura"
    assert DocumentType.zaloha   == "zaloha"
    assert DocumentType.dobropis == "dobropis"
    assert DocumentType.vrubopis == "vrubopis"
    assert DocumentType.uctenka  == "uctenka"
    assert DocumentType.unknown  == "unknown"


def test_payment_method_values():
    assert PaymentMethod.bank  == "bank"
    assert PaymentMethod.cash  == "cash"
    assert PaymentMethod.card  == "card"
    assert PaymentMethod.cod   == "cod"
    assert PaymentMethod.other == "other"


def test_line_item_defaults():
    li = LineItem(name="Služba", unit_price=100.0)
    assert li.quantity  == 1.0
    assert li.vat_rate  == 0.0
    assert li.unit_name is None


def test_extracted_document_defaults():
    doc = ExtractedDocument(document_type=DocumentType.faktura)
    assert doc.confidence        == 0.0
    assert doc.supplier_country  == "CZ"
    assert doc.currency          == "CZK"
    assert doc.reverse_charge    is False
    assert doc.payment_method    == PaymentMethod.bank
    assert doc.lines             == []
    assert doc.amount_total      is None


def test_line_item_total():
    li = LineItem(name="Zboží", quantity=3.0, unit_price=200.0, vat_rate=21.0)
    assert li.quantity * li.unit_price == 600.0


def test_document_type_serialization():
    doc = ExtractedDocument(document_type=DocumentType.dobropis)
    data = doc.model_dump()
    assert data["document_type"] == "dobropis"
