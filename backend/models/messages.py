"""
Message Models — Enhanced agent communication types.

Every message has a unique message_id and workflow_id for traceability.
Messages flow through the Shared Memory Bus, not direct function calls.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid


class AgentMessage(BaseModel):
    """Core message type for all agent-to-agent communication."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    workflow_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    from_agent: str
    to_agent: str

    message_type: str  # "task" | "response" | "event" | "error" | "routing_decision" | "state_update"

    status: str = "pending"  # "pending" | "processing" | "completed" | "failed"

    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # metadata can include: parent_message_id, execution_time_ms, retry_count, agent_version

    def to_bus_dict(self) -> dict:
        """Convert to dict for bus transmission."""
        return self.model_dump()


class RoutingDecision(BaseModel):
    """Records an orchestrator routing decision."""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    workflow_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    decision: str  # "PROCEED_TO_INVENTORY", "PROCEED_TO_INVOICE", "PROCEED_TO_RISK",
                   # "PARTIAL_FULFILL", "BACKORDER", "REJECT", "COMPLETE", "RISK_HOLD"

    reasoning: str
    context: Dict[str, Any] = Field(default_factory=dict)
    next_agent: Optional[str] = None


class HandoffLog(BaseModel):
    """Full workflow execution log."""
    workflow_id: str
    steps: List[AgentMessage] = Field(default_factory=list)
    routing_decisions: List[RoutingDecision] = Field(default_factory=list)
    final_status: str = "pending"  # "pending" | "completed" | "partial_fulfilled" |
                                    # "backorder_created" | "rejected" | "failed"
    total_execution_time: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class WorkflowEvent(BaseModel):
    """Audit trail entry for workflow_events collection."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    workflow_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    event_type: str  # "agent_started" | "agent_completed" | "routing_decision" |
                     # "state_change" | "workflow_started" | "workflow_completed"
    from_agent: str = ""
    to_agent: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
