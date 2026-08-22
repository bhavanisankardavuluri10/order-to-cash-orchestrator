"""
Workflow State Machine — Explicit states and legal transitions.

Every workflow progresses through a defined set of states.
Invalid transitions are rejected, preventing corrupted workflows.
"""
from enum import Enum
from typing import Dict, Set, Optional


class WorkflowStage(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INVENTORY_CHECK = "INVENTORY_CHECK"
    FULFILLED = "FULFILLED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    INVOICING = "INVOICING"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    COMPLETED = "COMPLETED"
    PARTIAL_FULFILLED = "PARTIAL_FULFILLED"
    BACKORDERED = "BACKORDERED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


# Legal state transitions
TRANSITIONS: Dict[WorkflowStage, Set[WorkflowStage]] = {
    WorkflowStage.RECEIVED: {WorkflowStage.VALIDATING},
    WorkflowStage.VALIDATING: {WorkflowStage.VALIDATED, WorkflowStage.VALIDATION_FAILED},
    WorkflowStage.VALIDATION_FAILED: {WorkflowStage.REJECTED},
    WorkflowStage.VALIDATED: {WorkflowStage.INVENTORY_CHECK},
    WorkflowStage.INVENTORY_CHECK: {
        WorkflowStage.FULFILLED,
        WorkflowStage.PARTIAL,
        WorkflowStage.INSUFFICIENT,
        WorkflowStage.FAILED,
    },
    WorkflowStage.FULFILLED: {WorkflowStage.INVOICING, WorkflowStage.FAILED},
    WorkflowStage.PARTIAL: {WorkflowStage.INVOICING, WorkflowStage.FAILED},
    WorkflowStage.INSUFFICIENT: {WorkflowStage.BACKORDERED, WorkflowStage.FAILED},
    WorkflowStage.INVOICING: {WorkflowStage.RISK_ASSESSMENT, WorkflowStage.FAILED},
    WorkflowStage.RISK_ASSESSMENT: {
        WorkflowStage.COMPLETED,
        WorkflowStage.PARTIAL_FULFILLED,
        WorkflowStage.FAILED,
    },
    # Terminal states — no further transitions
    WorkflowStage.COMPLETED: set(),
    WorkflowStage.PARTIAL_FULFILLED: set(),
    WorkflowStage.BACKORDERED: set(),
    WorkflowStage.REJECTED: set(),
    WorkflowStage.FAILED: set(),
}

# Terminal states
TERMINAL_STATES = {
    WorkflowStage.COMPLETED,
    WorkflowStage.PARTIAL_FULFILLED,
    WorkflowStage.BACKORDERED,
    WorkflowStage.REJECTED,
    WorkflowStage.FAILED,
}


class WorkflowStateMachine:
    """
    Manages the state of a single workflow.
    Validates that transitions are legal before applying them.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.current_stage = WorkflowStage.RECEIVED
        self.history: list = [{"stage": WorkflowStage.RECEIVED, "reason": "Workflow created"}]

    def transition(self, to_stage: WorkflowStage, reason: str = "") -> bool:
        """
        Attempt to transition to a new stage.
        Returns True if the transition was legal and applied.
        Returns False if the transition is illegal.
        """
        if to_stage in TRANSITIONS.get(self.current_stage, set()):
            prev = self.current_stage
            self.current_stage = to_stage
            self.history.append({
                "from": prev.value,
                "to": to_stage.value,
                "reason": reason
            })
            return True
        else:
            print(
                f"[WorkflowStateMachine] ILLEGAL transition: "
                f"{self.current_stage.value} → {to_stage.value} "
                f"(workflow {self.workflow_id})"
            )
            return False

    @property
    def is_terminal(self) -> bool:
        return self.current_stage in TERMINAL_STATES

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "current_stage": self.current_stage.value,
            "is_terminal": self.is_terminal,
            "history": self.history
        }
