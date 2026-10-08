"""
Core LangGraph agent — the autonomous task execution engine.

Architecture:
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  PLAN    │────▶│  ACT     │────▶│ OBSERVE  │
  │ (LLM)   │     │ (tools)  │     │ (result) │
  └──────────┘     └──────────┘     └──────────┘
       ▲                                  │
       └──────────────────────────────────┘
                   (loop until done)

The agent uses OpenAI function calling. Each node in the graph:
  - plan_and_act: LLM decides next tool call (or finishes)
  - execute_tool: runs the chosen tool, captures result
  - route: decides whether to continue looping or stop

State carries:
  - messages: full conversation + tool results
  - step_log: human-readable log of each action taken
  - task_complete: boolean
  - final_summary: agent's closing statement
"""
import json
import os
from typing import Annotated, Sequence, TypedDict, Optional
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from backend.tools.invoice_tools import ALL_TOOLS

# ─────────────────────────────────────────────
# Agent State
# ─────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    step_log: list[dict]          # [{step, action, result, timestamp}]
    task_complete: bool
    final_summary: Optional[str]
    task_id: str
    original_task: str

# ─────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous AI Task Worker for a company's finance operations.

Your job is to autonomously complete tasks involving invoices and the company's ERP (accounting) system.
You have access to tools to read invoice files, search for invoices, and enter data into the ERP system.

## Your Operating Principles:
1. **Understand the goal** — don't just follow instructions literally; understand what the user actually wants.
2. **Plan before acting** — think through the steps needed before starting.
3. **Verify your work** — after entering data into the ERP, always verify the entry was saved correctly.
4. **Handle errors gracefully** — if a tool fails, try an alternative approach before giving up.
5. **Be concise in tool calls** — don't call tools unnecessarily.
6. **Never fabricate data** — only use information you actually read from files or received from tools.

## Workflow for invoice tasks:
1. Understand what company/invoice the user is asking about.
2. Discover available invoices (list or search).
3. Read the specific invoice to extract all required data.
4. Check the ERP to see if this invoice was already entered (avoid duplicates).
5. Enter the invoice into the ERP with all required fields.
6. Verify the ERP entry is correct.
7. Report back with a concise summary including: invoice ID, amount, due date, ERP record ID, and status.

## Error Handling:
- If a file is not found, list available invoices and try to find the right one.
- If ERP entry fails, check if a duplicate already exists and report that.
- If verification fails, retry once before reporting failure.

Always end with a clear summary of what was accomplished and evidence (record IDs, amounts, dates).
"""

# ─────────────────────────────────────────────
# Build the graph
# ─────────────────────────────────────────────
def has_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and not key.startswith("sk-your-key"))


def build_agent(stream_callback=None):
    """Build and return a compiled LangGraph agent, or None if no valid key."""
    if not has_openai_key():
        return None

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        ).bind_tools(ALL_TOOLS)

        tool_node = ToolNode(ALL_TOOLS)

        def plan_and_act(state: AgentState, config: RunnableConfig):
            """LLM node — decides what to do next."""
            messages = state["messages"]
            # Inject system prompt if first call
            if not any(isinstance(m, SystemMessage) for m in messages):
                messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

            response = llm.invoke(messages, config)

            # Log the thinking step
            step_log = list(state.get("step_log", []))
            if response.tool_calls:
                for tc in response.tool_calls:
                    step_log.append({
                        "step": len(step_log) + 1,
                        "type": "tool_call",
                        "action": tc["name"],
                        "args": tc["args"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "result": None,
                    })
            else:
                step_log.append({
                    "step": len(step_log) + 1,
                    "type": "final_answer",
                    "action": "complete",
                    "content": response.content,
                    "timestamp": datetime.utcnow().isoformat(),
                })

            return {
                "messages": [response],
                "step_log": step_log,
                "task_complete": not bool(response.tool_calls),
                "final_summary": response.content if not response.tool_calls else state.get("final_summary"),
            }

        def execute_tools(state: AgentState, config: RunnableConfig):
            """Tool execution node — runs the tool chosen by the LLM."""
            result = tool_node.invoke(state, config)
            # Annotate last tool result into step log
            step_log = list(state.get("step_log", []))
            tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            for i, tm in enumerate(tool_messages):
                # Find matching pending step
                for entry in reversed(step_log):
                    if entry.get("result") is None and entry.get("type") == "tool_call":
                        entry["result"] = tm.content[:500]  # truncate for display
                        break
            return {"messages": result["messages"], "step_log": step_log}

        def should_continue(state: AgentState):
            """Router — loop back if tools were called, stop if done."""
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "execute_tools"
            return END

        # ── Build graph ──
        graph = StateGraph(AgentState)
        graph.add_node("plan_and_act", plan_and_act)
        graph.add_node("execute_tools", execute_tools)

        graph.set_entry_point("plan_and_act")
        graph.add_conditional_edges("plan_and_act", should_continue, {
            "execute_tools": "execute_tools",
            END: END,
        })
        graph.add_edge("execute_tools", "plan_and_act")

        return graph.compile()
    except Exception as e:
        print(f"Error compiling LangGraph agent: {e}")
        return None


# Singleton compiled agent
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent

def reset_agent():
    global _agent
    _agent = None
