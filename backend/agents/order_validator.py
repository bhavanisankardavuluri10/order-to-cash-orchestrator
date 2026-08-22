"""
Order Validator Agent — Validates customer identity, product existence, and quantities.

Runs as a bus-connected worker. Receives tasks from the orchestrator via the bus,
performs deterministic validation against MongoDB, and publishes results back.

Returns:
    SUCCESS     → validated_order with resolved customer name, product names, prices
    BUSINESS_EXCEPTION → invalid order (bad customer, bad product, negative qty)
"""
from agents.base_agent import BaseAgent, SUCCESS, BUSINESS_EXCEPTION
from models.messages import AgentMessage
from models.order import OrderInput, ValidatedOrder, ValidatedLineItem
from pydantic import ValidationError
from llm.ollama_client import OllamaClient


class OrderValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("order_validator")

    async def process(self, input_message: AgentMessage, db) -> AgentMessage:
        # 1. Schema validation
        try:
            order_input = OrderInput(**input_message.payload)
        except ValidationError as e:
            return AgentMessage(
                workflow_id=input_message.workflow_id,
                from_agent=self.name,
                to_agent="orchestrator",
                message_type="response",
                payload={
                    "status": "invalid",
                    "result_type": BUSINESS_EXCEPTION,
                    "errors": str(e),
                }
            )

        # 2. Customer lookup
        customer = await db.customers.find_one({"_id": order_input.customer_id})
        if not customer:
            return AgentMessage(
                workflow_id=input_message.workflow_id,
                from_agent=self.name,
                to_agent="orchestrator",
                message_type="response",
                payload={
                    "status": "invalid",
                    "result_type": BUSINESS_EXCEPTION,
                    "errors": f"Customer {order_input.customer_id} not found.",
                }
            )

        # 3. Validate each line item
        validated_items = []
        errors = []

        for item in order_input.line_items:
            if item.quantity <= 0:
                errors.append(f"Product {item.product_id} has invalid quantity {item.quantity}")
                continue

            product = await db.inventory.find_one({"_id": item.product_id})
            if not product:
                errors.append(f"Product {item.product_id} not found in inventory.")
                continue

            validated_items.append(ValidatedLineItem(
                product_id=product["_id"],
                product_name=product["name"],
                quantity=item.quantity,
                unit_price=product["unit_price"]
            ))

        if errors:
            return AgentMessage(
                workflow_id=input_message.workflow_id,
                from_agent=self.name,
                to_agent="orchestrator",
                message_type="response",
                payload={
                    "status": "invalid",
                    "result_type": BUSINESS_EXCEPTION,
                    "errors": "; ".join(errors),
                }
            )

        # 4. Build validated order
        validated_order = ValidatedOrder(
            order_id=input_message.workflow_id,
            customer_id=customer["_id"],
            customer_name=customer["name"],
            shipping_priority=order_input.shipping_priority,
            line_items=validated_items
        )

        # 5. Optional LLM enrichment (non-critical)
        try:
            system_prompt = "You are an order validation assistant for an Indian B2B e-commerce platform. Provide a brief 1-sentence summary of the validated order mentioning customer name, items, and quantities."
            prompt = f"Order: {validated_order.model_dump_json()}"
            summary = await OllamaClient.generate_response(prompt, system_prompt)
            validated_order.validation_summary = summary
        except Exception:
            validated_order.validation_summary = f"Order validated for {customer['name']}: {len(validated_items)} item(s)."

        return AgentMessage(
            workflow_id=input_message.workflow_id,
            from_agent=self.name,
            to_agent="orchestrator",
            message_type="response",
            payload={
                "status": "valid",
                "result_type": SUCCESS,
                "validated_order": validated_order.model_dump(),
            }
        )
