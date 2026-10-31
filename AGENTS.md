# Coordinación de agentes — frontier-submission

Antes de trabajar consulta `python3 ../frontier-cdmx/mission_clock.py now` y las instrucciones del proyecto en `../frontier-cdmx/AGENTS.md`.
Hasta cerrar el diseño, Claude es el único editor de `../frontier-cdmx/DESIGN.md` y `architecture.png`. No implementar el agente durante esa fase.
Un solo editor del motor a la vez; delimitar archivos antes de cada trabajo. OpenScion serializa commits, no evita conflictos entre ediciones simultáneas.

## Commits

Usa archivos individuales que hayas revisado, nunca `git add -A`:

```sh
python3 tools/team.py commit claude "Describe el cambio" archivo.py
python3 tools/team.py commit codex "Describe el cambio" archivo.py
python3 tools/team.py commit gemini "Describe el cambio" archivo.py
python3 tools/team.py status
```

Prefijos: 🎃 Claude, 🔵 Codex, 🟢 Gemini. Identifican al agente declarado, sin cambiar el autor Git humano ni demostrar identidad criptográfica. No atribuir a otro agente un trabajo propio.
Cada commit requiere validación apropiada y descripción de su diff en una frase por archivo.
No secretos, memoria de ejecución, logs ni push de frontier-cdmx. No modificar autoría ni historial existente.

## OpenScion y persistencia

Git conserva el historial público requerido por el reto. El wrapper replica solo snapshots ya committed a OpenScion local, con el autor del agente, emoji y SHA Git.
OpenScion está fijado al commit `00e92ab9c2a9985f39a64636b4b6c5c4bb583916` de tinyhumansai/openscion. Sus binarios locales están en `../frontier-cdmx/.runtime/openscion-source/target/debug`.
Esta versión guarda el servidor en memoria y no respeta `.gitignore` al importar directorios; por eso nunca se importa el checkout directo. El espejo contiene solo archivos de `git archive` y el servidor escucha únicamente en loopback.
Después de un reinicio se reconstruye el espejo desde Git con `python3 tools/team.py sync`. Si falla tras un commit Git, no repitas el commit: ejecuta `sync`.
No usar `opnscn commit` directamente sobre el checkout compartido; usa el wrapper para serializar commits y seleccionar archivos.

## Exportación del motor

Esta carpeta comienza con coordinación, no con un agente listo. A partir de ejecución, exportar el motor a un directorio temporal nuevo y revisar antes de copiar sus archivos aquí; el exportador rechaza destinos existentes. Preservar `.git`, `.githooks`, `tools/team.py` y este contrato. No sobrescribir trabajo de otros agentes. El runtime anterior necesita adaptación a VNC y al contrato asíncrono oficial; no afirmar que ya cumple.
