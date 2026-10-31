#!/usr/bin/env python3
"""Run by hand: the practice tasks on your own desktop, each one reset, run and checked.

Needs FRONTIER_DESKTOP_URL, FRONTIER_DESKTOP_PASSWORD, FRONTIER_DESKTOP_TOKEN and OPENROUTER_API_KEY.
  python3 practice.py E3 E5     # only these
  python3 practice.py           # all
Saves .runtime/practice/<time>.json with no credentials.
"""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import uuid

from screen_agent import run_task
from spike_vnc import websocket_url
from store import Store


def call(base: str, path: str, token: str, body=None):
    request = urllib.request.Request(base + path, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else b"")
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode()
    return json.loads(raw) if raw.strip().startswith("{") else raw


def own_checks(test, outcome):
    """What /__check does not see: the state and the summary."""
    checks = {"estado": outcome["estado"] == test["estado_esperado"]}
    lines = [line for line in outcome["resumen"].splitlines() if line.lower().startswith("respuesta:")]
    if "respuesta_esperada" in test:
        checks["respuesta"] = bool(lines) and str(test["respuesta_esperada"]) in lines[0]
    if "claves_razon" in test:
        checks["claves_razon"] = all(str(key) in outcome["resumen"] for key in test["claves_razon"])
    return checks


def main() -> None:
    base = os.environ["FRONTIER_DESKTOP_URL"].rstrip("/")
    token = os.environ["FRONTIER_DESKTOP_TOKEN"]
    url = websocket_url(base)
    wanted = set(sys.argv[1:])
    store = Store(Path(".runtime/practice/agent.sqlite"))
    rows = []
    for path in sorted(Path("pruebas").glob("*.json")):
        test = json.loads(path.read_text(encoding="utf-8"))
        if wanted and test["id"] not in wanted:
            continue
        call(base, "/__reset", token)
        time.sleep(4)  # The reset restarts the browser.
        task_id = uuid.uuid4().hex
        store.create_task(task_id, test["instruccion"])
        outcome = run_task(task_id, test["instruccion"], url, os.environ["FRONTIER_DESKTOP_PASSWORD"], store, secrets=[token])
        app_check = call(base, "/__check", token, test)
        own = own_checks(test, outcome)
        passed = bool(app_check.get("pass")) and all(own.values())
        rows.append({"id": test["id"], "pass": passed, "app_check": app_check, "own": own, **outcome})
        print(f"{'OK   ' if passed else 'FALLA'} {test['id']} · {outcome['estado']} · {outcome['pasos']} pasos · "
              f"{outcome['segundos']} s · {outcome['costo_usd']:.4f} USD · modelo {outcome['segundos_modelo']:.0f} s · pantalla {outcome['segundos_pantalla']:.0f} s")
        print(f"      resumen: {outcome['resumen'][:300]!r}")
        print(f"      app: {[c['nombre'] for c in app_check.get('checks', []) if not c.get('ok')] or 'ok'} · propios: {own}")
    output = Path(".runtime/practice") / f"{time.strftime('%H%M%S')}.json"
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{sum(r['pass'] for r in rows)}/{len(rows)} · {sum(r['costo_usd'] for r in rows):.4f} USD · {output}")


if __name__ == "__main__":
    main()
