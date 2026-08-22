from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class LineItemInput(BaseModel):
    product_id: str
    quantity: int


class OrderInput(BaseModel):
    customer_id: str
    shipping_priority: str = "standard"
    line_items: List[LineItemInput]
    idempotency_key: Optional[str] = None  # Prevents duplicate order processing


class ValidatedLineItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float


class ValidatedOrder(BaseModel):
    order_id: str
    customer_id: str
    customer_name: str
    order_date: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    shipping_priority: str
    line_items: List[ValidatedLineItem]
    validation_summary: Optional[str] = None


class InvoiceLineItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class Invoice(BaseModel):
    invoice_number: str
    order_id: str
    workflow_id: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    date: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    line_items: List[InvoiceLineItem]
    subtotal: float
    cgst: float = 0.0
    sgst: float = 0.0
    tax: float
    grand_total: float
    summary: Optional[str] = None


class BackorderRecord(BaseModel):
    backorder_id: Optional[str] = None
    order_id: str
    workflow_id: Optional[str] = None
    customer_id: str
    items: List[dict]  # product_id, product_name, shortfall_quantity
    status: str = "pending"  # "pending" | "restocked" | "cancelled"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
