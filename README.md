# CentrAlign AI Worker
### Autonomous AI Task Engine — Intern Submission

> A working prototype of an autonomous AI worker that takes a natural-language task and completes it end-to-end: reading invoice files, extracting structured data, entering it into a simulated ERP system, verifying the result, and streaming every step live to a web UI.

---

## Demo

**Live flow:** *"Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our ERP system, and confirm once it is done."*

The agent:
1. Lists available invoices
2. Searches for Acme Corp's invoice
3. Reads the full invoice file
4. Checks the ERP for duplicates
5. Creates a payable record in the ERP
6. Verifies the record was saved correctly
7. Returns a concise summary with the record ID, amount, and due date

Every step streams live to the browser via Server-Sent Events.

---

## Quickstart

### 1. Clone & enter the project
```bash
git clone <your-repo-url>
cd CentrAlign_AI
```

### 2. Install Python dependencies
```bash
pip3 install --user fastapi uvicorn langgraph langchain langchain-openai openai python-multipart httpx aiofiles pydantic websockets python-dotenv beautifulsoup4 requests
```

### 3. Set your OpenAI API key
```bash
cp .env.example .env
# Edit .env and set: OPENAI_API_KEY=sk-...
```

### 4. Start the system
```bash
bash start.sh
```

This launches:
- **Agent API** → `http://localhost:8000` (frontend + REST API)
- **ERP Simulator** → `http://localhost:8001` (mock accounts payable system)

### 5. Open the UI
Navigate to **http://localhost:8000** in your browser.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Browser / UI                        │
│  (HTML + CSS + JS, SSE streaming, task history)       │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────▼──────────────────────────────┐
│              Agent API  (FastAPI, port 8000)          │
│                                                       │
│  POST /api/tasks  →  creates task, runs agent async   │
│  GET  /api/tasks/:id/stream  →  SSE event stream      │
│  GET  /api/tasks  →  task history                     │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│         LangGraph Agent  (Plan → Act → Observe)       │
│                                                       │
│  ┌──────────┐    ┌──────────────┐    ┌────────────┐  │
│  │ plan_and │───▶│ execute_tool │───▶│   route    │  │
│  │  _act    │    │   (tools)    │    │ (continue/ │  │
│  │  (LLM)  │◀───│              │    │  stop)     │  │
│  └──────────┘    └──────────────┘    └────────────┘  │
│                                                       │
│  GPT-4o with function calling + system prompt         │
└───────────────────────┬──────────────────────────────┘
                        │
        ┌───────────────┼──────────────────────┐
        │               │                      │
┌───────▼──────┐ ┌──────▼──────┐  ┌───────────▼────────┐
│  File Tools  │ │  ERP Tools  │  │  Search/Find Tools │
│              │ │             │  │                    │
│ list_invoices│ │ enter_invoice│  │ find_by_company    │
│ read_invoice │ │ verify_entry │  │ list_payables      │
└──────────────┘ └──────┬──────┘  └────────────────────┘
                        │ HTTP
┌───────────────────────▼──────────────────────────────┐
│         ERP Simulator  (FastAPI, port 8001)           │
│                                                       │
│  In-memory accounts payable system                   │
│  POST /payables  →  create record (idempotent)        │
│  GET  /payables  →  list all records                  │
│  GET  /payables/:id  →  verify single record          │
│  PATCH /payables/:id  →  update status                │
│  GET  /audit-log  →  full audit trail                 │
└──────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. LangGraph for the Agent Loop
I used **LangGraph** (not raw LangChain) because it gives an explicit, stateful graph with named nodes. This makes the Plan → Act → Observe loop inspectable, debuggable, and easy to extend. Each edge is a condition that can be modified without touching other nodes.

### 2. OpenAI Function Calling (not ReAct prompting)
Rather than parsing tool calls from free text (ReAct style), I use OpenAI's native function-calling API. This is significantly more reliable — the model always returns structured JSON for tool calls, never hallucinates tool names, and handles multi-argument calls correctly.

### 3. Server-Sent Events (not WebSockets)
SSE is simpler and perfectly suited for unidirectional agent → browser streaming. It works through HTTP/1.1, reconnects automatically, and needs zero client-side libraries. WebSockets add bidirectional complexity that isn't needed here.

### 4. Idempotent ERP writes
The ERP `POST /payables` endpoint checks for duplicate `invoice_id` before inserting. If the agent retries (e.g. after an error), it won't create duplicate records. This is a critical reliability property.

### 5. Tool docstrings as the agent's contract
Each tool function has a detailed docstring. LangGraph automatically sends these to the LLM as the tool's description. This is the *only* place where tool behavior is documented — no separate prompt engineering needed. Changing a docstring directly changes what the agent knows about that tool.

### 6. Simulated ERP — real HTTP, not mocked
The ERP is a real FastAPI app with real HTTP endpoints. The agent's ERP tools make actual `httpx` calls — not mocked responses. This means error handling (404s, 422s, timeouts) is real and the agent can observe and recover from actual failures.

---

## Autonomy Capabilities

| Capability | Implementation |
|---|---|
| Understand goal | GPT-4o system prompt emphasizes goal understanding, not step following |
| Break into actions | LangGraph loop — LLM decides next tool at each step |
| Use tools | 7 tools: file listing, reading, ERP CRUD, search, verify |
| Observe results | Tool output is fed back as a ToolMessage into the conversation |
| Decide next step | LLM re-plans after every tool result |
| Remember context | Full message history is preserved in AgentState |
| Detect failures | Tool errors return structured JSON with `"error"` key |
| Retry / alternative | LLM observes the error and decides to retry or try another tool |
| Verify outcome | `verify_erp_entry` tool explicitly checks the saved record |
| Ask for clarification | System prompt instructs the agent to ask when uncertain |
| Return evidence | Final summary includes record ID, amount, due date, status |

---

## Demo Tasks to Try

```
Find the latest invoice from Acme Corp, extract the amount and due date,
enter it into our ERP system, and confirm once it is done.

Find all unpaid invoices, list their amounts and due dates, and enter
each one into the ERP system.

Find the invoice from TechSupplies Ltd and enter it into the ERP system,
then verify the entry was saved correctly.
```

---

## Project Structure

```
CentrAlign_AI/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── agent/
│   │   ├── graph.py             # LangGraph agent definition
│   │   └── task_manager.py      # Task state + SSE queue
│   ├── tools/
│   │   └── invoice_tools.py     # All 7 agent tools
│   ├── erp_sim/
│   │   ├── erp_app.py           # Simulated ERP system
│   │   └── run_erp.py           # ERP standalone runner
│   └── routers/
│       └── agent_router.py      # API endpoints + bg runner
├── frontend/
│   ├── index.html               # Single-page UI
│   ├── style.css                # Dark-mode premium CSS
│   └── app.js                   # SSE client + UI logic
├── data/
│   └── invoices/
│       ├── invoice_001.json     # Acme Corp (TechSupplies, $14,500)
│       └── invoice_002.json     # GlobalTech / OfficeWorld ($3,275)
├── start.sh                     # One-command startup
├── .env.example                 # API key template
└── README.md
```

---

## Known Limitations

1. **In-memory storage only** — ERP records are lost on restart. A real system would use PostgreSQL.
2. **No authentication** — API endpoints are open. Production would require JWT/OAuth.
3. **Single-user** — task state is per-process. Multi-user needs a proper database + message queue.
4. **Invoice data is local JSON** — a real system would read from email, S3, SharePoint, etc.
5. **No file upload UI** — invoices are pre-loaded; users can't upload new ones through the browser.
6. **GPT-4o cost** — each task uses ~3–6 LLM calls. A production system would cache and batch.

---

## What I'd Build Next

1. **PDF/email invoice ingestion** — accept PDF uploads, extract text with `pdfplumber`, parse with LLM.
2. **Approval workflow** — human-in-the-loop step: agent flags high-value invoices for manager approval before entering.
3. **Multi-step retry with exponential backoff** — retry failed tool calls with increasing delays.
4. **Persistent storage** — PostgreSQL for tasks and ERP records; Redis for SSE pub/sub across workers.
5. **Real ERP integration** — Xero/QuickBooks API instead of the simulator.
6. **Evaluation harness** — automated tests that verify agent completes known tasks correctly.
7. **Browser-use tool** — add Playwright so the agent can interact with actual web ERP UIs.
8. **Task queuing** — Celery + Redis for handling many concurrent tasks.

---

## Assumptions

- The demo focuses on invoice-to-ERP workflow as the primary use case.
- Invoices are provided as local JSON files (simulating a document storage system).
- The ERP system is a simplified accounts payable module (a real ERP has hundreds of modules).
- The OpenAI API is available and the user provides their own API key.
- Python 3.9+ is installed on the target machine.

---

## Technologies Used

| Category | Technology |
|---|---|
| LLM | OpenAI GPT-4o (function calling) |
| Agent Framework | LangGraph 0.6, LangChain 0.3 |
| Backend API | FastAPI + Uvicorn |
| Streaming | Server-Sent Events (SSE) |
| HTTP Client | httpx (async) |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| ERP Simulator | FastAPI (in-memory) |
| Config | python-dotenv |

---

*Built for CentrAlign AI Intern Application — October 2024*
