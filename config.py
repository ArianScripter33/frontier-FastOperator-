"""Limits and models. The evaluator only provides what the service gets at deploy time, so defaults must work."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Dict

ROOT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("FRONTIER_STATE_DIR", str(ROOT_DIR / ".runtime" if os.access(ROOT_DIR, os.W_OK)
                                                         else Path(tempfile.gettempdir()) / "frontier-state")))
EVENTS_PATH = Path(os.environ.get("FRONTIER_EVENTS_PATH", str(STATE_DIR / "events.jsonl")))
DB_PATH = Path(os.environ.get("FRONTIER_DB_PATH", str(STATE_DIR / "agent.sqlite")))


@dataclass
class RuntimeConfig:
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_decisions_url: str = "https://openrouter.ai/api/alpha/decisions"
    jev_model: str = os.environ.get("FRONTIER_JEV_MODEL", "typesafe/jev-1.14")
    use_jev: bool = os.environ.get("FRONTIER_USE_JEV", "0") == "1"
    fast_model: str = os.environ.get("FRONTIER_FAST_MODEL", "anthropic/claude-haiku-5.5")
    strong_model: str = os.environ.get("FRONTIER_STRONG_MODEL", "anthropic/claude-sonnet-5.5")
    require_zdr: bool = os.environ.get("FRONTIER_REQUIRE_ZDR", "1") == "1"
    task_seconds: float = float(os.environ.get("FRONTIER_TASK_SECONDS", "270"))  # Evaluator stops at 300.
    max_steps: int = 45
    max_actions_per_step: int = 6
    max_escalations: int = int(os.environ.get("FRONTIER_MAX_ESCALATIONS", "0"))  # Practice passed 5/5 on the fast model path; escalation cost 10x.
    max_cost_per_task_usd: float = 0.10
    max_run_budget_usd: float = 0.10  # One client per task, so this equals the task cap.
    request_timeout_sec: int = 25
    llm_total_timeout_sec: float = 45.0
    max_output_tokens: int = 2500
    max_call_reserve_usd: float = 0.01
    business_rules: Dict[str, object] = field(default_factory=dict)


CONFIG = RuntimeConfig()
