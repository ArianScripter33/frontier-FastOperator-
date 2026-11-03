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

## Métricas Reales en Evaluación Oculta
Set oculto en una aplicación no vista antes. Se usaron 2 de las 3 corridas: la 1 tuvo 34 tareas y la 2, 42.
- **Corrida 2 (final):** **28 de 42** tareas completadas (**66.7%**). Fáciles 12/13 (92%), regulares 12/17 (71%), difíciles 4/12 (33%). Mediana de **1 min 29 s** por tarea, con un límite de 5 min.
- **Corrida 1:** **15 de 34** (44.1%). Fáciles 6/10, regulares 6/14, difíciles 3/10. Mediana de 1 min 18 s. Arrancó a las 15:23, después del incidente y antes de adaptar el agente.
- **Fallos según el portal (estado reportado · cambios esperados · respuesta o razón):** corrida 1: 14 · 11 · 7; corrida 2: 8 · 7 · 4.
- **Costo según `/stats` del servicio:** 0.30 USD en la corrida 1 y 0.40 USD en la corrida 2 (a las 18:12, con una tarea aún en curso).
- **Cifra retirada:** "10 de 17 en vivo" era un parcial de la corrida 2, no un resultado.
- **Latencia:** el portal midió `GET /health` en 196 ms al validar (15:23). `POST /tasks` respondió en 0.37 s en la prueba remota (límite: 2 s).
- **Práctica local:** 5 de 5 según `/__check` antes del incidente (`evidencia/practica_pre_incidente.json`). Después del incidente solo se volvió a correr E1, que pasó; el resto no se volvió a medir.

## Resiliencia ante Incidente (GUI Drift a las 15:00 h)
A las 15:00 el entorno actualizó la aplicación a un tema de alto contraste con botones reubicados en pestañas secundarias y modales de bienvenida bloqueando el foco:
- **Diagnóstico por Telemetría:** en la corrida 1, el agente se declaró fallido en 17 tareas (según `/stats`); en la corrida 2, ya con el parche, en 10. La hipótesis fue que, sin encontrar los controles en la vista raíz, prefería no hacer clic a ciegas antes que dañar registros.
- **Adaptación en Caliente (`commit f3cbce6`):**
  - *Regla 2:* Cierre preventivo de modales con botón de cierre o tecla `escape`.
  - *Regla 4:* Exploración obligatoria de pestañas visibles cuando el control principal no está en el lienzo inicial.
  - *Regla 9:* Búsqueda exhaustiva en tablas con scroll vertical antes de declarar fallo.
  - *Manejo de Formularios:* Inyección de `BackSpace` (`0xFF08`) en `replace_text` para vaciar campos antes de escribir.

## Arquitectura de Frontera e Investigación Experimental (Fork Aislado)
**No desplegado.** Esta sección describe un fork aparte que no corrió en el set oculto. Este repositorio tiene JEV apagado por defecto (`FRONTIER_USE_JEV=0`) y el operador es Claude Haiku 5.5. La prueba que cita, `tests/test_jev_hybrid.py`, está en ese fork, no aquí. Cifras reportadas por el fork (no reproducidas en este repositorio):
- **TypeSafe JEV 1.14 (Oráculo Táctico):** Resolución nativa 1280×800 con header `TypeSafe-Danger-Zone-Images: true`. Latencia TTFT de **326.8 ms** (3.8x más rápido que Haiku) a **0.000015 USD** por decisión táctica.
- **Claude Haiku 5.5 (Operador Motor Primario):** TTFT de **971.0 ms** con pixel grounding exacto y 100% de OCR sobre controles ERP densos.
- **DeepSeek V4.1 Flash 1017 (Árbitro Semántico):** **2.14x más barato** en visión (0.000089 USD/turno), ideal para desempate semántico en pantallas estancadas, pero con varianza espacial (25-80 px) que descarta su uso para clics motores directos.

## Límites
- Una tarea en curso se pierde si el servicio se reinicia.
- El estado vive en disco local del contenedor, salvo que `FRONTIER_STATE_DIR` apunte a un volumen.
- Con 28 de 42 en el set oculto, el agente no resuelve todas las tareas de una aplicación nueva. Las difíciles fueron 4 de 12.
- CAPTCHAs externos quedan fuera.

## Procedencia
Motor de pantalla escrito durante el evento. `llm_client.py` y `telemetry.py` vienen de la preparación previa.
