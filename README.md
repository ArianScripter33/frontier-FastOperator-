# Agente que opera lo que no tiene API

Recibe una tarea en lenguaje natural y un escritorio remoto, y opera la aplicación solo por pantalla, con ratón y teclado, por VNC. Reporta `terminada` o `fallida` con un resumen.

## Cómo funciona
1. `POST /tasks` guarda la tarea y arranca un hilo; responde enseguida.
2. El worker captura la pantalla tras el repintado (`vnc_client.py`, RFB propio sobre websocket).
3. Un modelo de visión propone pocas acciones; el código las valida (`screen_agent.py`).
4. Solo termina tras ver el resultado en una captura nueva. Una escritura no se repite.
5. A los 4:30 se detiene, cierra VNC y publica `fallida`.

Cada petición al modelo se reconstruye con la captura actual y un registro de progreso, así que el contexto no crece. SQLite (`store.py`) guarda por tarea estado, pasos, costo, tiempos y motivo de fallo (`GET /stats`), más estrategias generales por app, sin datos ni números, que el modelo revalida.

## Contrato
Todas las rutas de tareas exigen `Authorization: Bearer <token del equipo>`.
- `GET /health`
- `POST /tasks` con `{"tarea": "...", "escritorio": {"url": "wss://.../websockify", "password": "..."}}` devuelve `{"task_id": "..."}`
- `GET /tasks/{id}` devuelve `{"estado": "en_curso|terminada|fallida", "resumen": "..."}`

## Correr
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests
export OPENROUTER_API_KEY=... FRONTIER_TEAM_TOKEN=...
.venv/bin/python service.py
```

Las pruebas usan un escritorio falso y un modelo simulado: comprueban protocolo y reglas, no la calidad del modelo. Con credenciales en un `.env` local (ignorado por Git): `practice.py` corre las tareas de `pruebas/` y `smoke_remote.py <url>` prueba un servicio desplegado.

## Desplegar
El `Dockerfile` sirve en cualquier host de contenedores. Define `OPENROUTER_API_KEY` y `FRONTIER_TEAM_TOKEN`. El servicio escucha en `PORT`.

## Límites
- Una tarea en curso se pierde si el servicio se reinicia.
- El estado vive en disco local del contenedor, salvo que `FRONTIER_STATE_DIR` apunte a un volumen.
- La adaptación a otras apps no está demostrada: solo se ha probado sobre la app de práctica.
- CAPTCHAs externos quedan fuera.

## Procedencia
Motor de pantalla escrito durante el evento. `llm_client.py` y `telemetry.py` vienen de la preparación previa.
