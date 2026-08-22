"""
Orchestrator — The central brain of the multi-agent system.

NEW ARCHITECTURE:
═════════════════
The Orchestrator no longer calls agents directly.
Instead, it uses the Shared Memory Bus for all agent communication.

Flow:
    1. Receive user request (structured JSON or natural language)
    2. Qwen parses intent → structured order
    3. Create workflow in bus + MongoDB
    4. Publish tasks to agents via bus
    5. Receive results from agents via bus
    6. Route to next agent based on results
    7. Persist everything to MongoDB
    8. Emit events to UI via EventManager

Agent Communication:
    Orchestrator → Bus → Agent → Bus → Orchestrator → Bus → Next Agent → ...

IMPORTANT: Qwen does NOT calculate inventory, invoices, or risk scores.
Those are deterministic Python operations inside the specialist agents.
"""
import asyncio
import time
import uuid
from datetime import datetime

from models.messages import AgentMessage, RoutingDecision
from models.order import BackorderRecord
from memory.agent_memory import AgentMemory
from memory.workflow_state import WorkflowStateMachine, WorkflowStage
from orchestration.qwen_orchestrator import QwenOrchestrator
from agents.order_validator import OrderValidatorAgent
from agents.inventory_checker import InventoryCheckerAgent
from agents.invoice_generator import InvoiceGeneratorAgent
from agents.payment_risk import PaymentRiskAgent
from database import get_db


class Orchestrator:
    """
    Multi-agent workflow orchestrator.
    Uses Shared Memory Bus for agent communication.
    Uses EventManager for WebSocket broadcasts.
    Uses Qwen for intent parsing and natural language responses.
    """

    def __init__(self, event_manager=None, bus=None):
        # Specialist agents
        self.validator = OrderValidatorAgent()
        self.inventory = InventoryCheckerAgent()
        self.invoice = InvoiceGeneratorAgent()
        self.risk = PaymentRiskAgent()

        # Infrastructure
        self.event_manager = event_manager
        self.bus = bus
        self.qwen = QwenOrchestrator()

    async def _emit(self, event_type: str, data: dict):
        """Emit a live event to the frontend via EventManager."""
        if self.event_manager:
            await self.event_manager.publish_event(event_type, data)

    async def _record_event(self, workflow_id: str, event_type: str,
                            from_agent: str = "", to_agent: str = "",
                            payload: dict = None):
        """Record event to both EventManager (live) and MongoDB (audit)."""
        await AgentMemory.record_event(
            workflow_id, event_type,
            from_agent=from_agent, to_agent=to_agent,
            payload=payload or {}
        )

    # ═══════════════════════════════════════════════════
    # MAIN ENTRY: Process a structured order
    # ═══════════════════════════════════════════════════

    async def process_order(self, order_payload: dict, workflow_id: str) -> dict:
        """
        Process a structured order through the 4-agent pipeline.
        Uses the bus for agent communication and EventManager for UI updates.
        """
        start_time = time.time()
        db = get_db()
        comms_log = []

        # Check idempotency
        idempotency_key = order_payload.get("idempotency_key")
        if idempotency_key:
            existing = await AgentMemory.check_idempotency(idempotency_key)
            if existing:
                return {
                    "status": "duplicate",
                    "workflow_id": existing.get("workflow_id"),
                    "message": "This order has already been processed.",
                    "original_result": existing
                }

        # Initialize workflow state machine
        state_machine = WorkflowStateMachine(workflow_id)

        # Create workflow in persistent memory
        await AgentMemory.create_workflow(workflow_id, plan={
            "intent": "create_sales_order",
            "required_agents": ["order_validator", "inventory_checker", "invoice_generator", "payment_risk"],
        })

        # Create runtime state on bus
        if self.bus:
            await self.bus.create_workflow_state(workflow_id, {
                "order_payload": order_payload,
            })

        # Emit workflow started
        await self._emit("workflow_started", {"workflow_id": workflow_id})
        await self._record_event(workflow_id, "workflow_started", from_agent="orchestrator")

        # Emit Qwen thinking
        await self._emit("qwen_thinking", {
            "workflow_id": workflow_id,
            "stage": "analyzing",
            "detail": "Analyzing order request and creating execution plan..."
        })

        # ═══════════════════════════════════════════════════
        # PHASE 1: ORDER VALIDATION
        # ═══════════════════════════════════════════════════
        state_machine.transition(WorkflowStage.VALIDATING, "Starting order validation")

        val_req = AgentMessage(
            workflow_id=workflow_id,
            from_agent="orchestrator",
            to_agent="order_validator",
            message_type="task",
            payload=order_payload
        )

        comms_log.append({
            "from": "orchestrator", "to": "order_validator",
            "type": "task", "summary": "Validate order"
        })

        await self._emit("agent_started", {
            "workflow_id": workflow_id,
            "agent": "order_validator",
            "request": val_req.model_dump()
        })
        await self._record_event(workflow_id, "agent_started",
                                 from_agent="orchestrator", to_agent="order_validator")

        # Execute via bus-connected agent
        val_res = await self.validator.execute(val_req, db)
        await AgentMemory.add_step(workflow_id, val_res)

        await self._emit("agent_completed", {
            "workflow_id": workflow_id,
            "agent": "order_validator",
            "response": val_res.model_dump()
        })
        await self._record_event(workflow_id, "agent_completed",
                                 from_agent="order_validator", to_agent="orchestrator",
                                 payload={"status": val_res.payload.get("status")})

        comms_log.append({
            "from": "order_validator", "to": "orchestrator",
            "type": "response",
            "summary": f"Status: {val_res.payload.get('status')}"
        })

        # ─── Route: Validation result ───────────────────
        if val_res.payload.get("status") == "invalid":
            state_machine.transition(WorkflowStage.VALIDATION_FAILED, "Validation failed")
            state_machine.transition(WorkflowStage.REJECTED, "Order rejected")

            decision = RoutingDecision(
                workflow_id=workflow_id,
                decision="REJECT",
                reasoning=f"❌ Order rejected — {val_res.payload.get('errors')}",
                context={"errors": val_res.payload.get("errors")}
            )
            await AgentMemory.add_routing_decision(workflow_id, decision)
            await self._emit("routing_decision", decision.model_dump())
            await self._record_event(workflow_id, "routing_decision",
                                     from_agent="orchestrator",
                                     payload={"decision": "REJECT"})

            comms_log.append({
                "from": "orchestrator", "to": "ALL",
                "type": "decision", "summary": "REJECTED — Workflow terminated"
            })

            await self._save_order(db, workflow_id, "rejected", order_payload,
                                   comms_log, time.time() - start_time,
                                   state_machine=state_machine,
                                   idempotency_key=idempotency_key)

            return {
                "status": "rejected",
                "workflow_id": workflow_id,
                "errors": val_res.payload.get("errors"),
                "comms_log": comms_log,
                "state_history": state_machine.to_dict()["history"],
            }

        state_machine.transition(WorkflowStage.VALIDATED, "Order validated successfully")

        # Routing decision: proceed to parallel phase
        decision = RoutingDecision(
            workflow_id=workflow_id,
            decision="PROCEED_PARALLEL",
            reasoning="✅ Order valid. Starting Inventory Check + Risk Assessment in parallel.",
            next_agent="inventory_checker"
        )
        await AgentMemory.add_routing_decision(workflow_id, decision)
        await self._emit("routing_decision", decision.model_dump())

        # ═══════════════════════════════════════════════════
        # PHASE 2: INVENTORY CHECK + RISK ASSESSMENT (PARALLEL)
        # ═══════════════════════════════════════════════════
        state_machine.transition(WorkflowStage.INVENTORY_CHECK, "Checking inventory")

        validated_order = val_res.payload.get("validated_order")

        # Prepare both agent requests
        inv_req = AgentMessage(
            workflow_id=workflow_id,
            from_agent="orchestrator",
            to_agent="inventory_checker",
            message_type="task",
            payload={"validated_order": validated_order}
        )
        risk_req = AgentMessage(
            workflow_id=workflow_id,
            from_agent="orchestrator",
            to_agent="payment_risk",
            message_type="task",
            payload={
                "validated_order": validated_order,
                "customer_id": validated_order.get("customer_id")
            }
        )

        comms_log.append({"from": "orchestrator", "to": "inventory_checker", "type": "task", "summary": "Check stock availability"})
        comms_log.append({"from": "orchestrator", "to": "payment_risk", "type": "task", "summary": "Assess customer payment risk"})

        # Start both agents simultaneously
        await self._emit("agent_started", {"workflow_id": workflow_id, "agent": "inventory_checker"})
        await self._emit("agent_started", {"workflow_id": workflow_id, "agent": "payment_risk"})
        await self._record_event(workflow_id, "agent_started", from_agent="orchestrator", to_agent="inventory_checker")
        await self._record_event(workflow_id, "agent_started", from_agent="orchestrator", to_agent="payment_risk")

        # Run PARALLEL using asyncio.gather
        inv_res, risk_res = await asyncio.gather(
            self.inventory.execute(inv_req, db),
            self.risk.execute(risk_req, db)
        )

        # Process inventory result
        await AgentMemory.add_step(workflow_id, inv_res)
        await self._emit("agent_completed", {
            "workflow_id": workflow_id,
            "agent": "inventory_checker",
            "response": inv_res.model_dump()
        })
        await self._record_event(workflow_id, "agent_completed",
                                 from_agent="inventory_checker", to_agent="orchestrator",
                                 payload={"status": inv_res.payload.get("status")})
        comms_log.append({
            "from": "inventory_checker", "to": "orchestrator",
            "type": "response",
            "summary": f"Stock: {inv_res.payload.get('status')}"
        })

        # Process risk result
        await AgentMemory.add_step(workflow_id, risk_res)
        risk_data = risk_res.payload.get("risk_assessment", {})
        await self._emit("agent_completed", {
            "workflow_id": workflow_id,
            "agent": "payment_risk",
            "response": risk_res.model_dump()
        })
        await self._record_event(workflow_id, "agent_completed",
                                 from_agent="payment_risk", to_agent="orchestrator",
                                 payload={"risk_level": risk_data.get("risk_level")})
        comms_log.append({
            "from": "payment_risk", "to": "orchestrator",
            "type": "response",
            "summary": f"Risk: {risk_data.get('risk_level', 'N/A')} ({risk_data.get('risk_score', 0)}/100)"
        })

        inv_status = inv_res.payload.get("status")

        # ─── Route: Combined inventory + risk decision ──
        if inv_status == "insufficient":
            state_machine.transition(WorkflowStage.INSUFFICIENT, "All items out of stock")
            state_machine.transition(WorkflowStage.BACKORDERED, "Backorder created")

            decision = RoutingDecision(
                workflow_id=workflow_id,
                decision="BACKORDER",
                reasoning=f"❌ All items out of stock. Risk: {risk_data.get('risk_level', 'N/A')}. Creating backorder."
            )
            await AgentMemory.add_routing_decision(workflow_id, decision)
            await self._emit("routing_decision", decision.model_dump())

            # Create backorder record
            backorder = await self._create_backorder(db, workflow_id, validated_order, inv_res.payload)

            comms_log.append({"from": "orchestrator", "to": "ALL", "type": "decision", "summary": "BACKORDER — Insufficient inventory"})

            await self._save_order(db, workflow_id, "backorder_created", order_payload,
                                   comms_log, time.time() - start_time,
                                   risk_assessment=risk_data,
                                   backorder=backorder,
                                   state_machine=state_machine,
                                   idempotency_key=idempotency_key)

            return {
                "status": "backorder_created",
                "workflow_id": workflow_id,
                "risk_assessment": risk_data,
                "backorder": backorder,
                "comms_log": comms_log,
                "state_history": state_machine.to_dict()["history"],
            }

        # Risk hold check
        if risk_data.get("requires_approval"):
            decision = RoutingDecision(
                workflow_id=workflow_id,
                decision="RISK_HOLD",
                reasoning=f"⚠️ High risk detected (score {risk_data.get('risk_score')}/100). Proceeding with flag."
            )
            await AgentMemory.add_routing_decision(workflow_id, decision)
            await self._emit("routing_decision", decision.model_dump())

        # Transition based on inventory status
        if inv_status == "partial":
            state_machine.transition(WorkflowStage.PARTIAL, "Partial stock available")
            decision = RoutingDecision(
                workflow_id=workflow_id,
                decision="PARTIAL_FULFILL",
                reasoning=f"⚠️ Some items short. Risk: {risk_data.get('risk_level')}. Generating invoice for available items."
            )
        else:
            state_machine.transition(WorkflowStage.FULFILLED, "All items in stock")
            decision = RoutingDecision(
                workflow_id=workflow_id,
                decision="PROCEED_TO_INVOICE",
                reasoning=f"✅ Inventory fulfilled, risk is {risk_data.get('risk_level')}. Generating invoice."
            )

        await AgentMemory.add_routing_decision(workflow_id, decision)
        await self._emit("routing_decision", decision.model_dump())

        # ═══════════════════════════════════════════════════
        # PHASE 3: INVOICE GENERATION
        # ═══════════════════════════════════════════════════
        state_machine.transition(WorkflowStage.INVOICING, "Generating invoice")

        inv_gen_req = AgentMessage(
            workflow_id=workflow_id,
            from_agent="orchestrator",
            to_agent="invoice_generator",
            message_type="task",
            payload={
                "validated_order": validated_order,
                "stock_result": inv_res.payload
            }
        )

        comms_log.append({"from": "orchestrator", "to": "invoice_generator", "type": "task", "summary": "Generate GST invoice"})

        await self._emit("agent_started", {"workflow_id": workflow_id, "agent": "invoice_generator"})
        await self._record_event(workflow_id, "agent_started", from_agent="orchestrator", to_agent="invoice_generator")

        inv_gen_res = await self.invoice.execute(inv_gen_req, db)
        await AgentMemory.add_step(workflow_id, inv_gen_res)

        invoice = inv_gen_res.payload.get("invoice", {})

        await self._emit("agent_completed", {
            "workflow_id": workflow_id,
            "agent": "invoice_generator",
            "response": inv_gen_res.model_dump()
        })
        await self._record_event(workflow_id, "agent_completed",
                                 from_agent="invoice_generator", to_agent="orchestrator",
                                 payload={"invoice_number": invoice.get("invoice_number")})

        comms_log.append({
            "from": "invoice_generator", "to": "orchestrator",
            "type": "response",
            "summary": f"Invoice {invoice.get('invoice_number')} — ₹{invoice.get('grand_total', 0):,.2f}"
        })

        # ═══════════════════════════════════════════════════
        # FINALIZE WORKFLOW
        # ═══════════════════════════════════════════════════
        state_machine.transition(WorkflowStage.RISK_ASSESSMENT, "Risk assessment complete")

        final_status = "partial_fulfilled" if inv_status == "partial" else "completed"

        if final_status == "partial_fulfilled":
            state_machine.transition(WorkflowStage.PARTIAL_FULFILLED, "Partial fulfillment complete")
        else:
            state_machine.transition(WorkflowStage.COMPLETED, "Workflow complete")

        # Commit inventory reservation
        await InventoryCheckerAgent.commit_reservation(
            db, workflow_id,
            [item.model_dump() if hasattr(item, 'model_dump') else item
             for item in inv_res.payload.get("line_items", [])]
        )

        # Create backorder for partial
        backorder = None
        if inv_status == "partial":
            backorder = await self._create_backorder(db, workflow_id, validated_order, inv_res.payload)

        # Final routing decision
        decision = RoutingDecision(
            workflow_id=workflow_id,
            decision="COMPLETE",
            reasoning=f"🏁 Workflow complete — Status: {final_status.upper()}. Invoice: ₹{invoice.get('grand_total', 0):,.2f}"
        )
        await AgentMemory.add_routing_decision(workflow_id, decision)
        await self._emit("routing_decision", decision.model_dump())

        comms_log.append({"from": "orchestrator", "to": "ALL", "type": "decision", "summary": f"COMPLETED — {final_status}"})

        # Persist final order
        await self._save_order(db, workflow_id, final_status, order_payload,
                               comms_log, time.time() - start_time,
                               invoice=invoice, risk_assessment=risk_data,
                               backorder=backorder,
                               state_machine=state_machine,
                               idempotency_key=idempotency_key)

        # Emit workflow completed
        await self._emit("workflow_completed", {
            "workflow_id": workflow_id,
            "final_status": final_status,
        })
        await self._record_event(workflow_id, "workflow_completed",
                                 from_agent="orchestrator",
                                 payload={"final_status": final_status})

        return {
            "status": final_status,
            "workflow_id": workflow_id,
            "invoice": invoice,
            "risk_assessment": risk_data,
            "backorder": backorder,
            "comms_log": comms_log,
            "state_history": state_machine.to_dict()["history"],
        }

    # ═══════════════════════════════════════════════════
    # NATURAL LANGUAGE ENTRY POINT
    # ═══════════════════════════════════════════════════

    async def process_natural_language(self, user_text: str, workflow_id: str) -> dict:
        """
        Process a natural language order request.
        Qwen parses → structured order → process_order()
        """
        await self._emit("qwen_thinking", {
            "workflow_id": workflow_id,
            "stage": "parsing",
            "detail": f"Understanding: \"{user_text}\""
        })

        # Parse with Qwen
        parsed_order = await self.qwen.parse_natural_language(user_text)

        await self._emit("qwen_thinking", {
            "workflow_id": workflow_id,
            "stage": "parsed",
            "detail": f"Identified: Customer={parsed_order.get('customer_id')}, Items={len(parsed_order.get('line_items', []))}"
        })

        # Process the parsed order
        result = await self.process_order(parsed_order, workflow_id)
        result["parsed_from_text"] = user_text
        result["parsed_order"] = parsed_order

        return result

    # ═══════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════

    async def _save_order(self, db, workflow_id, status, order_payload,
                          comms_log, elapsed, invoice=None, risk_assessment=None,
                          backorder=None, state_machine=None, idempotency_key=None):
        """Persist the complete order + workflow to MongoDB."""
        doc = {
            "workflow_id": workflow_id,
            "status": status,
            "order_payload": order_payload,
            "comms_log": comms_log,
            "elapsed_seconds": round(elapsed, 2),
            "created_at": datetime.utcnow().isoformat(),
        }
        if invoice:
            doc["invoice"] = invoice
        if risk_assessment:
            doc["risk_assessment"] = risk_assessment
        if backorder:
            doc["backorder"] = backorder
        if state_machine:
            doc["state_history"] = state_machine.to_dict()["history"]
        if idempotency_key:
            doc["idempotency_key"] = idempotency_key

        await db.orders.update_one(
            {"workflow_id": workflow_id},
            {"$set": doc},
            upsert=True
        )
        await AgentMemory.complete_workflow(workflow_id, status, elapsed)

    async def _create_backorder(self, db, workflow_id, validated_order, inv_payload):
        """Create a backorder record for out-of-stock items."""
        backorder_items = inv_payload.get("backorder_items", [])
        if not backorder_items:
            return None

        backorder_id = f"BO-{workflow_id}"
        backorder = BackorderRecord(
            backorder_id=backorder_id,
            order_id=workflow_id,
            workflow_id=workflow_id,
            customer_id=validated_order.get("customer_id", "UNKNOWN"),
            items=backorder_items,
            status="pending"
        )

        backorder_doc = backorder.model_dump()
        backorder_doc["_id"] = backorder_id
        await db.backorders.update_one(
            {"_id": backorder_id},
            {"$set": backorder_doc},
            upsert=True
        )

        return backorder.model_dump()
