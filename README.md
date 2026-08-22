# Multi-Agent Order-to-Cash Orchestrator

<div align="center">

![Multi-Agent O2C](https://img.shields.io/badge/Architecture-Multi--Agent-blueviolet?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python)

**A production-grade multi-agent system that processes sales orders end-to-end using a Shared Memory Bus architecture, 4 specialist AI agents, real-time WebSocket visualization, and MongoDB persistence.**

[Live Demo](#running-locally) · [Architecture](#architecture) · [AWS Deployment](#aws-deployment) · [Demo Script](DEMO_SCRIPT.md)

</div>

---

## What This Builds

A real multi-agent system — not a single monolithic prompt — where each agent owns one discrete step of an order-to-cash workflow:

```
Customer Order → [Orchestrator] → Validate → Inventory+Risk(parallel) → Invoice → Done
```

Every handoff between agents is logged, every decision is reasoned, every order is persisted in MongoDB.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│              (WebSocket live agent visualization)                │
└─────────────────┬───────────────────────────────────────────────┘
                  │  ws://localhost:8000/ws
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                               │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              Qwen Orchestrator                            │  │
│   │   • Intent-based dynamic order planning                   │  │
│   │   • Natural language order parsing                        │  │
│   │   • Dependency-aware agent routing                        │  │
│   └──────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│   ┌───────────────────────▼──────────────────────────────────┐  │
│   │              Shared Memory Bus                            │  │
│   │        (asyncio.Queue — in-process event bus)            │  │
│   └──┬─────────────┬──────────────┬─────────────┬───────────┘  │
│      │             │              │             │               │
│   ┌──▼──┐      ┌───▼───┐    ┌────▼────┐  ┌────▼────┐          │
│   │ [1] │      │  [2]  │    │   [3]   │  │   [4]   │          │
│   │Order│      │Invent.│    │ Invoice │  │Payment  │          │
│   │Valid│      │Checker│    │Generator│  │  Risk   │          │
│   └──┬──┘      └───┬───┘    └────┬────┘  └────┬────┘          │
│      │             │              │             │               │
│   ┌──▼─────────────▼──────────────▼─────────────▼───────────┐  │
│   │           Workflow State Machine                          │  │
│   │  RECEIVED→VALIDATING→VALIDATED→INVENTORY_CHECK→          │  │
│   │  FULFILLED/PARTIAL/INSUFFICIENT→INVOICING→               │  │
│   │  RISK_ASSESSMENT→COMPLETED/BACKORDERED/REJECTED          │  │
│   └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │           Event Manager (WebSocket Bridge)               │  │
│   │    Agent events → WebSocket → React live updates         │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MongoDB Atlas                                   │
│  Collections: inventory · customers · orders · invoices          │
│               backorders · workflows · workflow_events           │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Execution Flow (Dependency-Aware)

```
Step 1 — Sequential (must pass before continuing):
    Order Validator ──► validates customer, products, quantities

Step 2 — Parallel (both run simultaneously):
    Inventory Checker ──┐
                        ├──► results merged by orchestrator
    Payment Risk ───────┘

Step 3 — Conditional (only if stock available):
    Invoice Generator ──► generates GST invoice (CGST 9% + SGST 9%)

Step 4 — Final Orchestrator Decision:
    COMPLETED / PARTIAL_FULFILLED / BACKORDER_CREATED / REJECTED
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Shared Memory Bus** (asyncio.Queue) | Runtime agent coordination — no blocking HTTP calls between agents |
| **Inventory Reservation Model** | `quantity_available` decrements during workflow; committed on success, released on failure |
| **Dependency-Aware Routing** | Steps 1→2→3 are ordered; Step 2 runs inventory+risk in parallel |
| **Deterministic fallback** | All business logic works without Ollama — LLM adds narrative only |
| **12 Intent Types** | Qwen reads live inventory and builds order plans dynamically |

---

## Features

- **4 Long-Lived Specialist Agents** — each runs as an async worker subscribed to the bus
- **Shared Memory Bus** — in-process `asyncio.Queue` for zero-latency agent communication
- **Workflow State Machine** — explicit stage transitions, no ambiguous state
- **12 Dynamic Order Intents** — Qwen reads live MongoDB inventory and picks products/quantities
- **Natural Language Orders** — type "Order 50 Samsung phones for Croma" and Qwen parses it
- **Real-Time WebSocket Pipeline** — watch all 4 agents execute live in the browser
- **Indian GST Invoices** — CGST 9% + SGST 9% = 18% GST with ₹ formatting
- **Payment Risk Assessment** — credit limit, payment history, order value scoring
- **Backorder Management** — partial fulfillment creates invoice for available + backorder for shortfall
- **Order History** — every order persisted in MongoDB with full audit trail
- **PDF Export** — download full invoice + agent reports + risk assessment as PDF

---

## Exception Paths Handled

| Scenario | What Happens |
|----------|-------------|
| **Invalid customer** | Validator rejects immediately; no other agents run |
| **Zero quantity / bad data** | Validator catches, returns structured error |
| **Out of stock** | Inventory agent returns `insufficient`; backorder created |
| **Partial stock** | Invoice for available items + backorder for shortfall |
| **High payment risk** | Risk agent flags, sets `requires_approval = true` |
| **Credit limit exceeded** | Risk score increases, flagged in risk assessment |
| **Agent timeout** | Bus message expires, orchestrator handles gracefully |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI + Uvicorn |
| **Agent Bus** | asyncio.Queue (Shared Memory Bus) |
| **Database** | MongoDB Atlas (Motor async driver) |
| **LLM** | Ollama + Qwen 2.5:3B (optional — falls back gracefully) |
| **Frontend** | React 19 + Vite |
| **Real-time** | WebSocket (native FastAPI) |
| **Styling** | Vanilla CSS (dark mode, glassmorphism) |
| **PDF** | jsPDF + jspdf-autotable |
| **Containerization** | Docker + AWS ECR |

---

## Project Structure

```
order-to-cash-orchestrator/
├── backend/
│   ├── agents/
│   │   ├── base_agent.py          # Long-lived async bus worker base class
│   │   ├── order_validator.py     # Step 1: validates customer + line items
│   │   ├── inventory_checker.py   # Step 2a: stock check + reservation
│   │   ├── payment_risk.py        # Step 2b: credit + risk scoring
│   │   └── invoice_generator.py   # Step 3: GST invoice generation
│   ├── memory/
│   │   ├── shared_memory_bus.py   # asyncio.Queue event bus
│   │   └── workflow_state.py      # State machine transitions
│   ├── events/
│   │   └── event_manager.py       # WebSocket bridge (bus → frontend)
│   ├── orchestration/
│   │   ├── qwen_orchestrator.py   # LLM reasoning + routing decisions
│   │   ├── routing.py             # Dependency-aware execution pipeline
│   │   └── order_planner.py       # Dynamic intent-based order planning
│   ├── models/
│   │   ├── messages.py            # AgentMessage, RoutingDecision models
│   │   ├── order.py               # ValidatedOrder, Invoice models
│   │   └── inventory.py           # StockCheckResult, ProcessedLineItem
│   ├── config.py                  # Settings (MongoDB URI, Ollama URL)
│   ├── database.py                # Motor async client + indexes
│   ├── orchestrator.py            # Main workflow orchestration logic
│   ├── main.py                    # FastAPI app + all endpoints
│   ├── seed_data.py               # 6 products + 6 customers seed script
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Full React app (WebSocket, intents, history)
│   │   └── App.css                # Dark mode UI styles
│   ├── package.json
│   └── index.html
├── DEMO_SCRIPT.md                 # 5-minute demo walkthrough
├── .gitignore
└── README.md
```

---

## Setup & Running Locally

### Prerequisites

1. **Python 3.11+**
2. **Node.js 18+ & npm**
3. **MongoDB Atlas** free M0 cluster (or local MongoDB)
4. **Ollama** (optional — for AI narrative summaries)

### Step 1 — Clone & Configure

```bash
git clone https://github.com/bhavanisankardavuluri10/order-to-cash-orchestrator.git
cd order-to-cash-orchestrator
```

Create `backend/.env`:
```env
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net
OLLAMA_URL=http://localhost:11434
MODEL_NAME=qwen2.5:3b
```

### Step 2 — Backend Setup

```bash
cd backend
pip install -r requirements.txt

# Seed MongoDB with 6 products (500 units each) + 6 customers
python seed_data.py

# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

Expected output:
```
===========================================
  [*] Multi-Agent O2C Orchestrator v2.0
  [+] Shared Memory Bus: ACTIVE
  [+] Event Manager: ACTIVE
  [+] Agents: 4 specialists ready
  [+] Qwen Orchestrator: READY
===========================================
```

### Step 3 — Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

### Step 4 — Optional: Ollama (AI Summaries)

```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5:3b
ollama serve
```

> Without Ollama, the system works fully with deterministic business logic. Ollama only adds narrative text summaries.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/orders` | Submit a structured order |
| `POST` | `/api/orders/intent` | Dynamic intent-based order (Qwen plans from live inventory) |
| `POST` | `/api/orders/natural` | Natural language order parsing |
| `GET` | `/api/orders/intents` | List all 12 intent types |
| `GET` | `/api/orders` | Order history (MongoDB) |
| `GET` | `/api/inventory` | Live inventory state |
| `GET` | `/api/customers` | All customers |
| `POST` | `/api/reset-inventory` | Reset to seed state |
| `GET` | `/api/system-status` | Bus + agent health check |
| `GET` | `/docs` | Swagger API documentation |
| `WS` | `/ws` | WebSocket for live agent events |

### Intent-Based Order Example

```bash
curl -X POST http://localhost:8000/api/orders/intent \
  -H "Content-Type: application/json" \
  -d '{"intent": "bulk_order", "customer_id": "CUST-101"}'
```

Qwen reads live inventory → picks 4 products → 200–400 units each → full workflow runs.

### Natural Language Example

```bash
curl -X POST http://localhost:8000/api/orders/natural \
  -H "Content-Type: application/json" \
  -d '{"text": "Order 50 Samsung phones for Croma with express shipping"}'
```

---

## WebSocket Event Stream

The frontend receives these real-time events:

```json
{ "type": "workflow_started",  "data": { "workflow_id": "WF-..." } }
{ "type": "qwen_thinking",     "data": { "stage": "planning", "detail": "..." } }
{ "type": "agent_started",     "data": { "agent": "order_validator" } }
{ "type": "agent_completed",   "data": { "agent": "order_validator", "response": {...} } }
{ "type": "routing_decision",  "data": { "decision": "PROCEED_PARALLEL", "reasoning": "..." } }
{ "type": "workflow_completed","data": { "final_status": "completed" } }
```

---

## Inventory Products (Seeded)

| SKU | Product | Price | Stock | Category |
|-----|---------|-------|-------|----------|
| SKU-1001 | boAt Airdopes 141 (Wireless Earbuds) | ₹1,299 | 500 | Electronics |
| SKU-1002 | Samsung Galaxy M14 5G (128GB) | ₹13,490 | 500 | Smartphones |
| SKU-1003 | Noise ColorFit Pro 4 Smart Watch | ₹3,999 | 500 | Wearables |
| SKU-1004 | Ambrane 20000mAh Power Bank | ₹999 | 500 | Accessories |
| SKU-1005 | HP Victus 15 Gaming Laptop (i5, RTX 3050) | ₹62,990 | 500 | Laptops |
| SKU-1006 | Levi's Men's 511 Slim Fit Jeans | ₹2,499 | 500 | Fashion |

## Customers (Seeded)

| ID | Customer | Credit Limit | Tier |
|----|----------|-------------|------|
| CUST-101 | Reliance Digital Stores | ₹5,00,000 | Premium |
| CUST-102 | Croma Electronics | ₹3,00,000 | Medium |
| CUST-103 | Poorvika Mobiles | ₹2,00,000 | Standard |
| CUST-104 | Vijay Sales | ₹4,00,000 | Premium |
| CUST-105 | Sangeetha Mobiles | ₹1,50,000 | Standard |
| CUST-106 | E-Kart Wholesale | ₹7,50,000 | Enterprise |

---

## AWS Deployment

### Architecture on AWS

```
CloudFront ──► S3 (React frontend)
     │
     ▼
Application Load Balancer
     │
     ▼
ECS Fargate (FastAPI backend) ──► MongoDB Atlas (existing)
     │
     └──► EC2 (Ollama/Qwen — optional)
```

### Quick Deploy

```bash
# 1. Build and push to ECR
cd backend
docker build -t o2c-backend .
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.ap-south-1.amazonaws.com
docker tag o2c-backend:latest <ECR_URI>:latest
docker push <ECR_URI>:latest

# 2. Build frontend
cd ../frontend
npm run build
aws s3 sync dist/ s3://<YOUR-BUCKET> --delete

# 3. Deploy ECS service (see full guide in aws_deployment_guide.md)
aws ecs create-service --cluster o2c-cluster --service-name o2c-backend ...
```

**Estimated cost: ~$33/month** (ECS Fargate + ALB + S3 + CloudFront, no Ollama)

---

## What Makes This a Genuine Multi-Agent System

Per the Supervity FDE evaluation criteria:

| Criterion | Implementation |
|-----------|---------------|
| **Orchestrator-to-specialist delegation** | Orchestrator sends messages via Shared Memory Bus; agents subscribe and respond independently |
| **Each agent owns one discrete step** | Validator → Inventory/Risk (parallel) → Invoice — no agent does two jobs |
| **Genuine multi-agent vs single prompt** | 4 separate Python classes, each with its own bus subscription, processing logic, and response format |
| **Exception path handling** | Invalid customer, zero stock, partial stock, credit exceeded — each routes differently |
| **Agent-to-agent communication logging** | Every handoff logged in `comms_log` + MongoDB `workflow_events` collection |
| **Parallel execution** | Inventory + Risk run simultaneously via `asyncio.gather` |

---

## License

MIT — Built for the Supervity Forward Deployed Engineer evaluation.
