"""LangGraph orchestrator for clinic agents."""
from __future__ import annotations

import os
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver


class ClinicState(TypedDict):
    session_id: str
    patient_id: str | None
    channel: Literal["voice", "whatsapp", "web"]
    user_message: str
    intent: str
    working_memory: dict
    response: str
    done: bool


def classify_intent(msg: str) -> str:
    m = msg.lower()
    if any(w in m for w in ("agendar", "cita", "cuando", "disponibilidad")):
        return "book"
    if any(w in m for w in ("reagendar", "cambiar cita", "mover")):
        return "reschedule"
    if "cancelar" in m:
        return "cancel"
    if any(w in m for w in ("confirmar", "sí asistiré", "ahí estaré")):
        return "confirm"
    if any(w in m for w in ("reseña", "review", "opinión")):
        return "review"
    return "unknown"


def router_node(state: ClinicState) -> ClinicState:
    state["intent"] = classify_intent(state["user_message"])
    return state


def booking_node(state: ClinicState) -> ClinicState:
    # Bind booking_agent from clinic.agents at runtime; stub here.
    state["response"] = "Claro, te ayudo a agendar. ¿Qué día prefieres?"
    state["done"] = True
    return state


def reminder_node(state: ClinicState) -> ClinicState:
    state["response"] = "¡Perfecto, quedó confirmada tu cita!"
    state["done"] = True
    return state


def review_node(state: ClinicState) -> ClinicState:
    state["response"] = "Gracias por compartir. ¿Podrías dejar una reseña en Google?"
    state["done"] = True
    return state


def fallback_node(state: ClinicState) -> ClinicState:
    state["response"] = "Te paso con una recepcionista humana."
    state["done"] = True
    return state


def route(state: ClinicState) -> str:
    intent = state["intent"]
    if intent in ("book", "reschedule", "cancel", "ask_info"):
        return "booking"
    if intent == "confirm":
        return "reminder"
    if intent == "review":
        return "review"
    return "fallback"


def build_graph():
    g = StateGraph(ClinicState)
    g.add_node("router", router_node)
    g.add_node("booking", booking_node)
    g.add_node("reminder", reminder_node)
    g.add_node("review", review_node)
    g.add_node("fallback", fallback_node)
    g.set_entry_point("router")
    g.add_conditional_edges("router", route, {
        "booking": "booking",
        "reminder": "reminder",
        "review": "review",
        "fallback": "fallback",
    })
    for n in ("booking", "reminder", "review", "fallback"):
        g.add_edge(n, END)
    checkpointer = PostgresSaver.from_conn_string(os.environ["POSTGRES_URL"])
    return g.compile(checkpointer=checkpointer)
