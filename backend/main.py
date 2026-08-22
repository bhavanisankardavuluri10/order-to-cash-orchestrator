"""
FastAPI Application — Multi-Agent Order-to-Cash Orchestrator

Startup sequence:
    1. Connect to MongoDB Atlas
    2. Initialize Shared Memory Bus
    3. Initialize Event Manager
    4. Initialize Qwen Orchestrator
    5. Start all 4 specialist agents (they subscribe to bus and listen)
    6. Start WebSocket Manager

The agents remain alive and listening throughout the application lifecycle.
They are NOT created from scratch for every user request.
"""
import datetime
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from database import connect_to_mongo, close_mongo_connection, get_db
from config import settings
from memory.shared_memory_bus import SharedMemoryBus
from events.event_manager import EventManager
from orchestrator import Orchestrator

app = FastAPI(title="Multi-Agent Order-to-Cash Orchestrator", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global Infrastructure ─────────────────────────────
bus = SharedMemoryBus()
event_manager = EventManager()
orchestrator = Orchestrator(event_manager=event_manager, bus=bus)


# ═══════════════════════════════════════════════════
# LIFECYCLE
# ═══════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    # 1. Connect MongoDB
    await connect_to_mongo()

    # 2. Wire bus → event manager (forward bus messages to WebSocket)
    bus.add_listener(event_manager.on_bus_message)

    # 3. Subscribe all agents to the bus
    for agent in [orchestrator.validator, orchestrator.inventory,
                  orchestrator.invoice, orchestrator.risk]:
        agent.set_bus(bus)
        agent.set_db_getter(get_db)
        bus.subscribe(agent.name)

    # 4. Subscribe orchestrator
    bus.subscribe("orchestrator")

    print("===========================================")
    print("  [*] Multi-Agent O2C Orchestrator v2.0")
    print("  [+] Shared Memory Bus: ACTIVE")
    print("  [+] Event Manager: ACTIVE")
    print("  [+] Agents: 4 specialists ready")
    print("  [+] Qwen Orchestrator: READY")
    print("===========================================")


@app.on_event("shutdown")
async def shutdown():
    for agent in [orchestrator.validator, orchestrator.inventory,
                  orchestrator.invoice, orchestrator.risk]:
        agent.stop()
    await close_mongo_connection()


# ═══════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await event_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await event_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════
# ORDER ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/orders")
async def create_order(order: dict):
    """Submit a structured order for processing."""
    workflow_id = f"WF-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"
    result = await orchestrator.process_order(order, workflow_id)
    return result


@app.post("/api/orders/intent")
async def create_order_by_intent(body: dict):
    """
    Dynamic intent-based order.
    Qwen reads live inventory and builds the order plan itself.
    Body: {"intent": "bulk_order", "customer_id": "CUST-101"}
    No hardcoded product IDs needed — the planner picks from actual stock.
    """
    from orchestration.order_planner import build_dynamic_order
    intent = body.get("intent", "medium_order")
    customer_id = body.get("customer_id", "CUST-101")
    db = get_db()

    # Planner reads live inventory and builds the order
    planned_order = await build_dynamic_order(intent, customer_id, db)

    # Emit planning event to UI
    workflow_id = f"WF-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"
    await event_manager.emit_qwen_thinking(
        workflow_id,
        "planning",
        f"Building '{planned_order.get('_intent_label')}' — picked {len(planned_order['line_items'])} products from live inventory"
    )

    # Strip internal metadata before passing to orchestrator
    order_payload = {
        "customer_id": planned_order["customer_id"],
        "shipping_priority": planned_order["shipping_priority"],
        "line_items": planned_order["line_items"],
    }

    result = await orchestrator.process_order(order_payload, workflow_id)
    # Attach plan info to response so frontend can show what was planned
    result["plan"] = {
        "intent": intent,
        "intent_label": planned_order.get("_intent_label"),
        "intent_description": planned_order.get("_intent_description"),
        "selected_products": planned_order.get("_selected_products", []),
    }
    return result


@app.get("/api/orders/intents")
async def list_intents():
    """Return all available intent types for the frontend."""
    from orchestration.order_planner import get_intent_list
    return get_intent_list()




@app.post("/api/orders/natural")
async def create_order_natural(body: dict):
    """
    Submit a natural language order for Qwen to parse.
    Body: {"text": "Order 50 earbuds for Reliance Digital"}
    """
    user_text = body.get("text", "")
    if not user_text:
        return {"status": "error", "message": "No text provided"}

    workflow_id = f"WF-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"
    result = await orchestrator.process_natural_language(user_text, workflow_id)
    return result


# ═══════════════════════════════════════════════════
# DATA ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/api/inventory")
async def get_inventory():
    db = get_db()
    items = await db.inventory.find().to_list(100)
    for item in items:
        item["_id"] = str(item["_id"])
    return items


@app.get("/api/customers")
async def get_customers():
    db = get_db()
    customers = await db.customers.find().to_list(100)
    for c in customers:
        c["_id"] = str(c["_id"])
    return customers


@app.get("/api/orders")
async def get_orders():
    db = get_db()
    orders = await db.orders.find().sort("created_at", -1).to_list(100)
    for o in orders:
        if "_id" in o:
            o["_id"] = str(o["_id"])
    return orders


@app.get("/api/invoices")
async def get_invoices():
    db = get_db()
    invoices = await db.invoices.find().sort("date", -1).to_list(100)
    for inv in invoices:
        if "_id" in inv:
            inv["_id"] = str(inv["_id"])
    return invoices


@app.get("/api/backorders")
async def get_backorders():
    db = get_db()
    backorders = await db.backorders.find().sort("created_at", -1).to_list(100)
    for bo in backorders:
        if "_id" in bo:
            bo["_id"] = str(bo["_id"])
    return backorders


@app.get("/api/workflows")
async def get_workflows():
    db = get_db()
    workflows = await db.workflows.find().sort("created_at", -1).to_list(100)
    for w in workflows:
        if "_id" in w:
            w["_id"] = str(w["_id"])
    return workflows


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    db = get_db()
    wf = await db.workflows.find_one({"workflow_id": workflow_id})
    if wf and "_id" in wf:
        wf["_id"] = str(wf["_id"])
    return wf


@app.get("/api/workflow-events/{workflow_id}")
async def get_workflow_events(workflow_id: str):
    """Get the full audit trail for a specific workflow."""
    from memory.agent_memory import AgentMemory
    events = await AgentMemory.get_workflow_events(workflow_id)
    return events


# ═══════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/reset-inventory")
async def reset_inventory():
    """Reset inventory and all data to seed values for demo."""
    from seed_data import seed_database
    await seed_database()
    return {"message": "All data reset to seed values."}


@app.get("/api/sample-orders")
async def get_sample_orders():
    """Return sample order payloads matching actual seed data SKUs."""
    return {
        "happy_path": {
            "customer_id": "CUST-101",
            "shipping_priority": "standard",
            "line_items": [
                {"product_id": "SKU-1001", "quantity": 10},
                {"product_id": "SKU-1004", "quantity": 5}
            ]
        },
        "partial_fulfill": {
            "customer_id": "CUST-102",
            "shipping_priority": "express",
            "line_items": [
                {"product_id": "SKU-1002", "quantity": 30},
                {"product_id": "SKU-1006", "quantity": 5}
            ]
        },
        "insufficient": {
            "customer_id": "CUST-103",
            "shipping_priority": "standard",
            "line_items": [
                {"product_id": "SKU-1003", "quantity": 10}
            ]
        },
        "invalid": {
            "customer_id": "CUST-999",
            "shipping_priority": "rush",
            "line_items": [
                {"product_id": "SKU-1001", "quantity": -5}
            ]
        }
    }


@app.get("/api/system-status")
async def system_status():
    """Return system health and connected client count."""
    return {
        "status": "running",
        "version": "2.0",
        "websocket_clients": event_manager.connection_count,
        "agents": ["order_validator", "inventory_checker", "invoice_generator", "payment_risk"],
        "bus": "active",
        "event_manager": "active",
    }
