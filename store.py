"""SQLite: what happened to each task, and what the agent learned about each app.

Task rows hold no credentials. App notes are general strategies, never business data or coordinates,
and are checked again against the screen every time they are used.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import DB_PATH

MAX_NOTES_PER_APP = 12
_DATA_LIKE = re.compile(r"\d")


class Store:
    def __init__(self, path: Path = DB_PATH) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, tarea TEXT, estado TEXT, resumen TEXT, app TEXT, motivo TEXT,
                pasos INTEGER DEFAULT 0, escaladas INTEGER DEFAULT 0, costo_usd REAL DEFAULT 0,
                segundos_modelo REAL DEFAULT 0, segundos_pantalla REAL DEFAULT 0, segundos REAL DEFAULT 0,
                creada REAL, terminada REAL);
            CREATE TABLE IF NOT EXISTS app_notes (app TEXT, note TEXT, created REAL, PRIMARY KEY (app, note));
            """
        )
        self._db.commit()

    def create_task(self, task_id: str, tarea: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO tasks (id, tarea, estado, resumen, creada) VALUES (?, ?, 'en_curso', '', ?)",
                             (task_id, tarea, time.time()))
            self._db.commit()

    def finish_task(self, task_id: str, **fields: Any) -> None:
        fields["terminada"] = time.time()
        columns = ", ".join(f"{name} = ?" for name in fields)
        with self._lock:
            self._db.execute(f"UPDATE tasks SET {columns} WHERE id = ?", (*fields.values(), task_id))
            self._db.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def stats(self) -> Dict[str, Any]:
        """Where the time and the failures go."""
        with self._lock:
            by_state = {r["estado"]: r["n"] for r in self._db.execute("SELECT estado, COUNT(*) n FROM tasks GROUP BY estado")}
            totals = dict(self._db.execute(
                """SELECT COALESCE(AVG(pasos),0) pasos, COALESCE(AVG(segundos),0) segundos, COALESCE(SUM(costo_usd),0) costo_total,
                          COALESCE(AVG(segundos_modelo),0) segundos_modelo, COALESCE(AVG(segundos_pantalla),0) segundos_pantalla
                   FROM tasks WHERE estado != 'en_curso'""").fetchone())
            reasons = [dict(r) for r in self._db.execute(
                "SELECT motivo, COUNT(*) n FROM tasks WHERE motivo IS NOT NULL GROUP BY motivo ORDER BY n DESC LIMIT 10")]
        return {"por_estado": by_state, "promedios": totals, "motivos": reasons}

    def notes_for(self, app: str) -> List[str]:
        with self._lock:
            rows = self._db.execute("SELECT note FROM app_notes WHERE app = ? ORDER BY created DESC LIMIT ?",
                                    (app, MAX_NOTES_PER_APP)).fetchall()
        return [r["note"] for r in rows]

    def add_notes(self, app: str, notes: List[Any]) -> None:
        with self._lock:
            for note in notes:
                text = str(note).strip()[:200]
                # Digits mean ids, amounts, dates or coordinates: data from one task, not a strategy.
                if text and not _DATA_LIKE.search(text):
                    self._db.execute("INSERT OR REPLACE INTO app_notes VALUES (?, ?, ?)", (app, text, time.time()))
            self._db.commit()

    def remove_note(self, app: str, note: str) -> int:
        with self._lock:
            removed = self._db.execute("DELETE FROM app_notes WHERE app = ? AND note = ?", (app, note)).rowcount
            self._db.commit()
        return removed
