# 5-Minute Demo Script — Multi-Agent O2C Orchestrator

> **Use this for your video walkthrough. Each section has a time target and exact talking points.**

---

## Pre-Demo Setup (Do this before recording)

```bash
# Terminal 1 — Backend
cd backend
python seed_data.py          # reset to clean state
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open browser to **http://localhost:5173**

---

## [0:00 – 0:30] — Open: What Is This?

> *Show the browser with the app open. Point to the pipeline strip at the top.*

**Say:**
> "This is a multi-agent Order-to-Cash orchestrator. When a sales order comes in, it goes through four specialist AI agents — Order Validator, Inventory Checker, Invoice Generator, and Payment Risk — all coordinated by an orchestrator using a Shared Memory Bus.
>
> This is not a single prompt asking GPT to do everything. These are four separate agents, each owning one step. Let me show you how it works live."

---

## [0:30 – 1:30] — The Architecture (30 seconds)

> *Scroll down to show the Live Inventory sidebar. Point to the agent pipeline at the top of the main area.*

**Say:**
> "Here's the pipeline. The Orchestrator sits at the left. It sends tasks to agents via an in-process Shared Memory Bus — that's an asyncio Queue, not HTTP calls between microservices. Agents subscribe to the bus at startup and run as long-lived workers.
>
> The orchestrator knows the dependency order — first validate, then check inventory and assess payment risk in parallel, then generate the invoice. The state machine tracks every transition.
>
> Every event is streamed to this React frontend in real-time via WebSocket."

---

## [1:30 – 2:30] — Demo 1: Happy Path (Dynamic Intent)

> *In the sidebar:*
> - *Select customer: "Reliance Digital Stores (CUST-101)"*
> - *Click the "Large Order" intent card (🏭)*
> - *Click "Submit via Orchestrator"*

**Say:**
> "Instead of hardcoded orders, the system uses intent-based planning. I'll pick 'Large Order' — the Qwen Orchestrator will read the live inventory from MongoDB and decide which 3 products to order and how many.
>
> Watch the pipeline — agents light up in real-time."

> *Wait for completion (~15 seconds). Point to:*
> - *Green checkmarks on all 4 agents*
> - *The orchestrator messages: "Order valid. Starting Inventory Check + Risk in parallel"*
> - *The plan reveal box showing which products Qwen chose*
> - *The invoice with ₹ amount and CGST/SGST breakdown*

**Say:**
> "Done. The system picked 3 products from live stock, validated the order, checked inventory and risk simultaneously, generated a GST invoice with CGST and SGST breakdown. All 4 agents communicated through the bus — you can see the handoffs in the orchestrator decision messages."

---

## [2:30 – 3:15] — Demo 2: Exception Path (Out of Stock Backorder)

> *Keep the same customer. Click the "High Value Order" intent card (🏆). Submit.*

> *(If not triggering backorder naturally, type in Natural Language box:)*
> `"Order 600 units of each product for Reliance Digital with standard shipping"`

**Say:**
> "Now let me trigger the exception path — ordering more than available stock.
>
> Watch what the Inventory Checker returns..."

> *Point to the inventory checker card — it will show `PARTIAL` or `INSUFFICIENT`*
> *Point to the orchestrator message: "Insufficient inventory... Creating backorder"*

**Say:**
> "The Inventory Checker detected insufficient stock. The orchestrator routed to backorder creation — the Invoice Generator was skipped entirely because there's nothing to invoice. A backorder document was created in MongoDB.
>
> This is the exception path the requirements asked for — and you can see each agent's individual decision contributing to the final outcome."

---

## [3:15 – 3:45] — Demo 3: Natural Language Order

> *Type in the Natural Language box:*
> `"Order 30 Samsung Galaxy phones for Croma with express shipping"`

> *Click "Submit via Qwen AI"*

**Say:**
> "The system also accepts natural language. Qwen parses this into a structured order — customer ID, product SKU, quantity, shipping priority — then the same 4-agent pipeline runs.
>
> This demonstrates the LLM layer. Without Ollama running locally, it falls back to deterministic parsing. With Ollama, it generates AI narrative summaries on the invoice and risk assessment."

---

## [3:45 – 4:15] — Order History & Persistence

> *Click the "Order History" tab*

**Say:**
> "Every order is persisted in MongoDB with the full workflow state — the comms log showing every agent handoff, the state machine transitions, invoice data, and risk score.
>
> This is the audit trail. You can see completed orders, backorders, and rejections — all timestamped and stored in the `orders` collection."

---

## [4:15 – 4:45] — Code Architecture (30 seconds)

> *Switch to your code editor. Show `backend/memory/shared_memory_bus.py` briefly*

**Say:**
> "The core of this system is the Shared Memory Bus — an asyncio Queue that agents subscribe to at startup. When the orchestrator publishes a message, the target agent's queue receives it, processes it, and publishes a response.
>
> Each agent — Validator, Inventory, Invoice, Risk — is a separate Python class with its own `process()` method. They don't call each other directly. The orchestrator mediates every handoff.
>
> The orchestration layer also handles the routing logic — whether to proceed, backorder, or reject — all as explicit code decisions, not LLM guesses."

> *Show `backend/orchestration/order_planner.py` briefly*

**Say:**
> "And the order planner — 12 intent types. When you pick 'Bulk Order', it queries MongoDB for live inventory, picks 4 products randomly, assigns quantities in the 200–400 range. Every run is different. The system handles every outcome correctly regardless of what Qwen picks."

---

## [4:45 – 5:00] — Close

> *Switch back to browser. Show the pipeline one more time.*

**Say:**
> "To summarize what this demonstrates:
>
> - A genuine multi-agent system — one orchestrator, four specialists, each with one job
> - Agent communication via Shared Memory Bus, not API calls
> - Real exception handling — not just an error message, but a full backorder workflow
> - All handoffs are logged, all state transitions are explicit
> - MongoDB persistence, real-time WebSocket, PDF invoice export
>
> The entire codebase is at github.com/bhavanisankardavuluri10/order-to-cash-orchestrator.
> Thank you."

---

## Key Points to Emphasize (If Asked)

**"Why Shared Memory Bus instead of HTTP between agents?"**
> "HTTP between agents adds latency and failure points. An asyncio Queue is synchronous within the process — zero network overhead, instant delivery, and the orchestrator controls the order of execution."

**"How is this different from a single LLM prompt?"**
> "Each agent is a separate Python class with its own business logic. The Inventory Checker queries MongoDB and applies reservation logic. The Risk Agent calculates a score from credit history, order value, and payment records. None of this is 'ask LLM to figure it out' — the LLM only adds narrative text on top of deterministic results."

**"What happens if Ollama isn't running?"**
> "The system falls back to deterministic mode automatically. Every agent returns structured data. The only thing missing is the AI narrative summary on the invoice — all business logic still works."

**"How would you scale this?"**
> "Each agent class can be extracted into its own microservice. The Shared Memory Bus becomes a message broker like Redis Streams or AWS SQS. The orchestrator becomes a Step Functions state machine. The architecture is designed to make that migration straightforward."

---

## Backup Commands (If Something Fails Live)

```bash
# Reset inventory to 500 units each
curl -X POST http://localhost:8000/api/reset-inventory

# Check system health
curl http://localhost:8000/api/system-status

# Manually test happy path
curl -X POST http://localhost:8000/api/orders/intent \
  -H "Content-Type: application/json" \
  -d '{"intent": "medium_order", "customer_id": "CUST-101"}'

# Check what's in MongoDB
curl http://localhost:8000/api/orders
```
