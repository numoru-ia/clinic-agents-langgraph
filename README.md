# clinic-agents-langgraph

Three orchestrated LangGraph agents for a dental clinic: appointments + reminders + reviews.
Postgres checkpointer, Mem0 semantic memory, Temporal long-running workflows, NeMo guardrails, Langfuse observability.

Companion to: [Orquestar tres agentes para una clínica dental con LangGraph](https://numoru.com/contribuciones/agentes-clinica-dental-langgraph).

## Results

From pilot clinic (3 doctors, 850 visits/month):

| Metric | Before | 90 days later |
|---|---|---|
| No-show rate | 22% | 14% |
| After-hours leads captured | 12% | 87% |
| Reception hours/month | 170 | 108 |
| Google reviews/month | 4 | 18 |

## Run

```bash
docker compose up -d
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn clinic.api:app --host 0.0.0.0 --port 8000
```
