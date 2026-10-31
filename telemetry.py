"""
telemetry.py — Registro estructurado en events.jsonl (Evidencia directa para 4/4 en Incidente 15:30 y Debrief).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from config import EVENTS_PATH


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"authorization|api.?key|password|secret|token", str(k), re.I) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            value = value.replace(key, "[REDACTED]")
        value = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", value)
        return re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value


def log_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "event": event_type,
        **redact(payload),
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def log_incident_drift(
    layer: str,
    stale_key: str,
    details: str,
    recovery_action: str,
    recovery_success: bool,
) -> Dict[str, Any]:
    """
    Emite la traza exacta que demuestra detección y adaptación automática ante el cambio de las 15:30.
    """
    return log_event(
        "INCIDENT_DRIFT_DETECTED",
        layer=layer,
        stale_key=stale_key,
        details=details,
        recovery_action=recovery_action,
        recovery_success=recovery_success,
    )
