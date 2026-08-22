"""
Inventory Checker Agent — Checks stock and RESERVES items.

Uses a reservation model:
    1. Check available quantity
    2. RESERVE fulfillable quantity (decrement available, increment reserved)
    3. Orchestrator COMMITS on success or RELEASES on failure

This prevents inventory disappearing when downstream agents fail.

Returns:
    SUCCESS (fulfilled) → all items available and reserved
    BUSINESS_EXCEPTION (partial) → some items short, partial reservation
    BUSINESS_EXCEPTION (insufficient) → zero items available
"""
from agents.base_agent import BaseAgent, SUCCESS, BUSINESS_EXCEPTION
from models.messages import AgentMessage
from models.order import ValidatedOrder
from models.inventory import ProcessedLineItem, StockCheckResult


class InventoryCheckerAgent(BaseAgent):
    def __init__(self):
        super().__init__("inventory_checker")

    async def process(self, input_message: AgentMessage, db) -> AgentMessage:
        validated_order = ValidatedOrder(**input_message.payload.get("validated_order", {}))

        processed_items = []
        backorder_items = []
        all_fulfilled = True
        any_fulfilled = False

        for item in validated_order.line_items:
            product = await db.inventory.find_one({"_id": item.product_id})
            if not product:
                continue

            qty_available = product.get("quantity_available", 0)
            requested_qty = item.quantity
            fulfillable_qty = min(requested_qty, qty_available)
            shortfall = requested_qty - fulfillable_qty

            if shortfall > 0:
                all_fulfilled = False
                backorder_items.append({
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "shortfall": shortfall
                })

            if fulfillable_qty > 0:
                any_fulfilled = True

            processed_items.append(ProcessedLineItem(
                product_id=item.product_id,
                product_name=item.product_name,
                requested_quantity=requested_qty,
                fulfillable_quantity=fulfillable_qty,
                shortfall=shortfall,
                unit_price=item.unit_price
            ))

            # RESERVE stock (not commit) — atomic MongoDB update
            if fulfillable_qty > 0:
                await db.inventory.update_one(
                    {"_id": item.product_id, "quantity_available": {"$gte": fulfillable_qty}},
                    {
                        "$inc": {
                            "quantity_available": -fulfillable_qty,
                            "quantity_reserved": fulfillable_qty,
                        }
                    }
                )

        # Determine status
        if all_fulfilled:
            status = "fulfilled"
            result_type = SUCCESS
        elif any_fulfilled:
            status = "partial"
            result_type = BUSINESS_EXCEPTION
        else:
            status = "insufficient"
            result_type = BUSINESS_EXCEPTION

        result = StockCheckResult(
            status=status,
            line_items=processed_items,
            backorder_items=backorder_items
        )

        return AgentMessage(
            workflow_id=input_message.workflow_id,
            from_agent=self.name,
            to_agent="orchestrator",
            message_type="response",
            payload={
                **result.model_dump(),
                "result_type": result_type,
            }
        )

    @staticmethod
    async def commit_reservation(db, workflow_id: str, line_items: list):
        """
        Commit reserved stock after successful workflow.
        Moves items from 'reserved' to 'committed' (decrements reserved).
        """
        for item in line_items:
            if item.get("fulfillable_quantity", 0) > 0:
                await db.inventory.update_one(
                    {"_id": item["product_id"]},
                    {"$inc": {"quantity_reserved": -item["fulfillable_quantity"]}}
                )

    @staticmethod
    async def release_reservation(db, workflow_id: str, line_items: list):
        """
        Release reserved stock on workflow failure.
        Returns items from 'reserved' back to 'available'.
        """
        for item in line_items:
            if item.get("fulfillable_quantity", 0) > 0:
                await db.inventory.update_one(
                    {"_id": item["product_id"]},
                    {
                        "$inc": {
                            "quantity_available": item["fulfillable_quantity"],
                            "quantity_reserved": -item["fulfillable_quantity"],
                        }
                    }
                )
