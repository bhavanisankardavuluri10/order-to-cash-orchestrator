"""
Routing Engine — Dependency-aware agent execution ordering.

Defines the execution graph:
    Validator → Inventory → Invoice → Risk

Handles branching for:
    - Full fulfillment → Invoice → Risk → COMPLETED
    - Partial fulfillment → Invoice (for available qty) → Risk → PARTIAL_FULFILLED
    - Insufficient stock → BACKORDERED (skip Invoice & Risk)
    - Validation failure → REJECTED (skip all downstream agents)
"""
from typing import List, Optional


# Agent execution order (dependency chain)
AGENT_PIPELINE = [
    "order_validator",
    "inventory_checker",
    "invoice_generator",
    "payment_risk",
]

# Which agents can run after which
AGENT_DEPENDENCIES = {
    "order_validator": [],                  # No dependencies — runs first
    "inventory_checker": ["order_validator"],  # Needs validated order
    "invoice_generator": ["inventory_checker"],  # Needs fulfillment result
    "payment_risk": ["invoice_generator"],      # Needs invoice context
}


def get_next_agent(current_agent: str, result_status: str) -> Optional[str]:
    """
    Determine the next agent in the pipeline based on the current agent's result.
    Returns None if the workflow should terminate or branch.
    """
    if current_agent == "order_validator":
        if result_status == "invalid":
            return None  # Workflow terminates with REJECT
        return "inventory_checker"

    elif current_agent == "inventory_checker":
        if result_status == "insufficient":
            return None  # Workflow terminates with BACKORDER
        # Both "fulfilled" and "partial" proceed to invoice
        return "invoice_generator"

    elif current_agent == "invoice_generator":
        return "payment_risk"

    elif current_agent == "payment_risk":
        return None  # Workflow complete

    return None


def get_required_agents(intent: str) -> List[str]:
    """
    Given an order intent, return the list of required agents.
    For standard orders, all 4 agents are needed.
    """
    if intent == "create_sales_order":
        return list(AGENT_PIPELINE)
    # Could add more intents later (e.g., "check_inventory_only")
    return list(AGENT_PIPELINE)


def get_agent_display_name(agent_id: str) -> str:
    """Return human-readable agent name."""
    names = {
        "order_validator": "Order Validator",
        "inventory_checker": "Inventory Checker",
        "invoice_generator": "Invoice Generator",
        "payment_risk": "Payment Risk Assessor",
        "orchestrator": "Qwen Orchestrator",
    }
    return names.get(agent_id, agent_id)
