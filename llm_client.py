"""
llm_client.py — Cliente unificado de OpenRouter para Frontier CDMX:
  1. `ask_jev_decision`: Consume TypeSafe Jev 1.14 en OpenRouter (`/api/alpha/decisions`) para decisiones
     tipadas ultrarrápidas (`choice`, `noul`, `score`, `box` con imágenes en `assets`).
     Si `FRONTIER_USE_JEV=0`, o si el endpoint alpha devuelve error, o si `confidence < umbral`,
     hace fallback transparente a `Claude Haiku 5.5` sin tirar el flujo.
  2. `ask_json`: Consume `anthropic/claude-haiku-5.5`, `deepseek/deepseek-v4.1-flash-1017` (preferencia
     DeepInfra/GMICloud y filtro ZDR; sin garantía regional) o el modelo que indique quien llama.
     `browser_agent` escala a `anthropic/claude-sonnet-5.5` solo cuando el validador rechaza un plan.
"""

from __future__ import annotations

import functools
import threading
import math
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from config import CONFIG
from telemetry import log_event

RETRYABLE_HTTP = {429, 500, 502, 503, 504}
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class BudgetExceededError(RuntimeError):
    pass


def parse_json_loose(text: str) -> Dict[str, Any]:
    cleaned = FENCE_RE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def validate_decisions(answers: Any, questions: Dict[str, Any]) -> None:
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Incomplete decisions response")
    for key, spec in questions.items():
        answer = answers[key]
        kind = spec.get("type")
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise ValueError("Invalid decision type")
        value = answer.get(kind)
        if kind == "choice":
            if value not in spec.get("criteria", {}):
                raise ValueError("Decision choice outside criteria")
        elif kind in ("noul", "score"):
            upper = 1 if kind == "noul" else len(spec.get("criteria", [])) - 1
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
                raise ValueError("Invalid decision score")
        elif kind == "box":
            if not isinstance(value, dict) or not all(isinstance(value.get(k), (int, float)) and math.isfinite(value[k]) for k in ("top", "bottom", "left", "right")):
                raise ValueError("Invalid box")
            if not (0 <= value["top"] < value["bottom"] <= 1 and 0 <= value["left"] < value["right"] <= 1):
                raise ValueError("Invalid box bounds")
        else:
            raise ValueError("Unsupported decision type")
        if kind in ("choice", "score", "box"):
            confidence = answer.get("confidence")
            if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid confidence")


def serialized_call(method):
    """Keep reserve/settle and nested fallback deltas atomic across HTTP tasks."""
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._call_lock:
            return method(self, *args, **kwargs)
    return wrapped


class OpenRouterClient:
    def __init__(self) -> None:
        self._call_lock = threading.RLock()
        self.total_cost_usd: float = 0.0
        self.calls: int = 0
        self.jev_calls: int = 0
        self.reported_cost_usd: float = 0.0
        self.unknown_cost_calls: int = 0

    def _reserve(self, task_spent: float, baseline: float) -> float:
        self._check_budget(task_spent + self.total_cost_usd - baseline)
        reserve = CONFIG.max_call_reserve_usd
        if reserve <= 0 or not math.isfinite(reserve):
            raise BudgetExceededError("Reserva por llamada inválida")
        if (task_spent + self.total_cost_usd - baseline + reserve > CONFIG.max_cost_per_task_usd
                or self.total_cost_usd + reserve > CONFIG.max_run_budget_usd):
            raise BudgetExceededError("Presupuesto insuficiente para reservar el siguiente intento")
        self.total_cost_usd += reserve
        return reserve

    def _settle(self, raw: Any, reserve: float) -> tuple[float, str]:
        usage = raw.get("usage") if isinstance(raw, dict) else None
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
            self.total_cost_usd += cost - reserve
            self.reported_cost_usd += cost
            return float(cost), "reported"
        self.unknown_cost_calls += 1
        return reserve, "unknown_reserved"


    def _check_budget(self, task_spent_usd: float) -> str:
        if task_spent_usd >= CONFIG.max_cost_per_task_usd:
            raise BudgetExceededError(f"Tope por tarea alcanzado ({task_spent_usd:.4f} USD)")
        if self.total_cost_usd >= CONFIG.max_run_budget_usd:
            raise BudgetExceededError(f"Tope de corrida alcanzado ({self.total_cost_usd:.4f} USD)")
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY no está definida en el entorno.")
        return api_key

    @serialized_call
    def ask_jev_decision(
        self,
        state: Any,
        questions: Dict[str, Dict[str, Any]],
        assets_b64_png: Optional[Dict[str, str]] = None,
        task_spent_usd: float = 0.0,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        Llama a TypeSafe Jev 1.14 vía OpenRouter Decisions API (`/api/alpha/decisions` — auditado con Deep Research):
          - Activa `TypeSafe-Danger-Zone-Images: true` y envuelve PNGs en `DecisionsImageAsset` cuando hay imágenes o `box`.
          - Activa `TypeSafe-Danger-Zone-Long-Context: true` si el payload supera ~60k tokens.
          - Poda listas `choice.criteria` a <= 25 opciones para no desactivar la compuerta interna de refinamiento.
          - El fallback de Claude Haiku 5.5 mantiene paridad 1:1 de esquema anidado (`{"type": "noul", "noul": 0.95}`, etc.).
        """
        api_key = self._check_budget(task_spent_usd)
        baseline = self.total_cost_usd
        t0 = time.perf_counter()

        # Pre-podar opciones >25 en primitivas choice (límite de refinamiento de decisions v1)
        safe_questions: Dict[str, Dict[str, Any]] = {}
        for q_key, q_spec in questions.items():
            q_copy = dict(q_spec)
            if q_copy.get("type") == "choice" and isinstance(q_copy.get("criteria"), dict) and len(q_copy["criteria"]) > 25:
                raise ValueError("Jev choice accepts at most 25 criteria; caller must rank candidates")
            safe_questions[q_key] = q_copy

        has_box = any(q.get("type") == "box" for q in safe_questions.values())

        if CONFIG.use_jev:
            body: Dict[str, Any] = {
                "model": CONFIG.jev_model,
                "state": state,
                "questions": safe_questions,
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            if assets_b64_png or has_box:
                headers["TypeSafe-Danger-Zone-Images"] = "true"
            if assets_b64_png:
                body["assets"] = {
                    k: {"type": "image", "format": "png", "data_base64": v}
                    for k, v in assets_b64_png.items()
                }
            payload_str = json.dumps(body, ensure_ascii=False)
            if len(payload_str) > 220_000:
                headers["TypeSafe-Danger-Zone-Long-Context"] = "true"

            req = urllib.request.Request(
                CONFIG.openrouter_decisions_url,
                data=payload_str.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            reserve = self._reserve(task_spent_usd, baseline)
            try:
                with urllib.request.urlopen(req, timeout=CONFIG.request_timeout_sec) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                cost, cost_source = self._settle(raw, reserve)
                answers = raw.get("answers") or raw.get("decisions")
                validate_decisions(answers, safe_questions)
                if any(answer.get("confidence", 1) < CONFIG.business_rules.get("jev_min_confidence", .75) for answer in answers.values()):
                    raise ValueError("Low confidence decision")
                self.jev_calls += 1
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                log_event(
                    "JEV_DECISION_COMPLETED",
                    model=CONFIG.jev_model,
                    latency_ms=latency_ms,
                    cost_usd=round(cost, 6),
                )
                return {
                    "engine": "jev",
                    "answers": answers,
                    "cost_source": cost_source,
                    "cost_usd": cost,
                    "latency_ms": latency_ms,
                }
            except BudgetExceededError:
                raise
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 402:
                    raise BudgetExceededError("OpenRouter devolvió 402") from exc
                log_event("JEV_FALLBACK_TO_HAIKU", reason=type(exc).__name__)

        if not allow_fallback:
            # The operator call that follows already reads the page; a second model for hints adds cost only.
            return {
                "engine": "none",
                "answers": {},
                "cost_usd": self.total_cost_usd - baseline,
                "cost_source": "none",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }

        # Fallback con paridad estricta de esquema anidado respecto a Decisions API v1
        fallback_res = self.ask_json(
            system_prompt=(
                "Respond ONLY with JSON `{\"answers\": {...}}` matching every key in `questions`. "
                "Exact nested schema per question type: "
                "noul -> `{\"type\": \"noul\", \"noul\": float}`; "
                "choice -> `{\"type\": \"choice\", \"choice\": str, \"confidence\": float, \"probabilities\": {}}`; "
                "score -> `{\"type\": \"score\", \"score\": float, \"confidence\": float}`; "
                "box -> `{\"type\": \"box\", \"box\": {\"top\": float, \"bottom\": float, \"left\": float, \"right\": float}, \"confidence\": float}`."
            ),
            user_prompt=json.dumps({"state": state, "questions": safe_questions}, ensure_ascii=False),
            model=CONFIG.fast_model,
            task_spent_usd=task_spent_usd + self.total_cost_usd - baseline,
            images_b64_png=list(assets_b64_png.values()) if assets_b64_png else None,
            _deadline=time.monotonic() + max(0, CONFIG.llm_total_timeout_sec - (time.perf_counter() - t0)),
        )
        validate_decisions(fallback_res["data"].get("answers"), safe_questions)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "engine": "haiku_fallback",
            "answers": fallback_res["data"].get("answers", fallback_res["data"]),
            "cost_usd": self.total_cost_usd - baseline,
            "cost_source": fallback_res["cost_source"],
            "latency_ms": latency_ms,
        }

    @serialized_call
    def ask_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        task_spent_usd: float = 0.0,
        images_b64_png: Optional[List[str]] = None,
        retries: int = 2,
        _deadline: Optional[float] = None,
    ) -> Dict[str, Any]:
        api_key = self._check_budget(task_spent_usd)
        baseline = self.total_cost_usd
        deadline = _deadline if _deadline is not None else time.monotonic() + CONFIG.llm_total_timeout_sec
        chosen_model = model or CONFIG.fast_model
        if "terra" in chosen_model.lower() or ("deepseek-v4.1-flash" in chosen_model and "1017" not in chosen_model):
            raise ValueError("Modelo no permitido por el contrato runtime")
        user_content: Any = user_prompt
        if images_b64_png:
            user_content = [{"type": "text", "text": user_prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}} for b64 in images_b64_png
            ]
        body: Dict[str, Any] = {
            "model": chosen_model,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": CONFIG.max_output_tokens,
            "provider": {"zdr": CONFIG.require_zdr, "data_collection": "deny"},
            "usage": {"include": True},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if "deepseek" in chosen_model.lower():
            # Preference order does not guarantee processing region.
            body["provider"].update({"order": ["DeepInfra", "GMICloud"], "allow_fallbacks": True})
        payload = json.dumps(body).encode("utf-8")

        raw: Dict[str, Any] = {}
        for attempt in range(retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("LLM total deadline exhausted")
            reserve = self._reserve(task_spent_usd, baseline)
            req = urllib.request.Request(
                CONFIG.openrouter_base_url,
                data=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=min(CONFIG.request_timeout_sec, remaining)) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                _, settled_source = self._settle(raw, reserve)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 402:
                    log_event("LLM_BUDGET_402", model=chosen_model)
                    raise BudgetExceededError("OpenRouter devolvió 402: saldo agotado") from exc
                if exc.code in RETRYABLE_HTTP and attempt < retries:
                    log_event("LLM_RETRY", model=chosen_model, http_code=exc.code, attempt=attempt + 1)
                    time.sleep(min(1.5 * (attempt + 1), max(0, deadline - time.monotonic())))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < retries:
                    log_event("LLM_RETRY", model=chosen_model, http_code="network", attempt=attempt + 1)
                    time.sleep(min(1.5 * (attempt + 1), max(0, deadline - time.monotonic())))
                    continue
                raise

        cost = self.total_cost_usd - baseline
        cost_source = settled_source if attempt == 0 else "mixed_reported_and_reserved"
        self.calls += 1

        try:
            content = raw["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Model content must be text")
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Malformed chat response envelope") from exc
        parsed = parse_json_loose(content)
        log_event(
            "LLM_CALL_COMPLETED",
            model=chosen_model,
            cost_usd=round(cost, 6),
            total_cost_usd=round(self.total_cost_usd, 6),
        )
        return {"data": parsed, "cost_usd": cost, "cost_source": cost_source, "model": chosen_model}
