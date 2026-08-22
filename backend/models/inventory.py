from pydantic import BaseModel
from typing import List, Optional


class InventoryItem(BaseModel):
    id: str  # maps to _id in mongo
    name: str
    category: str
    quantity_available: int
    quantity_reserved: int = 0  # Reservation model: reserved during workflow
    reorder_point: int
    unit_cost: float
    unit_price: float
    warehouse: str


class ProcessedLineItem(BaseModel):
    product_id: str
    product_name: str
    requested_quantity: int
    fulfillable_quantity: int
    shortfall: int
    unit_price: float


class StockCheckResult(BaseModel):
    status: str  # "fulfilled", "partial", "insufficient"
    line_items: List[ProcessedLineItem]
    backorder_items: List[dict]  # product_id, product_name, shortfall
