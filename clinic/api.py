"""FastAPI entry that exposes the graph over HTTP."""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from clinic.graph import build_graph

app = FastAPI()
graph = build_graph()


class Turn(BaseModel):
    session_id: str | None = None
    patient_id: str | None = None
    channel: str = "whatsapp"
    message: str


@app.post("/turn")
async def turn(t: Turn):
    session_id = t.session_id or uuid.uuid4().hex
    state = await graph.ainvoke(
        {
            "session_id": session_id,
            "patient_id": t.patient_id,
            "channel": t.channel,
            "user_message": t.message,
            "working_memory": {},
            "response": "",
            "intent": "unknown",
            "done": False,
        },
        config={"configurable": {"thread_id": session_id}},
    )
    return {"session_id": session_id, "response": state["response"]}


@app.get("/healthz")
async def healthz():
    return {"ok": True}
