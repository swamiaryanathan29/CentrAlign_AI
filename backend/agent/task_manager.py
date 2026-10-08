"""
Task manager — stores and manages running/completed tasks.
Each task has a unique ID and streams progress via Server-Sent Events.
"""
import uuid
import asyncio
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class Task:
    task_id: str
    original_task: str
    status: str = "pending"   # pending | running | completed | failed | cancelled
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    step_log: list = field(default_factory=list)
    final_summary: Optional[str] = None
    error: Optional[str] = None
    # SSE queue for streaming
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    def push_event(self, event: dict):
        """Non-blocking push to SSE queue."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def event_stream(self):
        """Async generator for SSE streaming."""
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                if event.get("type") == "done":
                    yield event
                    break
                yield event
            except asyncio.TimeoutError:
                yield {"type": "heartbeat"}


# In-memory task store
_tasks: dict[str, Task] = {}

def create_task(task_text: str) -> Task:
    task_id = str(uuid.uuid4())[:8]
    task = Task(task_id=task_id, original_task=task_text)
    _tasks[task_id] = task
    return task

def get_task(task_id: str) -> Optional[Task]:
    return _tasks.get(task_id)

def all_tasks() -> list[Task]:
    return list(_tasks.values())

def clear_all_tasks() -> None:
    _tasks.clear()

def cancel_task(task_id: str) -> bool:
    t = _tasks.get(task_id)
    if not t:
        return False
    if t.status == "running":
        t.status = "cancelled"
        t.completed_at = datetime.utcnow().isoformat()
        t.push_event({
            "type": "done",
            "status": "cancelled",
            "error": "Task was manually cancelled by user.",
        })
    return True
