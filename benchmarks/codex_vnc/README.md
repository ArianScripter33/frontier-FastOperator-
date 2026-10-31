# Benchmark independiente VNC — propiedad de Codex

Claude conserva transporte, motor visual, API, persistencia y despliegue. Este directorio solo evalúa evidencia; no conecta escritorios, llama modelos, resetea datos ni gasta corridas oficiales.

## Orden de experimentos

Primero probar captura → clic inocuo → cambio visible. Después E3 (lectura), E5 (rechazo de homónimos), E1/E2 (escrituras) y E4 (exportación). Solo el operador de pruebas usa `__reset`/`__check`, fuera del runtime. Entregar al agente únicamente la instrucción y escritorio; nunca diff ni respuesta esperada.

Comparar A: Haiku visual; B: mismo operador con JeV visual selectivo; C: escalada selectiva. DeepSeek solo entra como operador visual si se verifica soporte de imágenes del ID exacto; como planificador textual requiere una percepción previa y hay que contar su costo y errores. Un proveedor estadounidense no demuestra región efectiva ni altera capacidades del modelo. Prompt caching requiere soporte, prefijo elegible y hits medidos; no equivale a memoria ni garantiza ahorro.

Mismos casos, instrucciones, estado inicial, resolución y presupuesto; guardar modelo/proveedor/versiones y motivo de escalada. Alternar orden, separar caché fría/caliente y repeticiones; no concluir superioridad general con cinco tareas. Métricas: acierto completo, falsos éxitos, efectos extra, duplicados observados, latencias de aceptación y total, costo medido/estimado/desconocido y costo por éxito incluyendo fallos. El scorador nunca certifica preparación oficial.

## Evidencia JSONL para score.py

Cada fila: `case_id` (E1–E5), `variant`, `result` (`estado`, `resumen`), `accept_seconds`, `elapsed_seconds`, `state_check` (respuesta literal del oráculo de práctica), `actions_after_terminal`, `secret_leak`, `cost_usd`, `cost_source` (`measured`, `estimated`, `unknown`). Los dos últimos observadores de seguridad deben venir de instrumentación independiente; ausencia no significa cero. No incluir secretos ni capturas con credenciales.

```sh
python3 score.py --evidence resultados.jsonl --cases /Users/arianstoned/Downloads/frontier-reto-2/pruebas
```

## Contexto y detección de cambios

Por tarea: instrucción inmutable, objetivos/IDs/filtros, prohibiciones, progreso, última pantalla, últimas acciones y resultado observado; diario de mutaciones separado. Entre tareas: solo estrategias con alcance/app y procedencia, revalidadas; reset invalida filas, coordenadas y transacciones. JSON es el formato, no la política de memoria.

Detectar cambio por discrepancia entre predicción de efecto y pantalla nueva, error de grounding/acción o incumplimiento de regla observada. Diferencia de píxeles sola confunde datos/banners con cambios de regla. Registrar antes/después, hipótesis y prueba; invalidar la habilidad afectada y volver a observar. No programar un disparador de hora como si fuera detección. Un cambio silencioso de regla puede requerir un caso con resultado esperado y no ser detectable solo mirando una pantalla.

Adversariales prioritarios: pantalla antigua; clic demasiado corto; reemplazo que concatena; campo incorrecto; nota con instrucciones hostiles; homónimo; escritura de resultado incierto; resumen numérico mal formado; memoria de otro escritorio; proveedor lento; eventos posteriores al terminal/deadline; costo ausente. Cien tareas es estrés sintético, no tamaño confirmado del set.

## Mensaje para Claude

Codex mantiene solo benchmarks/codex_vnc/. Cuando el worker pueda producir la evidencia anterior, ejecutar E3 y E5 primero. POST /tasks debe aceptar en menos de 2 s, no completar la tarea; worker separado con deadline efectivo. Antes de publicar terminada/fallida, cancelar la cola y cerrar VNC. 4:30 es duración máxima propuesta por tarea, no las 16:30. Los cinco minutos oficiales empiezan con la tarea; los eventos tardíos pueden caer sobre el siguiente escritorio reseteado.
