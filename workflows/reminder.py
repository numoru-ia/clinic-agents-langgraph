"""Temporal workflow: appointment reminders at 24h and 1h."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from temporalio import workflow


@dataclass
class Appointment:
    id: str
    patient_id: str
    start: datetime


@dataclass
class ReminderInput:
    patient_id: str
    slot_iso: str
    kind: str  # "24h" | "1h"


@workflow.defn
class AppointmentReminderWorkflow:
    @workflow.run
    async def run(self, appt: Appointment) -> None:
        now = workflow.now()
        delta_24 = (appt.start - timedelta(hours=24)) - now
        if delta_24.total_seconds() > 0:
            await workflow.sleep(delta_24)
        await workflow.execute_activity(
            "send_whatsapp_template",
            ReminderInput(appt.patient_id, appt.start.isoformat(), "24h"),
            start_to_close_timeout=timedelta(minutes=2),
        )
        now = workflow.now()
        delta_1 = (appt.start - timedelta(hours=1)) - now
        if delta_1.total_seconds() > 0:
            await workflow.sleep(delta_1)
        await workflow.execute_activity(
            "send_whatsapp_template",
            ReminderInput(appt.patient_id, appt.start.isoformat(), "1h"),
            start_to_close_timeout=timedelta(minutes=2),
        )
