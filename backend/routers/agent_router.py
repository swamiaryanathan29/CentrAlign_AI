"""
API routers for the agent task system.
Supports both OpenAI GPT-4o (LangGraph) and the built-in Autonomous Engine.
"""
import os
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from backend.agent.task_manager import create_task, get_task, all_tasks, clear_all_tasks, cancel_task
from backend.agent.graph import get_agent, has_openai_key, reset_agent
from backend.agent.autonomous_engine import run_autonomous_worker

router = APIRouter(prefix="/api", tags=["agent"])


class TaskRequest(BaseModel):
    task: str


class ConfigUpdateRequest(BaseModel):
    openai_api_key: str


@router.post("/tasks")
async def submit_task(body: TaskRequest):
    """Submit a new natural-language task for the agent to complete."""
    if not body.task.strip():
        raise HTTPException(status_code=400, detail="Task cannot be empty")

    task = create_task(body.task)
    task.status = "running"

    # Run agent in background with safe runner
    asyncio.create_task(_run_agent(task))

    return {
        "task_id": task.task_id,
        "status": task.status,
        "message": "Task started. Connect to /api/tasks/{task_id}/stream for live updates.",
    }


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    """SSE stream — sends live updates as the agent works."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        async for event in task.event_stream():
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks")
async def list_tasks():
    """List all tasks (most recent first)."""
    tasks = all_tasks()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "original_task": t.original_task,
                "status": t.status,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
                "steps": len(t.step_log),
                "final_summary": t.final_summary,
                "error": t.error,
            }
            for t in reversed(tasks)
        ]
    }


@router.delete("/tasks")
async def delete_all_tasks():
    """Clear all task history."""
    clear_all_tasks()
    return {"status": "ok", "message": "All tasks cleared"}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task_endpoint(task_id: str):
    """Cancel a running task."""
    ok = cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "message": f"Task {task_id} cancelled"}


@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: str):
    """Get full task detail including step log."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.task_id,
        "original_task": task.original_task,
        "status": task.status,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "step_log": task.step_log,
        "final_summary": task.final_summary,
        "error": task.error,
    }


@router.get("/config")
async def get_config():
    """Get AI engine and API key status."""
    active_key = has_openai_key()
    return {
        "has_openai_key": active_key,
        "engine": "OpenAI GPT-4o (LangGraph)" if active_key else "Autonomous Local Engine",
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
    }


@router.post("/config")
async def update_config(body: ConfigUpdateRequest):
    """Configure or update the OpenAI API key."""
    key = body.openai_api_key.strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
        # Persist to .env
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        env_path = os.path.join(root_dir, ".env")
        try:
            with open(env_path, "w") as f:
                f.write(f"OPENAI_API_KEY={key}\n")
        except Exception:
            pass
        reset_agent()
    return {
        "status": "ok",
        "has_openai_key": has_openai_key(),
        "engine": "OpenAI GPT-4o (LangGraph)" if has_openai_key() else "Autonomous Local Engine",
    }


@router.get("/health")
async def health():
    active_key = has_openai_key()
    return {
        "status": "ok",
        "agent": "ready",
        "engine": "OpenAI GPT-4o" if active_key else "Autonomous Local Engine",
    }


# ─────────────────────────────────────────────
# Background agent runner with graceful fallback
# ─────────────────────────────────────────────
async def _run_agent(task):
    """
    Run agent execution with full failure resilience:
    - If OpenAI key is present: runs LangGraph agent.
    - If no key or OpenAI fails: seamlessly runs autonomous worker.
    - Guaranteed to never leave a task hanging in 'running' state.
    """
    try:
        task.push_event({"type": "status", "status": "running", "message": "Agent initialized"})

        # Check if OpenAI is configured
        if has_openai_key():
            agent = get_agent()
            if agent:
                initial_state = {
                    "messages": [HumanMessage(content=task.original_task)],
                    "step_log": [],
                    "task_complete": False,
                    "final_summary": None,
                    "task_id": task.task_id,
                    "original_task": task.original_task,
                }

                # Stream node-by-node from LangGraph
                async for chunk in agent.astream(initial_state, stream_mode="updates"):
                    if task.status == "cancelled":
                        return
                    for node_name, node_output in chunk.items():
                        step_log = node_output.get("step_log", [])
                        if step_log:
                            latest_step = step_log[-1]
                            task.step_log = step_log
                            task.push_event({
                                "type": "step",
                                "node": node_name,
                                "step": latest_step,
                                "total_steps": len(step_log),
                            })

                        if node_output.get("task_complete"):
                            task.final_summary = node_output.get("final_summary", "")

                task.status = "completed"
                task.completed_at = datetime.utcnow().isoformat()
                task.push_event({
                    "type": "done",
                    "status": "completed",
                    "final_summary": task.final_summary,
                    "step_log": task.step_log,
                })
                return

        # If OpenAI is not configured or returned None, use autonomous engine
        await run_autonomous_worker(task)

    except Exception as e:
        # If LangGraph / OpenAI threw an error (e.g. quota, network), fallback to autonomous engine
        try:
            await run_autonomous_worker(task)
        except Exception as inner_e:
            task.status = "failed"
            task.error = f"{str(e)} | Fallback error: {str(inner_e)}"
            task.completed_at = datetime.utcnow().isoformat()
            task.push_event({
                "type": "done",
                "status": "failed",
                "error": task.error,
            })
