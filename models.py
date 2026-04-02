from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class DocumentType(str, Enum):
    faktura  = "faktura"
    zaloha   = "zaloha"    # Zálohová faktura / proforma (pozor: není vždy daňový doklad)
    dobropis = "dobropis"  # Opravný daňový doklad – snížení (záporné částky)
    vrubopis = "vrubopis"  # Opravný daňový doklad – zvýšení (kladné částky)
    uctenka  = "uctenka"   # Zjednodušený daňový doklad (paragon, max 10 000 Kč)
    unknown  = "unknown"


class PaymentMethod(str, Enum):
    bank  = "bank"
    cash  = "cash"
    card  = "card"
    cod   = "cod"
    other = "other"


class LineItem(BaseModel):
    name: str
    quantity: float = 1.0
    unit_price: float
    vat_rate: float = 0.0
    unit_name: Optional[str] = None


class ExtractedDocument(BaseModel):
    document_type: DocumentType
    confidence: float = 0.0
    supplier_name: Optional[str] = None
    registration_no: Optional[str] = None
    vat_no: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    supplier_country: str = "CZ"
    original_number: Optional[str] = None
    issued_on: Optional[str] = None
    taxable_fulfillment_due: Optional[str] = None
    due_on: Optional[str] = None
    variable_symbol: Optional[str] = None
    payment_method: PaymentMethod = PaymentMethod.bank
    currency: str = "CZK"
    exchange_rate: Optional[float] = None
    reverse_charge: bool = False
    amount_total: Optional[float] = None   # z LegalMonetaryTotal/PayableAmount
    lines: List[LineItem] = []
