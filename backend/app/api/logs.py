"""
backend/app/api/logs.py
Server-Sent Events endpoint for real-time log streaming.
GET /api/logs/stream  — streams last 100 lines then tails new entries
GET /api/logs/recent  — returns last N log lines as JSON
"""
from __future__ import annotations

import asyncio
import os
import json
from collections import deque
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from backend.app.dependencies import get_current_user


router = APIRouter()

# In-memory circular buffer — stores last 5000 log entries
_log_buffer: deque = deque(maxlen=5000)
_log_subscribers: list = []   # list of asyncio.Queue for SSE clients

LOG_FILE_PATH = os.environ.get("LOG_FILE", "/app/logs/app.log")


def push_log(entry: dict) -> None:
    """Called by the logging handler to push a new log entry into the buffer."""
    _log_buffer.append(entry)
    # Notify all SSE subscribers
    for q in list(_log_subscribers):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass


# ──────────────────────────────────────────────
# SSE STREAM
# ──────────────────────────────────────────────

async def _log_event_generator(queue: asyncio.Queue, lines: int = 100) -> AsyncGenerator[str, None]:
    """Yields SSE-formatted log entries from the queue."""
    # First: dump the current buffer (last N entries)
    for entry in list(_log_buffer)[-lines:]:
        yield f"data: {json.dumps(entry)}\n\n"

    # Then stream new entries as they arrive
    try:
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(entry)}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield "data: {\"type\":\"heartbeat\"}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _log_subscribers.remove(queue)


@router.get("/stream")
async def stream_logs(token: str = Query(None), lines: int = Query(100)):
    """
    SSE endpoint — streams live log entries to the browser.
    Accepts ?token=<jwt> because the browser EventSource API cannot set
    custom Authorization headers.
    """
    # Validate token manually
    if not token:
        from fastapi.responses import Response
        return Response(status_code=401, content="Missing token")

    try:
        from jose import jwt as _jwt, JWTError
        from backend.app.security import SECRET_KEY, ALGORITHM
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise JWTError("no sub")
    except Exception:
        from fastapi.responses import Response
        return Response(status_code=401, content="Invalid token")

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _log_subscribers.append(queue)

    return StreamingResponse(
        _log_event_generator(queue, lines),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/recent")
async def get_recent_logs(
    n: int = 100,
    level: str = None,
    current_user=Depends(get_current_user),
):
    """
    Return last N log entries as JSON.
    Optional ?level=ERROR to filter by log level.
    """
    entries = list(_log_buffer)
    if level:
        entries = [e for e in entries if e.get("level", "").upper() == level.upper()]
    return {"logs": entries[-n:], "total": len(entries)}
