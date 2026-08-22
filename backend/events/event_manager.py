"""
Event Manager — Bridges backend agent events to the React frontend via WebSocket.

Stream A: Agent ↔ Agent communication (via Shared Memory Bus) — internal
Stream B: Agent/Orchestrator → WebSocket → React UI — this module

The Event Manager listens to the Shared Memory Bus and selectively
forwards relevant events to all connected WebSocket clients.
"""
import asyncio
import json
from datetime import datetime
from typing import List, Optional
from fastapi import WebSocket


class EventManager:
    """
    Manages WebSocket connections and broadcasts live workflow events
    from the backend to the React frontend.
    """

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._event_log: List[dict] = []  # Recent events buffer
        self._lock = asyncio.Lock()

    # ─── WebSocket Connection Management ────────────────

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    # ─── Event Publishing ───────────────────────────────

    async def publish_event(self, event_type: str, data: dict):
        """
        Publish a structured event to all connected WebSocket clients.

        Event format sent to frontend:
        {
            "type": "agent_started" | "agent_completed" | "routing_decision" | ...,
            "data": { ... },
            "timestamp": "2026-08-22T..."
        }
        """
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Buffer for debugging
        self._event_log.append(event)
        if len(self._event_log) > 500:
            self._event_log = self._event_log[-250:]

        await self._broadcast(event)

    async def _broadcast(self, event: dict):
        """Send event to all connected WebSocket clients."""
        dead_connections = []

        for ws in list(self._connections):
            try:
                await ws.send_text(json.dumps(event, default=str))
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if ws in self._connections:
                        self._connections.remove(ws)

    # ─── Bus Listener (called by SharedMemoryBus) ──────

    async def on_bus_message(self, message: dict):
        """
        Callback registered with the SharedMemoryBus.
        Converts internal agent messages into frontend-friendly events.
        """
        msg_type = message.get("message_type", "")
        from_agent = message.get("from_agent", "")
        to_agent = message.get("to_agent", "")
        workflow_id = message.get("workflow_id", "")

        # Forward agent communication as a live event
        await self.publish_event("agent_message", {
            "workflow_id": workflow_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_type": msg_type,
            "timestamp": message.get("timestamp", ""),
        })

    # ─── Convenience Event Methods ──────────────────────

    async def emit_workflow_started(self, workflow_id: str, plan: dict = None):
        await self.publish_event("workflow_started", {
            "workflow_id": workflow_id,
            "plan": plan or {},
        })

    async def emit_agent_started(self, workflow_id: str, agent_name: str, task_summary: str = ""):
        await self.publish_event("agent_started", {
            "workflow_id": workflow_id,
            "agent": agent_name,
            "task_summary": task_summary,
        })

    async def emit_agent_completed(self, workflow_id: str, agent_name: str, response: dict):
        await self.publish_event("agent_completed", {
            "workflow_id": workflow_id,
            "agent": agent_name,
            "response": response,
        })

    async def emit_routing_decision(self, workflow_id: str, decision: str, reasoning: str, context: dict = None):
        await self.publish_event("routing_decision", {
            "workflow_id": workflow_id,
            "decision": decision,
            "reasoning": reasoning,
            "context": context or {},
        })

    async def emit_workflow_state_change(self, workflow_id: str, from_stage: str, to_stage: str, reason: str = ""):
        await self.publish_event("workflow_state_change", {
            "workflow_id": workflow_id,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "reason": reason,
        })

    async def emit_workflow_completed(self, workflow_id: str, final_status: str, summary: dict = None):
        await self.publish_event("workflow_completed", {
            "workflow_id": workflow_id,
            "final_status": final_status,
            "summary": summary or {},
        })

    async def emit_qwen_thinking(self, workflow_id: str, stage: str, detail: str = ""):
        """Emit a Qwen thinking/planning event for UI display."""
        await self.publish_event("qwen_thinking", {
            "workflow_id": workflow_id,
            "stage": stage,
            "detail": detail,
        })

    @property
    def connection_count(self) -> int:
        return len(self._connections)
