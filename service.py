#!/usr/bin/env python3
"""The public contract: GET /health, POST /tasks, GET /tasks/{id}, plus GET /stats for monitoring.

POST /tasks only records the task and starts a thread, so it answers well under the 2 s limit.
"""
from __future__ import annotations

import hmac
import os
import threading
import uuid
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from screen_agent import run_task
from store import Store


class Desktop(BaseModel):
    url: str
    password: str

    def __repr__(self) -> str:  # The password must not reach a log through a traceback or a print.
        return "Desktop(...)"


class TaskRequest(BaseModel):
    tarea: str
    escritorio: Desktop


def create_app(store: Optional[Store] = None, runner: Any = run_task) -> FastAPI:
    app = FastAPI(title="Agente por pantalla", docs_url=None, redoc_url=None, openapi_url=None)
    store = store or Store()

    def require_token(authorization: str = Header(default="")) -> None:
        expected = os.environ.get("FRONTIER_TEAM_TOKEN", "")
        if not expected or not hmac.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/health")
    def health() -> Dict[str, bool]:
        return {"ok": True}

    @app.post("/tasks", dependencies=[Depends(require_token)])
    def create_task(request: TaskRequest) -> Dict[str, str]:
        if not request.escritorio.url.startswith(("wss://", "ws://")):
            raise HTTPException(status_code=422, detail="escritorio.url must be a websocket URL")
        task_id = uuid.uuid4().hex
        store.create_task(task_id, request.tarea)
        secrets = [os.environ.get("FRONTIER_TEAM_TOKEN", ""), os.environ.get("OPENROUTER_API_KEY", "")]
        threading.Thread(target=runner, daemon=True,
                         args=(task_id, request.tarea, request.escritorio.url, request.escritorio.password, store),
                         kwargs={"secrets": secrets}).start()
        return {"task_id": task_id}

    @app.get("/tasks/{task_id}", dependencies=[Depends(require_token)])
    def get_task(task_id: str) -> Dict[str, str]:
        task = store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Unknown task")
        return {"estado": task["estado"], "resumen": task["resumen"] or ""}

    @app.get("/stats", dependencies=[Depends(require_token)])
    def stats() -> Dict[str, Any]:
        return store.stats()

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
