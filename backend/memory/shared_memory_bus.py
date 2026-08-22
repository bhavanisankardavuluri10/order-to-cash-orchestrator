"""
Shared Memory Bus — Runtime coordination layer for agent communication.

This is the LIVE communication mechanism. Agents publish and receive messages
through the bus, NOT by calling each other directly.

MongoDB is for persistence/audit — NOT for live agent coordination.

Architecture:
    Agent A → publish(msg) → Bus → receive("agent_b") → Agent B
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any


class SharedMemoryBus:
    """
    In-process async event bus.

    Each agent has a dedicated asyncio.Queue. Publishing a message
    routes it to the target agent's queue. The orchestrator can also
    subscribe to see all messages flowing through the bus.
    """

    def __init__(self):
        # Per-agent message queues
        self._queues: Dict[str, asyncio.Queue] = {}
        # All messages indexed by workflow_id
        self._messages: Dict[str, List[dict]] = {}
        # Runtime workflow state (not MongoDB — in-memory only)
        self._workflow_state: Dict[str, dict] = {}
        # Event listeners for side-effects (e.g., pushing to EventManager)
        self._listeners: List[Callable] = []
        # Lock for thread-safe state updates
        self._lock = asyncio.Lock()

    # ─── Subscription ───────────────────────────────────

    def subscribe(self, agent_name: str):
        """Register an agent to receive messages. Creates its queue."""
        if agent_name not in self._queues:
            self._queues[agent_name] = asyncio.Queue()

    def add_listener(self, callback: Callable):
        """
        Add a listener that is called for every message published.
        Used by EventManager to forward events to WebSocket clients.
        """
        self._listeners.append(callback)

    # ─── Publish / Receive ──────────────────────────────

    async def publish(self, message: dict):
        """
        Publish a message to the bus.
        Routes it to the target agent's queue.
        Also stores it in the workflow's message log.
        """
        workflow_id = message.get("workflow_id", "unknown")
        to_agent = message.get("to_agent", "")
        timestamp = datetime.utcnow().isoformat()

        # Enrich with bus metadata
        message["bus_timestamp"] = timestamp

        # Store in workflow message log
        async with self._lock:
            if workflow_id not in self._messages:
                self._messages[workflow_id] = []
            self._messages[workflow_id].append(message)

        # Route to target agent's queue
        if to_agent in self._queues:
            await self._queues[to_agent].put(message)

        # Notify all listeners (e.g., EventManager for WebSocket)
        for listener in self._listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(message)
                else:
                    listener(message)
            except Exception as e:
                print(f"[Bus] Listener error: {e}")

    async def receive(self, agent_name: str, timeout: float = 120.0) -> Optional[dict]:
        """
        Wait for the next message targeted at this agent.
        Returns None on timeout.
        """
        if agent_name not in self._queues:
            self.subscribe(agent_name)

        try:
            message = await asyncio.wait_for(
                self._queues[agent_name].get(),
                timeout=timeout
            )
            return message
        except asyncio.TimeoutError:
            return None

    # ─── Workflow State Management ──────────────────────

    async def create_workflow_state(self, workflow_id: str, initial_data: dict = None):
        """Create runtime state for a new workflow."""
        async with self._lock:
            self._workflow_state[workflow_id] = {
                "workflow_id": workflow_id,
                "current_stage": "RECEIVED",
                "created_at": datetime.utcnow().isoformat(),
                "agent_outputs": {},
                "routing_decisions": [],
                **(initial_data or {})
            }

    async def get_state(self, workflow_id: str) -> Optional[dict]:
        """Get current runtime state for a workflow."""
        return self._workflow_state.get(workflow_id)

    async def update_state(self, workflow_id: str, updates: dict):
        """Update runtime workflow state."""
        async with self._lock:
            if workflow_id in self._workflow_state:
                self._workflow_state[workflow_id].update(updates)
                self._workflow_state[workflow_id]["updated_at"] = datetime.utcnow().isoformat()

    async def set_agent_output(self, workflow_id: str, agent_name: str, output: dict):
        """Store an agent's output in the workflow state."""
        async with self._lock:
            if workflow_id in self._workflow_state:
                self._workflow_state[workflow_id]["agent_outputs"][agent_name] = output

    async def add_routing_decision(self, workflow_id: str, decision: dict):
        """Record a routing decision in the workflow state."""
        async with self._lock:
            if workflow_id in self._workflow_state:
                self._workflow_state[workflow_id]["routing_decisions"].append(decision)

    # ─── Message Retrieval ──────────────────────────────

    def get_messages(self, workflow_id: str) -> List[dict]:
        """Get all messages for a workflow (for audit/debugging)."""
        return self._messages.get(workflow_id, [])

    # ─── Cleanup ────────────────────────────────────────

    async def cleanup_workflow(self, workflow_id: str):
        """Remove runtime state for a completed workflow (memory management)."""
        async with self._lock:
            self._workflow_state.pop(workflow_id, None)
            # Keep messages for a bit (don't delete immediately)

    async def drain_queue(self, agent_name: str):
        """Clear all pending messages for an agent."""
        if agent_name in self._queues:
            while not self._queues[agent_name].empty():
                try:
                    self._queues[agent_name].get_nowait()
                except asyncio.QueueEmpty:
                    break
