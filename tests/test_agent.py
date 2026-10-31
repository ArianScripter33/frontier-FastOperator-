"""Real RFB bytes over a real websocket, against a small fake desktop. The model is scripted:
this proves the protocol and the loop's rules, never the quality of a real model."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time

_runtime = Path(tempfile.mkdtemp(prefix="frontier-test-"))
os.environ["FRONTIER_EVENTS_PATH"] = str(_runtime / "events.jsonl")
os.environ["FRONTIER_DB_PATH"] = str(_runtime / "agent.sqlite")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Crypto.Cipher import DES
from fastapi.testclient import TestClient
import pytest
from websockets.sync.server import serve

import screen_agent
from llm_client import BudgetExceededError
from screen_agent import build_summary, run_task, validate_plan
from service import create_app
from store import Store
import vnc_client
from vnc_client import VncClient, VncError

PASSWORD = "clave-del-escritorio"
WIDTH, HEIGHT = 64, 40


class FakeDesktop:
    def __init__(self):
        self.pointer, self.keys = [], []
        self.pixel = bytes([10, 20, 30, 0])
        self.server = serve(self.handler, "127.0.0.1", 0, subprotocols=["binary"], max_size=None)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"ws://127.0.0.1:{self.server.socket.getsockname()[1]}/websockify"

    def handler(self, ws):
        buffer = bytearray()

        def read(count):
            while len(buffer) < count:
                buffer.extend(ws.recv())
            data = bytes(buffer[:count])
            del buffer[:count]
            return data

        ws.send(b"RFB 003.008\n")
        assert read(12) == b"RFB 003.008\n"
        ws.send(bytes([1, 2]))
        assert read(1) == b"\x02"
        challenge = bytes(range(16))
        ws.send(challenge)
        key = bytes(int(f"{b:08b}"[::-1], 2) for b in PASSWORD.encode()[:8])
        ok = read(16) == DES.new(key, DES.MODE_ECB).encrypt(challenge)
        ws.send(struct.pack(">I", 0 if ok else 1))
        if not ok:
            return
        read(1)
        ws.send(struct.pack(">HH", WIDTH, HEIGHT) + bytes(16) + struct.pack(">I", 4) + b"demo")
        while True:
            kind = read(1)[0]
            if kind == 0:
                read(19)
            elif kind == 2:
                _, count = struct.unpack(">BH", read(3))
                read(count * 4)
            elif kind == 3:
                read(9)
                ws.send(b"\x00\x00" + struct.pack(">H", 1) + struct.pack(">HHHHi", 0, 0, WIDTH, HEIGHT, 0) + self.pixel * (WIDTH * HEIGHT))
            elif kind == 4:
                down, keysym = struct.unpack(">BxxI", read(7))
                self.keys.append((down, keysym, time.monotonic()))
            elif kind == 5:
                mask, x, y = struct.unpack(">BHH", read(5))
                self.pointer.append((mask, x, y, time.monotonic()))


@pytest.fixture
def desktop(monkeypatch):
    monkeypatch.setattr(vnc_client, "REPAINT_SECONDS", 0.01)
    fake = FakeDesktop()
    yield fake
    fake.server.shutdown()


class ScriptedModel:
    def __init__(self, plans):
        self.plans = list(plans)
        self.prompts = []
        self.models = []

    def ask_json(self, system_prompt, user_prompt, model=None, task_spent_usd=0.0, images_b64_png=None, _deadline=None):
        self.prompts.append(json.loads(user_prompt))
        self.models.append(model)
        assert images_b64_png
        plan = self.plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        return {"data": plan, "cost_usd": 0.001, "cost_source": "reported", "model": model}


def finish(estado="terminada", **fields):
    return {"app": "SIGECOM", "progreso": {"hecho": "x", "falta": "", "datos": {}}, "actions": [],
            "fin": {"estado": estado, "resumen": "Hecho.", **fields}}


def act(*actions):
    return {"app": "SIGECOM", "progreso": {"hecho": "paso", "falta": "más", "datos": {"visto": 1}}, "actions": list(actions), "fin": None}


def run(desktop, tmp_path, plans, name="t1", **kwargs):
    store = Store(tmp_path / "db.sqlite")
    store.create_task(name, "tarea")
    model = ScriptedModel(plans)
    return run_task(name, "tarea", desktop.url, PASSWORD, store, llm=model, **kwargs), store, model


def test_client_reads_screen_and_holds_clicks_long_enough(desktop):
    client = VncClient(desktop.url, PASSWORD)
    assert (client.width, client.height) == (WIDTH, HEIGHT)
    png = client.screenshot_png()
    assert png.startswith(b"\x89PNG")
    from io import BytesIO
    from PIL import Image
    assert Image.open(BytesIO(png)).getpixel((3, 3)) == (30, 20, 10)
    client.click(5, 6)
    client.close()
    time.sleep(0.05)
    down = next(p for p in desktop.pointer if p[0] == 1)
    up = next(p for p in desktop.pointer if p[0] == 0 and p[3] > down[3])
    assert up[3] - down[3] >= 0.1 and down[1:3] == (5, 6)


def test_wrong_password_is_rejected(desktop):
    with pytest.raises(VncError):
        VncClient(desktop.url, "otra-clave")


def test_replace_text_selects_all_before_typing(desktop):
    client = VncClient(desktop.url, PASSWORD)
    client.replace_text(1, 1, "ñ")
    client.screenshot_png()
    client.close()
    time.sleep(0.05)
    pressed = [k[1] for k in desktop.keys if k[0]]
    assert pressed == [0xFFE3, ord("a"), ord("ñ")]


def test_task_acts_then_verifies_and_reports(desktop, tmp_path):
    outcome, store, model = run(desktop, tmp_path, [
        act({"op": "click", "x": 3, "y": 4, "guardado": None}), finish(respuesta=["45"]),
    ])
    assert outcome["estado"] == "terminada" and outcome["resumen"].splitlines()[0] == "respuesta: 45"
    assert model.prompts[1]["progreso"]["datos"] == {"visto": 1}
    assert store.get_task("t1")["estado"] == "terminada" and outcome["pasos"] == 2


def test_summary_format():
    assert build_summary("terminada", {"respuesta": ["Ana", 3], "resumen": "respuesta: 9\nListo"}, []) == "respuesta: Ana; 3\nListo"
    failed = build_summary("fallida", {"respuesta": ["1"], "datos_razon": ["52", "10"], "resumen": "Hay dos."}, [])
    assert "respuesta:" not in failed and "52" in failed and "10" in failed
    assert "clave" not in build_summary("terminada", {"resumen": "usé clave"}, ["clave"])


def test_finishing_and_acting_in_the_same_turn_is_rejected():
    plan = act({"op": "click", "x": 1, "y": 1})
    plan["fin"] = {"estado": "terminada"}
    with pytest.raises(ValueError):
        validate_plan(plan, WIDTH, HEIGHT, [])


@pytest.mark.parametrize("action", [{"op": "click", "x": 9999, "y": 1}, {"op": "drag"}, {"op": "type"}, {"op": "click", "x": True, "y": 1}])
def test_bad_actions_are_rejected(action):
    with pytest.raises(ValueError):
        validate_plan(act(action), WIDTH, HEIGHT, [])


def test_a_save_cannot_be_repeated(desktop, tmp_path):
    save = {"op": "click", "x": 2, "y": 2, "guardado": "Cliente nuevo"}
    outcome, _, model = run(desktop, tmp_path, [act(save), act({**save, "guardado": "cliente  NUEVO"}), finish("fallida", datos_razon=["sin confirmación"])])
    clicks = [p for p in desktop.pointer if p[0] == 1]
    assert len(clicks) == 1 and outcome["estado"] == "fallida"
    assert "Plan rechazado" in model.prompts[2]["aviso"] and model.prompts[2]["guardados_ya_intentados"] == ["cliente nuevo"]


def test_time_limit_stops_acting_and_publishes_fallida(desktop, tmp_path, monkeypatch):
    monkeypatch.setattr(screen_agent.CONFIG, "task_seconds", 0.0)
    outcome, store, model = run(desktop, tmp_path, [act({"op": "click", "x": 1, "y": 1})])
    assert outcome["estado"] == "fallida" and outcome["motivo"] == "sin_tiempo"
    assert store.get_task("t1")["estado"] == "fallida" and model.prompts == [] and not desktop.pointer


def test_budget_and_broken_desktop_end_as_fallida_without_secrets(desktop, tmp_path):
    outcome, _, _ = run(desktop, tmp_path, [BudgetExceededError("tope")])
    assert outcome["estado"] == "fallida" and outcome["motivo"] == "sin_presupuesto"
    store = Store(tmp_path / "other.sqlite")
    store.create_task("t2", "x")
    down = run_task("t2", "x", "ws://127.0.0.1:1/websockify", PASSWORD, store, llm=ScriptedModel([]))
    assert down["estado"] == "fallida" and PASSWORD not in down["resumen"]


def test_invalid_reply_retries_and_stuck_screen_escalates(desktop, tmp_path):
    click = {"op": "click", "x": 1, "y": 1}
    outcome, _, model = run(desktop, tmp_path, [ValueError("json"), act(click), act(click), act(click), finish()])
    assert outcome["estado"] == "terminada" and model.prompts[1]["aviso"]
    assert screen_agent.CONFIG.strong_model not in model.models  # Off by default.
    assert "no cambiaron la pantalla" in model.prompts[3]["aviso"]  # The fake screen never changes.


def test_notes_keep_strategies_not_data_and_stale_ones_leave(desktop, tmp_path):
    fin = finish(aprendido=["Los clientes están en el menú Clientes", "El NIT es 901234567"])
    run(desktop, tmp_path, [fin], name="a")
    store = Store(tmp_path / "db.sqlite")
    assert store.notes_for("SIGECOM") == ["Los clientes están en el menú Clientes"]
    stale = act({"op": "click", "x": 1, "y": 1})
    stale["notas_viejas"] = ["Los clientes están en el menú Clientes"]
    run(desktop, tmp_path, [stale, finish()], name="b")
    assert Store(tmp_path / "db.sqlite").notes_for("SIGECOM") == []


def test_service_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_TEAM_TOKEN", "equipo")
    store = Store(tmp_path / "s.sqlite")
    release = threading.Event()

    def runner(task_id, tarea, url, password, store, secrets=None):
        release.wait(5)
        store.finish_task(task_id, estado="terminada", resumen="respuesta: 1")

    http = TestClient(create_app(store, runner))
    assert http.get("/health").status_code == 200
    body = {"tarea": "x", "escritorio": {"url": "wss://d/websockify", "password": "p"}}
    assert http.post("/tasks", json=body).status_code == 401
    auth = {"Authorization": "Bearer equipo"}
    started = time.monotonic()
    task_id = http.post("/tasks", json=body, headers=auth).json()["task_id"]
    assert time.monotonic() - started < 2
    assert http.get(f"/tasks/{task_id}", headers=auth).json() == {"estado": "en_curso", "resumen": ""}
    release.set()
    for _ in range(50):
        if http.get(f"/tasks/{task_id}", headers=auth).json()["estado"] != "en_curso":
            break
        time.sleep(0.02)
    assert http.get(f"/tasks/{task_id}", headers=auth).json() == {"estado": "terminada", "resumen": "respuesta: 1"}
    assert http.get("/tasks/nada", headers=auth).status_code == 404
    assert http.post("/tasks", json={**body, "escritorio": {"url": "http://d", "password": "p"}}, headers=auth).status_code == 422
    assert http.get("/stats", headers=auth).json()["por_estado"] == {"terminada": 1}


def test_typing_stops_when_task_time_ends(desktop):
    from vnc_client import DeadlineReached
    client = VncClient(desktop.url, PASSWORD)
    client.stop_at = time.monotonic() - 1
    with pytest.raises(DeadlineReached):
        client.type_text("no debe llegar")
    client.screenshot_png()
    client.close()
    assert not desktop.keys
