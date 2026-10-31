#!/usr/bin/env python3
"""Run by hand: proves the desktop answers. Connects, captures, clicks an empty corner, captures, asks the model.

Needs FRONTIER_DESKTOP_URL (https://...) and FRONTIER_DESKTOP_PASSWORD. Saves images in .runtime/spike/.
With --model it also makes one real model call, which needs OPENROUTER_API_KEY.
"""
import argparse
import base64
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from vnc_client import VncClient


def websocket_url(desktop_url: str) -> str:
    parts = urlsplit(desktop_url)
    scheme = "ws" if parts.scheme in ("http", "ws") else "wss"
    return f"{scheme}://{parts.netloc}/websockify"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true", help="Also send the capture to the vision model")
    args = parser.parse_args()
    output = Path(".runtime/spike")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    client = VncClient(websocket_url(os.environ["FRONTIER_DESKTOP_URL"]), os.environ["FRONTIER_DESKTOP_PASSWORD"])
    print(f"Conectado: {client.width}x{client.height} en {time.monotonic() - started:.2f} s")
    try:
        started = time.monotonic()
        first = client.screenshot_png()
        print(f"Captura: {len(first)} bytes en {time.monotonic() - started:.2f} s")
        (output / "1_antes.png").write_bytes(first)
        client.click(client.width - 5, client.height - 5)
        started = time.monotonic()
        second = client.settled_screenshot()
        print(f"Captura tras clic: {len(second)} bytes en {time.monotonic() - started:.2f} s")
        (output / "2_despues.png").write_bytes(second)
    finally:
        client.close()
    if args.model:
        from llm_client import OpenRouterClient
        started = time.monotonic()
        result = OpenRouterClient().ask_json(
            system_prompt='Responde solo JSON {"app": str, "menus": [str], "fecha_visible": str|null}.',
            user_prompt="Describe la aplicación que muestra esta captura.",
            images_b64_png=[base64.b64encode(second).decode()],
        )
        print(f"Modelo {result['model']}: {time.monotonic() - started:.1f} s, {result['cost_usd']:.5f} USD ({result['cost_source']})")
        print(result["data"])
    print(f"Listo. Imágenes en {output}/")


if __name__ == "__main__":
    main()
