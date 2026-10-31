# Coordinación paralela — revisión del 31 de octubre, 13:30 CDMX

Claude conserva la edición de `practice.py`, transporte, motor, API y despliegue. Codex conserva `benchmarks/codex_vnc/` y hace revisión independiente de solo lectura. Solo un operador usa el escritorio: ninguna ejecución simultánea de VNC, reset o check. Este documento no certifica resultados.

## Corrección para Claude: práctica sin oráculo

Observado en `practice.py`: ante cualquier HTTPError de reset se continúa sin oráculo, incluso en E1/E2/E4; `passed = (not oracle or ...)` convierte esa ausencia en aprobación y la lista vacía imprime `app: ok`.

Corrección delimitada, sin cambiar el motor: por defecto abortar el caso si reset falla. Si se conserva un modo diagnóstico explícito, permitir únicamente E3/E5, marcar `pass: null` y mostrar `SIN VALIDAR`; nunca contar esos casos como aprobados. No llamar inválido al token ante un 500/429. Comprobar el primer número de la única línea `respuesta:` en vez de buscar `45` como subcadena: `respuesta: 145` debe fallar. Validación local con respuestas HTTP simuladas, sin gastar modelos ni tocar el escritorio.

## Reparto inmediato

- Arian: confirmar con staff hora del incidente y si ya ocurrió; crear/iniciar sesión en GitHub y Railway mientras corre la práctica.
- Claude: ejecutar las cinco prácticas con reset/check autenticados, conservar evidencia, corregir el runner y preparar el servicio. Publicar solo resultados comprobados.
- Codex: auditar contrato/despliegue sin mutaciones, revisar evidencia y preparar casos adversariales separados. No gastar corridas oficiales ni lanzar otro worker.

## Evidencia y hora del incidente

Los resultados E3/E5 pegados por Arian corresponden a ejecución real según ese reporte, con estado/resumen esperado, pero carecen de check de estado de la app. No son dos aprobaciones completas. La hora del incidente está pendiente de confirmación; ver capturas en cada paso no demuestra adaptación a una regla silenciosa. Sin un antes conservado no se afirmará una comparación antes/después.

Antes de despliegue: comprobar autenticación exigida por el contrato, POST/GET por HTTP, límite efectivo y cese de eventos, reinicio del proceso y almacenamiento. Una configuración Docker correcta no prueba accesibilidad pública ni supervivencia de tareas al reinicio.

## Bloqueador encontrado por revisión independiente

La revisión de solo lectura encontró que `screen_agent.py:260–267` comprueba el deadline antes de cada acción, pero `vnc_client.py:210–216` escribe carácter por carácter con pausas sin deadline/cancelación. `validate_plan` solo exige que el texto sea string (`screen_agent.py:83–84`). Una escritura larga puede superar el tiempo restante aunque haya empezado dentro del límite. Claude debe propagar deadline/cancelación al transporte y comprobarlos durante la escritura, con liberación de teclas/cierre apropiados; limitar longitud ayuda, pero no sustituye comprobar el tiempo restante. Verificar con reloj/transporte simulados que no haya eventos tras el deadline, sin usar el escritorio real. Es un defecto confirmado de control; no se observó un evento tardío real.

Otros hallazgos estáticos para Claude, por prioridad:

- Reinicio: `Dockerfile:6` usa `/tmp` y `service.py:54` workers daemon; no hay recuperación de trabajos. Sin volumen se pierden IDs al reemplazar contenedor; con volumen las tareas interrumpidas pueden quedar `en_curso`. Persistir SQLite y marcar interrumpidas como `fallida` al arrancar, sin repetir acciones.
- Concurrencia: cada POST lanza un worker (`service.py:47–56`) sin exclusión por escritorio. Reservar escritorio al aceptar y rechazar una segunda tarea ocupada. El daño por acciones intercaladas es un riesgo, no un resultado medido.
- Salud: `service.py:43` devuelve siempre 200, aunque falten credenciales. Comprobar configuración/readiness sin llamadas pagadas. `/health` es público; que el contrato diga que el evaluador envía token no establece por sí solo que rechazar consultas sin él sea obligatorio.
- Correcto por inspección: bind `0.0.0.0`, variable `PORT` y ACK independiente del modelo. Pendiente medición desde internet en Railway.
