"""
Invoice Generator Agent — Creates GST-compliant invoices in INR (₹).

Runs AFTER Inventory Checker confirms stock allocation.
Generates a proper Indian tax invoice with:
    - CGST 9% + SGST 9% = 18% GST
    - Invoice number format: INV-YYYYMMDD-XXXX
    - All amounts in ₹ (Indian Rupees)

Persists invoice to dedicated 'invoices' collection.
"""
from agents.base_agent import BaseAgent, SUCCESS
from models.messages import AgentMessage
from models.order import Invoice, InvoiceLineItem
from models.inventory import StockCheckResult
from llm.ollama_client import OllamaClient
import datetime
import random


class InvoiceGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("invoice_generator")

    async def process(self, input_message: AgentMessage, db) -> AgentMessage:
        stock_result = StockCheckResult(**input_message.payload.get("stock_result", {}))
        order_details = input_message.payload.get("validated_order", {})

        invoice_items = []
        subtotal = 0.0

        for item in stock_result.line_items:
            if item.fulfillable_quantity > 0:
                line_total = item.fulfillable_quantity * item.unit_price
                subtotal += line_total
                invoice_items.append(InvoiceLineItem(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    quantity=item.fulfillable_quantity,
                    unit_price=item.unit_price,
                    line_total=round(line_total, 2)
                ))

        # Indian GST: CGST 9% + SGST 9% = 18%
        cgst = round(subtotal * 0.09, 2)
        sgst = round(subtotal * 0.09, 2)
        tax = round(cgst + sgst, 2)
        grand_total = round(subtotal + tax, 2)

        date_str = datetime.datetime.utcnow().strftime("%Y%m%d")
        rand_suffix = f"{random.randint(1000, 9999)}"
        invoice_number = f"INV-{date_str}-{rand_suffix}"

        invoice = Invoice(
            invoice_number=invoice_number,
            order_id=input_message.workflow_id,
            workflow_id=input_message.workflow_id,
            customer_id=order_details.get("customer_id", "UNKNOWN"),
            customer_name=order_details.get("customer_name", "Unknown"),
            line_items=invoice_items,
            subtotal=round(subtotal, 2),
            cgst=cgst,
            sgst=sgst,
            tax=tax,
            grand_total=grand_total
        )

        # LLM summary (non-critical)
        try:
            prompt = f"Invoice: {invoice_number}, Customer: {order_details.get('customer_name', 'N/A')}, Total: ₹{grand_total:,.2f}, Items: {len(invoice_items)}, GST: ₹{tax:,.2f}"
            system_prompt = (
                "You are an invoicing system for an Indian e-commerce platform. "
                "Provide a polite 1-2 sentence summary mentioning the invoice number, "
                "total amount in ₹, and GST (18%) included. Keep it brief."
            )
            summary = await OllamaClient.generate_response(prompt, system_prompt)
            invoice.summary = summary
        except Exception:
            invoice.summary = f"Invoice {invoice_number} generated for ₹{grand_total:,.2f} (incl. 18% GST)."

        # Persist to invoices collection
        invoice_doc = invoice.model_dump()
        invoice_doc["_id"] = invoice_number
        await db.invoices.update_one(
            {"_id": invoice_number},
            {"$set": invoice_doc},
            upsert=True
        )

        return AgentMessage(
            workflow_id=input_message.workflow_id,
            from_agent=self.name,
            to_agent="orchestrator",
            message_type="response",
            payload={
                "invoice": invoice.model_dump(),
                "gst": {"cgst": cgst, "sgst": sgst, "total_gst": tax},
                "result_type": SUCCESS,
            }
        )
