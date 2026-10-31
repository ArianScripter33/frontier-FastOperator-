#!/usr/bin/env python3
"""Run by hand: proves the deployed service works, without spending an official run.

  python3 smoke_remote.py https://your-service.example
Needs FRONTIER_TEAM_TOKEN, FRONTIER_DESKTOP_URL and FRONTIER_DESKTOP_PASSWORD (.env is loaded).
"""
import json
import os
import sys
import time
import urllib.request

from spike_vnc import websocket_url


def call(base, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(base + path, headers=headers, data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode())


def main():
    base = sys.argv[1].rstrip("/")
    token = os.environ["FRONTIER_TEAM_TOKEN"]
    print("health:", call(base, "/health"))
    task = json.load(open("pruebas/E3-facturas-vencidas.json", encoding="utf-8"))
    started = time.monotonic()
    _, created = call(base, "/tasks", token, {"tarea": task["instruccion"], "escritorio": {
        "url": websocket_url(os.environ["FRONTIER_DESKTOP_URL"]), "password": os.environ["FRONTIER_DESKTOP_PASSWORD"]}})
    print(f"POST /tasks: {time.monotonic() - started:.2f} s")
    while time.monotonic() - started < 300:
        time.sleep(5)
        _, state = call(base, f"/tasks/{created['task_id']}", token)
        if state["estado"] != "en_curso":
            print(f"{state['estado']} en {time.monotonic() - started:.0f} s:", state["resumen"].splitlines()[:1])
            return
    print("Sin terminar a los 5 minutos")


if __name__ == "__main__":
    main()
