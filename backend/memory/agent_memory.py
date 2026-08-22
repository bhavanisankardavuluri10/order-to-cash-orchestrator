"""
Agent Memory — MongoDB-backed persistent memory for workflow history and audit.

This is the PERSISTENT layer. For LIVE runtime coordination, use SharedMemoryBus.

Responsibilities:
    - Store workflow state in MongoDB for recovery
    - Store workflow events for audit trail
    - Store completed agent messages
    - Provide workflow retrieval for history display
"""
from models.messages import AgentMessage, HandoffLog, RoutingDecision, WorkflowEvent
from database import get_db
from datetime import datetime


class AgentMemory:
    """Persistent memory backed by MongoDB Atlas."""

    @staticmethod
    async def create_workflow(workflow_id: str, plan: dict = None):
        db = get_db()
        workflow = HandoffLog(workflow_id=workflow_id)
        doc = workflow.model_dump(by_alias=True)
        if plan:
            doc["plan"] = plan
        await db.workflows.insert_one(doc)
        return workflow_id

    @staticmethod
    async def add_step(workflow_id: str, message: AgentMessage):
        db = get_db()
        await db.workflows.update_one(
            {"workflow_id": workflow_id},
            {"$push": {"steps": message.model_dump(by_alias=True)}}
        )

    @staticmethod
    async def add_routing_decision(workflow_id: str, decision: RoutingDecision):
        db = get_db()
        await db.workflows.update_one(
            {"workflow_id": workflow_id},
            {"$push": {"routing_decisions": decision.model_dump(by_alias=True)}}
        )

    @staticmethod
    async def complete_workflow(workflow_id: str, final_status: str, total_time: float):
        db = get_db()
        await db.workflows.update_one(
            {"workflow_id": workflow_id},
            {"$set": {
                "final_status": final_status,
                "total_execution_time": round(total_time, 2),
                "completed_at": datetime.utcnow().isoformat(),
            }}
        )

    @staticmethod
    async def get_workflow(workflow_id: str) -> dict:
        db = get_db()
        return await db.workflows.find_one({"workflow_id": workflow_id}, {"_id": 0})

    # ─── Workflow Events (Audit Trail) ──────────────────

    @staticmethod
    async def record_event(workflow_id: str, event_type: str,
                           from_agent: str = "", to_agent: str = "",
                           payload: dict = None):
        """Record a single event in the workflow_events audit trail."""
        db = get_db()
        event = WorkflowEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload or {}
        )
        await db.workflow_events.insert_one(event.model_dump())

    @staticmethod
    async def get_workflow_events(workflow_id: str) -> list:
        """Get all events for a workflow (audit trail)."""
        db = get_db()
        events = await db.workflow_events.find(
            {"workflow_id": workflow_id},
            {"_id": 0}
        ).sort("timestamp", 1).to_list(500)
        return events

    # ─── Idempotency Check ──────────────────────────────

    @staticmethod
    async def check_idempotency(idempotency_key: str) -> dict:
        """Check if an order with this idempotency key already exists."""
        if not idempotency_key:
            return None
        db = get_db()
        existing = await db.orders.find_one(
            {"idempotency_key": idempotency_key},
            {"_id": 0}
        )
        return existing
