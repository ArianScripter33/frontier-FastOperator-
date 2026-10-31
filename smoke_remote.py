#!/usr/bin/env python3
"""Check the deployed service without spending an official evaluation run.

Uses the practice desktop: never run alongside practice.py or another operator.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time
import urllib.request

from spike_vnc import websocket_url


def call(base, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(base + path, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode())


def correct_answer(state, expected):
    if state.get("estado") != "terminada":
        return False
    lines = re.findall(r"^respuesta:\s*(.*)$", state.get("resumen", ""), re.M | re.I)
    if len(lines) != 1:
        return False
    numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", lines[0])
    return bool(numbers) and numbers[0] == str(expected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public service URL, e.g. https://your-service.onrender.com")
    args = parser.parse_args(argv)
    base = args.url.rstrip("/")
    if not base.startswith("https://"):
        parser.error("Use the public HTTPS URL")
    required = ("FRONTIER_TEAM_TOKEN", "FRONTIER_DESKTOP_URL", "FRONTIER_DESKTOP_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        parser.error("Missing local configuration: " + ", ".join(missing))
    token = os.environ["FRONTIER_TEAM_TOKEN"]
    health_code, health = call(base, "/health", token)
    print("health:", (health_code, health), flush=True)
    if health_code != 200 or health.get("ok") is not True:
        print("FALLA: servicio no disponible", flush=True)
        return 1
    task = json.loads((Path(__file__).parent / "pruebas/E3-facturas-vencidas.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    code, created = call(base, "/tasks", token, {"tarea": task["instruccion"], "escritorio": {
        "url": websocket_url(os.environ["FRONTIER_DESKTOP_URL"]),
        "password": os.environ["FRONTIER_DESKTOP_PASSWORD"]}})
    accept_seconds = time.monotonic() - started
    task_id = created.get("task_id")
    if code not in (200, 201, 202) or not isinstance(task_id, str) or not task_id:
        print("FALLA: contrato de aceptación inválido; no reintentar automáticamente", flush=True)
        return 1
    print(f"POST /tasks: {accept_seconds:.2f} s; task_id: {task_id}", flush=True)
    if accept_seconds >= 2:
        print("FALLA: aceptación fuera de plazo; sigo consultando la misma tarea, sin reenviarla", flush=True)
    deadline = started + 300
    while time.monotonic() < deadline:
        time.sleep(min(5, max(0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            break
        _, state = call(base, f"/tasks/{task_id}", token)
        if state.get("estado") != "en_curso":
            elapsed = time.monotonic() - started
            passed = accept_seconds < 2 and elapsed < 300 and correct_answer(state, task["respuesta_esperada"])
            # Print no model-authored summary: it can contain secrets or irrelevant numbers.
            print(f"{'OK' if passed else 'FALLA'} · estado={state.get('estado')} · {elapsed:.1f} s · respuesta esperada {'confirmada' if passed else 'no confirmada'}", flush=True)
            return 0 if passed else 1
    print("FALLA: sin resultado confirmado antes de cinco minutos; no reintentar ni usar el escritorio hasta confirmar el cese del worker", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
