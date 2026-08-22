"""
Payment Risk Agent — Deterministic customer payment risk assessment.

Risk Factors (Indian B2B context):
    - New customer (< 3 orders)        → +25 points
    - Overdue payment history           → +25 points
    - Order exceeds credit limit        → +30 points
    - High-value order (> ₹50,000)     → +15 points
    - Rush/express shipping             → +10 points
    - PREPAID payment terms (new acct)  → +5 points

Risk Levels:
    ≤ 20  → LOW    (auto-approve)
    ≤ 45  → MEDIUM (auto-approve with flag)
    > 45  → HIGH   (requires manual approval)
"""
from agents.base_agent import BaseAgent, SUCCESS
from models.messages import AgentMessage
from llm.ollama_client import OllamaClient


class PaymentRiskAgent(BaseAgent):
    def __init__(self):
        super().__init__("payment_risk")

    async def process(self, input_message: AgentMessage, db) -> AgentMessage:
        validated_order = input_message.payload.get("validated_order", {})
        customer_id = input_message.payload.get("customer_id") or validated_order.get("customer_id")

        customer = await db.customers.find_one({"_id": customer_id})
        if not customer:
            return AgentMessage(
                workflow_id=input_message.workflow_id,
                from_agent=self.name,
                to_agent="orchestrator",
                message_type="error",
                status="failed",
                payload={
                    "error": f"Customer {customer_id} not found for risk assessment.",
                    "result_type": "BUSINESS_EXCEPTION",
                }
            )

        risk_score = 0
        risk_factors = []

        # Calculate estimated order value
        line_items = validated_order.get("line_items", [])
        estimated_total = sum(
            li.get("unit_price", 0) * li.get("quantity", 0)
            for li in line_items
        )

        # ─── Risk Rules (deterministic — NOT LLM) ─────
        total_orders = customer.get("total_orders", 0)
        if total_orders == 0:
            risk_score += 25
            risk_factors.append("Brand new customer — zero order history")
        elif total_orders < 3:
            risk_score += 15
            risk_factors.append(f"New customer (only {total_orders} previous orders)")

        overdue = customer.get("overdue_payments", 0)
        if overdue > 0:
            risk_score += 25
            risk_factors.append(f"Has {overdue} overdue payment(s)")

        credit_limit = customer.get("credit_limit", 100000)
        if estimated_total > credit_limit:
            risk_score += 30
            risk_factors.append(f"Order ₹{estimated_total:,.0f} exceeds credit limit ₹{credit_limit:,.0f}")

        if estimated_total > 50000:
            risk_score += 15
            risk_factors.append(f"High-value order (₹{estimated_total:,.0f})")

        shipping = validated_order.get("shipping_priority", "standard")
        if shipping in ("express", "rush"):
            risk_score += 10
            risk_factors.append("Express/rush shipping requested")

        if customer.get("payment_terms") == "PREPAID":
            risk_score += 5
            risk_factors.append("Account requires prepaid terms")

        # Determine risk level
        if risk_score <= 20:
            risk_level = "low"
            requires_approval = False
        elif risk_score <= 45:
            risk_level = "medium"
            requires_approval = False
        else:
            risk_level = "high"
            requires_approval = True

        risk_data = {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "requires_approval": requires_approval,
            "customer_name": customer.get("name"),
            "customer_tier": customer.get("risk_tier"),
            "credit_limit": credit_limit,
            "estimated_order_value": estimated_total,
        }

        # LLM risk narrative (non-critical enrichment)
        try:
            customer_safe = {k: v for k, v in customer.items() if k != "_id"}
            prompt = f"Customer profile: {customer_safe}. Order Risk Data: {risk_data}."
            system_prompt = (
                "You are a credit risk analyst for an Indian e-commerce B2B platform. "
                "Provide a 1-paragraph risk assessment explaining the risk level. "
                "Mention specific factors like payment history, credit limit, and order value in INR (₹). "
                "Keep it concise — 3-4 sentences max."
            )
            llm_assessment = await OllamaClient.generate_response(prompt, system_prompt)
            risk_data["llm_assessment"] = llm_assessment
        except Exception:
            risk_data["llm_assessment"] = (
                f"Risk assessment: {risk_level.upper()} ({risk_score}/100). "
                f"{'Manual approval required.' if requires_approval else 'Auto-approved.'}"
            )

        return AgentMessage(
            workflow_id=input_message.workflow_id,
            from_agent=self.name,
            to_agent="orchestrator",
            message_type="response",
            payload={
                "risk_assessment": risk_data,
                "result_type": SUCCESS,
            }
        )
