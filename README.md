# clinic-agents-langgraph

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.60-1c7ed6.svg)](https://langchain-ai.github.io/langgraph/)
[![Temporal](https://img.shields.io/badge/Temporal-1.25-000000.svg)](https://temporal.io)
[![NeMo Guardrails](https://img.shields.io/badge/NeMo_Guardrails-0.11.1-76b900.svg)](https://github.com/NVIDIA/NeMo-Guardrails)
[![Mem0](https://img.shields.io/badge/Mem0-0.1.31-a855f7.svg)](https://github.com/mem0ai/mem0)

> **Three coordinated LangGraph agents for a dental clinic — booking, reminders, and reviews — wired together with a Postgres-checkpointed state graph, Temporal workflows for 24h/1h appointment reminders, Mem0 semantic memory, NeMo Guardrails to refuse medical diagnosis, and Langfuse tracing.** Production-tested in a pilot clinic.

Companion article: [Orquestar tres agentes para una clínica dental con LangGraph](https://numoru.com/en/contributions/agentes-clinica-dental-langgraph).

> **Safety disclaimer.** This is a *receptionist* and scheduling assistant, **not** a medical product. Guardrails in `guardrails/clinic.colang` explicitly refuse clinical diagnosis and route back to a human clinician. Do not deploy without review from a licensed professional in your jurisdiction.

---

## Why

A dental clinic runs on three choreographies: **booking** (async, needs calendar and human confirmation), **reminders** (durable, time-based, often 24 h before and 1 h before), and **reviews** (after-visit, optional). A single monolithic agent either reinvents Temporal poorly or drops context across days. This repo composes the right tool for each:

| Concern | Component |
|---|---|
| Turn-by-turn routing | LangGraph `StateGraph(ClinicState)` with `PostgresSaver` checkpointer |
| Durable, time-based tasks | `temporalio` `AppointmentReminderWorkflow` (sleeps to `start - 24h`, then `start - 1h`) |
| Semantic memory per patient | `mem0ai==0.1.31` |
| Safety rails | `nemoguardrails==0.11.1` via `guardrails/clinic.colang` |
| Observability | `langfuse==2.58.1` |
| Transport | `FastAPI` POST `/turn` |

---

## The three agents

| Node (graph) | Responsibility | Memory | Tools expected | Escalates to |
|---|---|---|---|---|
| `booking` | Open slot, book, reschedule, cancel, answer clinic info | Mem0 per `patient_id` | `search_clinic_info`, calendar slot finder, booking API | `fallback` (human receptionist) |
| `reminder` | Handle patient confirmation replies (e.g. "confirmar"), acknowledge | LangGraph checkpoint only | none (state read) | — |
| `review` | Ask for Google review after positive signal | Mem0 flag "review-asked" | Review deep-link generator | — |
| `fallback` | Hand off to a human operator | — | none | Operator on Slack/email |
| `router` | Classify intent via simple keyword match; pluggable for LLM later | — | `classify_intent` | — |

---

## Run

```bash
docker compose up -d                        # postgres:16 + qdrant v1.12.5 + redis:7 + temporal:1.25
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_URL="postgresql://postgres:clinic@localhost:5432/clinic"
uvicorn clinic.api:app --host 0.0.0.0 --port 8000

# send a turn
curl -X POST http://localhost:8000/turn \
  -H "Content-Type: application/json" \
  -d '{"message":"quiero agendar una limpieza","channel":"whatsapp"}'
```

---

## Architecture

```mermaid
flowchart LR
    WA[WhatsApp / Voice / Web]
    WA -->|POST /turn| API[FastAPI<br/>clinic/api.py]
    API --> LG[LangGraph<br/>build_graph()]
    subgraph LG["clinic/graph.py · StateGraph(ClinicState)"]
        R[router_node<br/>classify_intent]
        B[booking_node]
        Re[reminder_node]
        Rv[review_node]
        F[fallback_node]
        R -- book/reschedule/cancel/ask_info --> B
        R -- confirm --> Re
        R -- review --> Rv
        R -- unknown --> F
    end
    LG --- CP[(Postgres<br/>PostgresSaver checkpointer)]
    LG --> Guards[NeMo Guardrails<br/>guardrails/clinic.colang]
    LG --> Mem[Mem0<br/>per patient_id]
    LG --> LF[Langfuse traces]
    API --> T[Temporal<br/>AppointmentReminderWorkflow]
    T -->|send_whatsapp_template| WA

    style Guards fill:#fee2e2,stroke:#dc2626
    style T fill:#fef3c7,stroke:#d97706
    style CP fill:#dbeafe,stroke:#2563eb
```

### Temporal workflow — state diagram (`AppointmentReminderWorkflow`)

```mermaid
stateDiagram-v2
    [*] --> Scheduled: workflow.start(appt)
    Scheduled --> Sleeping24h: sleep until appt.start - 24h
    Sleeping24h --> Sending24h: execute_activity("send_whatsapp_template", kind="24h", timeout=2m)
    Sending24h --> Sleeping1h: sleep until appt.start - 1h
    Sleeping1h --> Sending1h: execute_activity("send_whatsapp_template", kind="1h", timeout=2m)
    Sending1h --> Completed
    Sending24h --> RetryingActivity: activity failure (Temporal default retry)
    RetryingActivity --> Sending24h
    Sending1h --> RetryingActivity2: activity failure
    RetryingActivity2 --> Sending1h
    Completed --> [*]
```

### End-to-end turn — sequence

```mermaid
sequenceDiagram
    autonumber
    participant Patient as Patient
    participant WA as WhatsApp Business
    participant API as FastAPI /turn
    participant G as LangGraph graph
    participant R as router_node
    participant B as booking_node
    participant Mem as Mem0
    participant Guards as NeMo Guardrails
    participant LF as Langfuse
    participant T as Temporal

    Patient->>WA: "quiero agendar una limpieza para el jueves"
    WA->>API: POST /turn {message, channel=whatsapp}
    API->>G: ainvoke(ClinicState, thread_id=session_id)
    G->>R: router_node
    R->>R: classify_intent → "book"
    R->>Guards: check against clinic.colang
    Guards-->>R: allowed
    R->>B: booking_node
    B->>Mem: recall patient_id preferences
    Mem-->>B: past visits, allergies note
    B-->>G: state.response = "Claro, te ayudo a agendar..."
    G->>LF: trace(session_id, intent=book)
    G-->>API: final state
    API-->>WA: {session_id, response}
    WA-->>Patient: reply
    Note over T: Once the appointment is confirmed,<br/>API starts the Temporal workflow.
    API->>T: start AppointmentReminderWorkflow(appt)
    T-->>WA: 24h & 1h reminder activities fire at their times
```

---

## Guardrails (`guardrails/clinic.colang`)

| User intent | Bot behavior |
|---|---|
| Asks for medical diagnosis ("¿tengo caries?", "¿es grave?") | **Refuse** and redirect: *"Para diagnosticar necesitamos verte. ¿Te agendo con el doctor?"* |
| Asks for off-hand pricing ("¿cuánto cuesta limpieza?") | Execute `search_clinic_info` to return the published price list |

NeMo Colang flows are intentionally narrow — expand as needed, but keep medical-diagnosis refusal as the default policy.

---

## Configuration

| Env var | Required | Description |
|---|---|---|
| `POSTGRES_URL` | ✅ | Postgres connection string for `PostgresSaver` checkpoint + Temporal metadata |
| `ANTHROPIC_API_KEY` | ✅ | Required by `langchain-anthropic==0.3.0` LLM calls (when booking/review use an LLM) |
| `QDRANT_URL` | optional | For RAG over clinic FAQ |
| `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | optional | Langfuse observability |
| `TEMPORAL_ADDRESS` | optional | Default `localhost:7233` |

### Pinned dependencies

| Package | Version | Why |
|---|---|---|
| `langgraph` | 0.2.60 | `StateGraph` + `PostgresSaver` |
| `langchain-anthropic` | 0.3.0 | Claude calls inside nodes |
| `mem0ai` | 0.1.31 | Per-patient semantic memory |
| `temporalio` | 1.8.0 | Durable reminder workflow |
| `nemoguardrails` | 0.11.1 | Refusal flows in Colang |
| `qdrant-client` | 1.12.1 | RAG source (clinic FAQ) |
| `redis` | 5.2.1 | Working memory / rate limits |
| `langfuse` | 2.58.1 | Traces |
| `psycopg[binary]` | 3.2.3 | Postgres checkpointer backend |

---

## Pilot results (read with skepticism)

From a **pilot clinic (3 doctors, ~850 visits/month)**, 90 days after go-live:

| Metric | Before | 90 days later |
|---|---|---|
| No-show rate | 22% | 14% |
| After-hours leads captured | 12% | 87% |
| Reception hours/month | 170 | 108 |
| Google reviews/month | 4 | 18 |

These numbers are from one clinic and should not be extrapolated. Re-measure in your setting before making business decisions.

---

## Testing & evals

- **Graph-level**: unit-test `classify_intent` with a table of Spanish utterances → expected intents.
- **Temporal**: use `temporalio.testing.WorkflowEnvironment` to assert `AppointmentReminderWorkflow` sleeps and fires both activities.
- **Guardrails**: run the Colang flows against a red-team prompt set (symptom-style queries, pricing-baiting).
- **End-to-end**: hit `/turn` with a fixture conversation and assert the final `response` matches.

## Best practices

- **Always pass a `thread_id`** (the session/patient id) — LangGraph uses it to resume the correct checkpoint.
- **Keep `classify_intent` deterministic** to start; add an LLM fallback only for the long-tail.
- **Temporal workflows are for durable, time-based choreography** — do not pack LLM calls inside them without activities.
- **Never reveal the graph internals to the patient** — wrap failures in `fallback_node` and hand off.

## Roadmap

- [ ] LLM-backed `classify_intent` for the long-tail (router currently keyword-based).
- [ ] `booking_node`: bind a real calendar slot finder + booking API.
- [ ] First-class Langfuse spans per node.
- [ ] Reschedule/cancel edges with compensating Temporal workflows.
- [ ] Multi-clinic (multi-tenant) Qdrant payload filter.

## License

Apache 2.0 — see [LICENSE](LICENSE).
