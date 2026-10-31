#!/usr/bin/env python3
"""Asks for the desktop credentials without echoing them and stores them in the ignored .env."""
from getpass import getpass
import os
from pathlib import Path
import shlex
import sys

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / ".env"
values = {
    "FRONTIER_DESKTOP_URL": input("URL del escritorio (https://...): ").strip(),
    "FRONTIER_DESKTOP_PASSWORD": getpass("Contraseña del escritorio (no se verá): ").strip(),
    "FRONTIER_DESKTOP_TOKEN": getpass("Token del escritorio (no se verá): ").strip(),
}
if not all(values.values()) or not values["FRONTIER_DESKTOP_URL"].startswith("https://"):
    sys.exit("Falta un valor o la URL no empieza con https://; no cambié nada.")
kept = [line for line in (path.read_text(encoding="utf-8").splitlines() if path.exists() else [])
        if line.replace("export ", "", 1).split("=", 1)[0].strip() not in values]
path.write_text("\n".join(kept + [f"{k}={shlex.quote(v)}" for k, v in values.items()]) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
print("Guardado en .env. Ahora corre spike_vnc.py --model")
