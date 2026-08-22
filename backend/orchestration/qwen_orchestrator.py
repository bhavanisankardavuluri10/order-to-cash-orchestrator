"""
Qwen Orchestrator — The AI reasoning layer above the workflow engine.

RESPONSIBILITIES:
    1. Parse natural-language user request → structured order JSON
    2. Create the workflow plan (identify which agents are needed)
    3. During workflow: interpret agent results, decide next routing step
    4. After workflow: produce human-readable final response

WHAT QWEN DOES NOT DO:
    - Calculate inventory quantities
    - Compute invoice totals or tax
    - Determine risk scores
    - Directly modify MongoDB
    These are handled by deterministic Python code in specialist agents.
"""
import json
import re
from llm.ollama_client import OllamaClient

# Known customer aliases for deterministic fallback
CUSTOMER_ALIASES = {
    "reliance": "CUST-101", "reliance digital": "CUST-101",
    "croma": "CUST-102", "croma electronics": "CUST-102",
    "poorvika": "CUST-103", "poorvika mobiles": "CUST-103",
    "techbazaar": "CUST-201", "tech bazaar": "CUST-201",
    "vijay sales": "CUST-104", "vijay": "CUST-104",
    "amazon": "CUST-105", "amazon india": "CUST-105",
}

# Known product aliases for deterministic fallback
PRODUCT_ALIASES = {
    "earbuds": "SKU-1001", "airdopes": "SKU-1001", "boat": "SKU-1001",
    "phone": "SKU-1002", "samsung": "SKU-1002", "galaxy": "SKU-1002", "m14": "SKU-1002",
    "watch": "SKU-1003", "smartwatch": "SKU-1003", "smart watch": "SKU-1003", "noise": "SKU-1003",
    "power bank": "SKU-1004", "powerbank": "SKU-1004", "ambrane": "SKU-1004",
    "laptop": "SKU-1005", "gaming laptop": "SKU-1005", "victus": "SKU-1005", "hp": "SKU-1005",
    "jeans": "SKU-1006", "levis": "SKU-1006", "levi's": "SKU-1006",
}


class QwenOrchestrator:
    """
    The AI brain that interprets user requests and orchestrates the workflow.
    Falls back to deterministic parsing if Ollama is unavailable.
    """

    async def parse_natural_language(self, user_text: str) -> dict:
        """
        Convert natural language order request into structured JSON.

        Example input:  "Order 50 earbuds for Reliance Digital"
        Example output: {"customer_id": "CUST-101", "line_items": [{"product_id": "SKU-1001", "quantity": 50}]}
        """
        # Try LLM first
        system_prompt = """You are an order processing assistant for an Indian e-commerce B2B platform.
Parse the user's natural language order request into a JSON object.

Available customers:
- CUST-101: Reliance Digital Stores
- CUST-102: Croma Electronics
- CUST-103: Poorvika Mobiles
- CUST-201: TechBazaar Online
- CUST-104: Vijay Sales
- CUST-105: Amazon India Seller Hub

Available products:
- SKU-1001: boAt Airdopes 141 (Wireless Earbuds)
- SKU-1002: Samsung Galaxy M14 5G (128GB)
- SKU-1003: Noise ColorFit Pro 4 Smart Watch
- SKU-1004: Ambrane 20000mAh Power Bank
- SKU-1005: HP Victus 15 Gaming Laptop
- SKU-1006: Levi's Men's 511 Slim Fit Jeans

Return ONLY a valid JSON object in this exact format (no markdown, no explanation):
{
  "customer_id": "CUST-XXX",
  "shipping_priority": "standard",
  "line_items": [
    {"product_id": "SKU-XXXX", "quantity": N}
  ]
}

If you cannot identify the customer or product, use your best guess from the available options.
Default shipping_priority to "standard" unless "express", "rush", or "urgent" is mentioned."""

        try:
            response = await OllamaClient.generate_response(user_text, system_prompt)
            parsed = self._extract_json(response)
            if parsed and "customer_id" in parsed and "line_items" in parsed:
                return parsed
        except Exception as e:
            print(f"[QwenOrchestrator] LLM parse failed: {e}")

        # Fallback: deterministic parsing
        return self._deterministic_parse(user_text)

    async def interpret_agent_result(self, agent_name: str, result: dict, workflow_context: dict) -> dict:
        """
        Qwen interprets an agent's output and decides the next routing step.
        Returns a routing decision dict.
        """
        # This is deterministic routing — Qwen adds narrative only
        if agent_name == "order_validator":
            status = result.get("status", "")
            if status == "invalid":
                return {
                    "decision": "REJECT",
                    "reasoning": f"❌ Order rejected — {result.get('errors', 'Validation failed')}",
                    "next_agent": None
                }
            return {
                "decision": "PROCEED_TO_INVENTORY",
                "reasoning": "✅ Order valid. Routing to Inventory Checker.",
                "next_agent": "inventory_checker"
            }

        elif agent_name == "inventory_checker":
            status = result.get("status", "")
            if status == "insufficient":
                return {
                    "decision": "BACKORDER",
                    "reasoning": "❌ All items out of stock. Creating backorder.",
                    "next_agent": None
                }
            elif status == "partial":
                return {
                    "decision": "PARTIAL_FULFILL",
                    "reasoning": "⚠️ Some items short. Generating invoice for available items + backorder for rest.",
                    "next_agent": "invoice_generator"
                }
            else:
                return {
                    "decision": "PROCEED_TO_INVOICE",
                    "reasoning": "✅ All items in stock. Routing to Invoice Generator.",
                    "next_agent": "invoice_generator"
                }

        elif agent_name == "invoice_generator":
            return {
                "decision": "PROCEED_TO_RISK",
                "reasoning": "✅ Invoice generated. Routing to Payment Risk assessment.",
                "next_agent": "payment_risk"
            }

        elif agent_name == "payment_risk":
            risk_data = result.get("risk_assessment", {})
            risk_level = risk_data.get("risk_level", "low")
            inv_status = workflow_context.get("inventory_status", "fulfilled")

            if inv_status == "partial":
                return {
                    "decision": "COMPLETE",
                    "reasoning": f"🏁 Workflow complete — Partial fulfillment. Risk: {risk_level.upper()}.",
                    "next_agent": None,
                    "final_status": "partial_fulfilled"
                }
            else:
                return {
                    "decision": "COMPLETE",
                    "reasoning": f"🏁 Workflow complete — All items fulfilled. Risk: {risk_level.upper()}.",
                    "next_agent": None,
                    "final_status": "completed"
                }

        return {"decision": "UNKNOWN", "reasoning": "Unrecognized agent", "next_agent": None}

    async def generate_final_response(self, workflow_result: dict) -> str:
        """Generate a human-readable final response summarizing the workflow."""
        status = workflow_result.get("final_status", "unknown")
        invoice = workflow_result.get("invoice", {})
        risk = workflow_result.get("risk_assessment", {})

        # Try LLM narrative
        prompt = f"""Workflow result:
Status: {status}
Invoice: {invoice.get('invoice_number', 'N/A')}, Total: ₹{invoice.get('grand_total', 0):,.2f}
Risk: {risk.get('risk_level', 'N/A')} ({risk.get('risk_score', 0)}/100)
Customer: {invoice.get('customer_id', 'N/A')}"""

        system_prompt = (
            "You are an order processing assistant. Provide a brief 2-3 sentence summary "
            "of the completed order workflow. Mention the invoice number, total in ₹, "
            "and risk level. Be professional and concise."
        )

        try:
            response = await OllamaClient.generate_response(prompt, system_prompt)
            if response and "unavailable" not in response.lower():
                return response
        except Exception:
            pass

        # Fallback
        if status == "completed":
            return f"Order completed successfully. Invoice {invoice.get('invoice_number', 'N/A')} generated for ₹{invoice.get('grand_total', 0):,.2f}. Risk assessment: {risk.get('risk_level', 'low').upper()}."
        elif status == "partial_fulfilled":
            return f"Order partially fulfilled. Invoice {invoice.get('invoice_number', 'N/A')} for ₹{invoice.get('grand_total', 0):,.2f}. Backorder created for remaining items."
        elif status == "backordered":
            return "All items are out of stock. A backorder has been created."
        elif status == "rejected":
            return f"Order rejected: {workflow_result.get('errors', 'Validation failed')}."
        return f"Workflow completed with status: {status}."

    # ─── Private Helpers ────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        """Extract JSON object from LLM response text."""
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try finding JSON in code block
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding any JSON object
        match = re.search(r'\{[^{}]*"customer_id"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _deterministic_parse(self, text: str) -> dict:
        """
        Fallback parser: extract order info from natural language using regex + aliases.
        """
        text_lower = text.lower().strip()

        # Find customer
        customer_id = None
        for alias, cid in sorted(CUSTOMER_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in text_lower:
                customer_id = cid
                break

        # If customer_id is directly mentioned (e.g., "CUST-101")
        if not customer_id:
            cust_match = re.search(r'(CUST-\d+)', text, re.IGNORECASE)
            if cust_match:
                customer_id = cust_match.group(1).upper()

        if not customer_id:
            customer_id = "CUST-101"  # Default to Reliance Digital

        # Find products and quantities
        line_items = []

        # Pattern: "50 earbuds" or "10 units of SKU-1001"
        qty_product_patterns = [
            r'(\d+)\s+(?:units?\s+(?:of\s+)?)?(?:of\s+)?([\w\s\'-]+?)(?:\s+(?:for|to|from|and|\.|,|$))',
            r'(\d+)\s*[x×]\s*([\w\s\'-]+?)(?:\s+(?:for|to|from|and|\.|,|$))',
        ]

        for pattern in qty_product_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                qty = int(match.group(1))
                product_text = match.group(2).strip()

                # Try to resolve product alias
                product_id = None
                for alias, pid in sorted(PRODUCT_ALIASES.items(), key=lambda x: -len(x[0])):
                    if alias in product_text:
                        product_id = pid
                        break

                if not product_id:
                    # Try direct SKU match
                    sku_match = re.search(r'(SKU-\d+)', product_text, re.IGNORECASE)
                    if sku_match:
                        product_id = sku_match.group(1).upper()

                if product_id and qty > 0:
                    # Avoid duplicates
                    if not any(li["product_id"] == product_id for li in line_items):
                        line_items.append({"product_id": product_id, "quantity": qty})

        # Direct SKU-XXXX pattern anywhere in text
        if not line_items:
            sku_matches = re.finditer(r'(\d+)\s+(?:units?\s+(?:of\s+)?)?(SKU-\d+)', text, re.IGNORECASE)
            for match in sku_matches:
                qty = int(match.group(1))
                pid = match.group(2).upper()
                if qty > 0:
                    line_items.append({"product_id": pid, "quantity": qty})

        # Fallback: if no items found
        if not line_items:
            line_items = [{"product_id": "SKU-1001", "quantity": 10}]

        # Detect shipping priority
        shipping_priority = "standard"
        if any(w in text_lower for w in ["express", "rush", "urgent", "fast"]):
            shipping_priority = "express"

        return {
            "customer_id": customer_id,
            "shipping_priority": shipping_priority,
            "line_items": line_items
        }
