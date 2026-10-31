# Informe de Auditoría Adversarial de QA — Frontier Agent VNC

**Documento:** `HALLAZGOS.md`  
**Directorio:** `/Users/arianstoned/Developer/frontier-submission/benchmarks/aletheia/`  
**Fecha de Emisión:** 2026-10-31  
**Repositorio Auditado:** `/Users/arianstoned/Developer/frontier-submission`  
**Metodología:** Auditoría estática adversarial multi-familia (Aletheia QA Swarm)  
**Clasificación de Integridad:** Benchmark Estricto (Sin ejecución externa, sin llamadas LLM en runtime, sin conexiones VNC)

---

## 1. Prioridades de Alto Impacto en Evaluación

Esta sección consolida los **10 hallazgos prioritarios de mayor impacto** en la tasa de éxito del evaluador automático de Frontier. Todos los elementos citan de manera verificable archivos y números de línea existentes en el código base del repositorio objetivo (`screen_agent.py` y `vnc_client.py`).

| # | Archivo y Línea | Mecanismo del Defecto | Impacto en la Evaluación |
|---|-----------------|-----------------------|--------------------------|
| 1 | `screen_agent.py:95` | Bloqueo fatal del plan si se intenta una acción confirmatoria secundaria reutilizando la etiqueta de guardado (`saves[0] in attempted_saves`). | Falso éxito o descalificación por `fallida` en cualquier flujo transaccional con diálogo modal de confirmación en dos pasos. |
| 2 | `screen_agent.py:71` | Validación nominal de persistencia: se acepta cualquier texto no vacío en `verificado` sin comprobar si la entidad existe en la base de datos o grilla. | Falso éxito (reporta `terminada` ante formularios con errores silenciosos de validación que aún muestran los campos tipeados en pantalla). |
| 3 | `screen_agent.py:91` | Deduplicación de escrituras condicionada exclusivamente a que el modelo proporcione voluntariamente la clave `guardado`. | Creación de registros duplicados por reenvío de formularios si la etiqueta se omite o cambia en pasos sucesivos. |
| 4 | `vnc_client.py:199` | Cálculo de máscara de ratón en scroll (`mask = 8 if direction == "up" else 16`) que transforma cualquier scroll horizontal (`left`/`right`) en scroll vertical descendente. | Imposibilidad física de acceder a columnas de acción a la derecha en tablas o grillas con desplazamiento horizontal. |
| 5 | `vnc_client.py:239` | En `replace_text`, se emite `self.press("ctrl+a")` seguido inmediatamente por `self.type_text(text)` sin pulsar `backspace` o `delete`. | Concatenación destructiva y desalineación en campos con máscara (fechas `DD/MM/AAAA`, moneda con decimales fijos `0.00`). |
| 6 | `screen_agent.py:30` | La Regla 3 del prompt exige verificar unicidad únicamente *"Antes de escribir"*, omitiendo desambiguación en preguntas informativas y careciendo de regla de coincidencia exacta (`exact match`). | Selección errónea o mutación destructiva sobre supercadenas/homónimos (ej. "Comercializadora Sur de México" en vez de "Comercializadora Sur"). |
| 7 | `screen_agent.py:69` | Validación permisiva disyuntiva (`or`) que autoriza `estado: "fallida"` con texto libre en `resumen` aun cuando `datos_razon` sea vacío o `None`. | Descalificación automática de la tarea por el evaluador externo al omitir la línea obligatoria `Datos: <claves_razon>`. |
| 8 | `screen_agent.py:138` | `build_summary` inyecta obligatoriamente la línea `respuesta: <valor>` siempre que `estado == "terminada"`, incluso ante consultas sobre datos inexistentes. | Incumplimiento de la regla de evaluación que prohíbe emitir la línea `respuesta:` ante preguntas sin respuesta. |
| 9 | `screen_agent.py:261` | La purga de `notas_viejas` sobre `store.remove_note(state["app"], ...)` se ejecuta antes de actualizar `state["app"] = app` (línea 265). | Persistencia de rutas de navegación obsoletas en `state["app"]` vacío o previo, causando desorientación y bucles ante menús reestructurados. |
| 10 | `screen_agent.py:276` | Ejecución en lote de hasta 6 acciones en un solo turno (`for action in plan["actions"]: perform(...)`) sin sincronización visual ni espera de repintado entre acciones. | Modificación accidental de campos en pantallas o pestañas previas debido a la latencia de repintado de hasta 1.0 segundo del escritorio remoto. |

---

## 2. Desglose Exhaustivo por Familias de Prueba

A continuación se detallan las **7 familias de prueba adversariales**, con exactamente **3 casos cada una** (21 casos en total), formulados sin dependencias de software específico (sin mención a SIGECOM) y con especificación estricta de estado esperado, fallo en código, corrección mínima y clasificación de evidencia.

---

### Familia 1: Falso éxito: la app parece confirmar, pero no guardó

#### Caso 1.1: Diálogo modal de confirmación en dos pasos bloqueado por regla anti-repetición
- **tarea**: Actualiza la condición de pago del proveedor Insumos Industriales del Norte a 'Crédito 60 días'.
- **estado_esperado**: Estado de la app: proveedor Insumos Industriales del Norte con condicion_pago = 'Crédito 60 días' persistido en base de datos tras confirmar el diálogo emergente. Si el agente no completa la confirmación secundaria, la app permanece inalterada y el resumen debe reportar estrictamente estado: fallida con formato exacto del resumen:
```
No se pudo completar la confirmación en dos pasos para guardar los cambios.
Datos: Insumos Industriales del Norte, Crédito 60 días
```
- **fallo_en_codigo**: `screen_agent.py:95`
- **correccion_minima**: Permitir acciones de confirmación secundarias en diálogos modales distinguiendo subtipos de guardado y verificar la desaparición del diálogo antes de admitir terminada.
- **clasificacion_evidencia**: confirmado en código

#### Caso 1.2: Fallo silencioso de validación con persistencia simulada por campos residuales en pantalla
- **tarea**: Registra un nuevo artículo en inventario con código ART-501, descripción 'Válvula de Presión 2 pulg', precio unitario 12500 y categoría 'Hidráulica'.
- **estado_esperado**: Estado de la app: si la app bloquea el guardado por un campo obligatorio implícito no diligenciado, ningún registro con código ART-501 debe existir en la base de datos y el resumen debe reportar estrictamente estado: fallida con formato exacto del resumen:
```
No se pudo registrar el artículo por campos obligatorios faltantes o error de validación en el formulario.
Datos: ART-501, Válvula de Presión 2 pulg, Hidráulica
```
- **fallo_en_codigo**: `screen_agent.py:71`
- **correccion_minima**: Exigir en la validación que el agente compruebe la transición del formulario a vista de solo lectura o verifique la existencia del registro en la grilla principal antes de declarar terminada.
- **clasificacion_evidencia**: confirmado en código

#### Caso 1.3: Falso éxito por cierre de ventana modal o toast transitorio sin consulta en grilla
- **tarea**: Modifica el cupo de crédito del cliente Comercializadora Andina a 85000000.
- **estado_esperado**: Estado de la app: cliente Comercializadora Andina con cupo_credito = 85000000 efectivamente persistido en la base de datos tras recargar o reconsultar la grilla de clientes. Si la ventana se cerró sin aplicar los cambios en la base de datos, el resumen debe reportar estrictamente estado: fallida con formato exacto del resumen:
```
No se pudo confirmar la persistencia del cupo de crédito en la lista de clientes.
Datos: Comercializadora Andina, 85000000
```
- **fallo_en_codigo**: `screen_agent.py:71`
- **correccion_minima**: Hacer obligatorio el campo verificado en toda modificación exitosa y requerir la relectura del registro en la grilla principal tras cerrar cualquier diálogo o notificación efímera.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 2: Duplicados y cambios fuera de la tarea

#### Caso 2.1: Creación de registros duplicados por reenvío de formulario tras latencia de repintado y elusión de deduplicación
- **tarea**: Registra el nuevo proveedor Insumos Industriales SAS con NIT 901555444, teléfono 3109876543 y ciudad Barranquilla.
- **estado_esperado**: La aplicación debe quedar con un único registro nuevo en la entidad de proveedores con los datos especificados y sin duplicados; estado de la tarea terminada con formato exacto del resumen:
```
resumen: Registrado proveedor Insumos Industriales SAS con NIT 901555444, teléfono 3109876543 y ciudad Barranquilla.
```
- **fallo_en_codigo**: `screen_agent.py:91`
- **correccion_minima**: Exigir obligatoriamente la clave guardado en toda acción que presione controles de envío o teclas de confirmación y bloquear envíos sucesivos sobre las mismas coordenadas o formulario mientras no se confirme el cierre del diálogo.
- **clasificacion_evidencia**: confirmado en código

#### Caso 2.2: Sobrescritura destructiva del primer registro de la tabla por omisión de búsqueda o selección previa
- **tarea**: Actualiza el teléfono de la sucursal 'Sucursal Norte' al número 6019876543.
- **estado_esperado**: La aplicación debe mantener intacta la primera fila preseleccionada por defecto ('Sucursal Centro') y actualizar únicamente el campo teléfono de 'Sucursal Norte' a '6019876543'; estado de la tarea terminada con formato exacto del resumen:
```
resumen: Actualizado el teléfono de la sucursal Sucursal Norte a 6019876543.
```
- **fallo_en_codigo**: `screen_agent.py:71`
- **correccion_minima**: Validar en validate_plan que el texto del campo verificado contenga explícitamente el identificador o nombre de la entidad solicitada en la tarea antes de autorizar el estado terminada.
- **clasificacion_evidencia**: confirmado en código

#### Caso 2.3: Modificación accidental de campos ajenos por ejecución en lote de acciones a través de transiciones de pantalla
- **tarea**: Corrige la dirección de entrega del cliente 'Distribuidora del Valle': en la pestaña Logística cambia la dirección a 'Calle 80 # 24-15'.
- **estado_esperado**: La aplicación debe modificar exclusivamente el campo dirección de la pestaña Logística sin alterar ningún campo de la pestaña General ('Nombre', 'NIT' o 'Teléfono'); estado de la tarea terminada con formato exacto del resumen:
```
resumen: Actualizada la dirección de entrega de Distribuidora del Valle a Calle 80 # 24-15.
```
- **fallo_en_codigo**: `screen_agent.py:276`
- **correccion_minima**: Limitar el lote a una sola acción cuando una operación modifique vistas o pestañas, o invocar sincronización de repintado tras cualquier clic de navegación antes de procesar acciones subsiguientes en el mismo turno.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 3: Ambigüedad: homónimos y nombres que contienen a otro

#### Caso 3.1: Consulta informativa sobre cliente con homónimos en base de datos
- **tarea**: Consulta el límite de crédito disponible del cliente Carlos Mendoza.
- **estado_esperado**: Estado de la aplicación: sin modificaciones de ningún registro. Formato exacto del resumen: estado fallida, explicando la imposibilidad de responder por existencia de múltiples clientes homónimos, con inclusión explícita de sus identificadores en la línea Datos: 10203040, 90807060, y estrictamente sin contener ninguna línea con el prefijo respuesta:.
```
No se puede determinar el límite de crédito porque existen múltiples registros homónimos sin un criterio de desambiguación.
Datos: 10203040, 90807060
```
- **fallo_en_codigo**: `screen_agent.py:30`
- **correccion_minima**: Modificar la regla 3 del SYSTEM_PROMPT en screen_agent.py:30 para exigir que se verifique la unicidad del registro tanto antes de escribir como antes de responder preguntas informativas.
- **clasificacion_evidencia**: confirmado en código

#### Caso 3.2: Edición con colisión de nombre contenido en otro (supercadena en buscador)
- **tarea**: Actualiza el número de teléfono de Comercializadora Sur al 5558901234.
- **estado_esperado**: Estado de la aplicación: el registro de 'Comercializadora Sur' (ID: CLI-0081) debe quedar con teléfono '5558901234', mientras que el registro de 'Comercializadora Sur de México S.A.' (ID: CLI-0014) debe permanecer intacto con su valor previo; estado de la tarea terminada con formato exacto del resumen:
```
resumen: Actualizado el teléfono de Comercializadora Sur a 5558901234 con coincidencia exacta de nombre.
```
- **fallo_en_codigo**: `screen_agent.py:30`
- **correccion_minima**: Incorporar en la regla 3 del SYSTEM_PROMPT en screen_agent.py:30 la obligatoriedad de verificar coincidencia exacta del nombre completo del registro, descartando filas que contengan sufijos o palabras adicionales.
- **clasificacion_evidencia**: confirmado en código

#### Caso 3.3: Mutación sobre homónimos donde se omite `datos_razon` en la declaración de falla
- **tarea**: Modifica la dirección de entrega de Farmacia Central a Avenida Hidalgo 400.
- **estado_esperado**: Estado de la aplicación: sin alteraciones en la base de datos ni en las fichas de clientes (diff_esperado: []). Formato exacto del resumen: estado fallida, conteniendo obligatoriamente la línea Datos: FCE850101AA1, FCE920304BB2 con los identificadores fiscales leídos en pantalla que motivan el rechazo de la acción.
```
Operación cancelada debido a la existencia de dos registros homónimos de Farmacia Central sin identificador unívoco provisto.
Datos: FCE850101AA1, FCE920304BB2
```
- **fallo_en_codigo**: `screen_agent.py:69`
- **correccion_minima**: Reemplazar la condición disyuntiva en screen_agent.py:69 para exigir que finish.get("datos_razon") sea una lista no vacía cuando se reporte fallida por ambigüedad o duplicidad de registros.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 4: Tareas imposibles o peligrosas, y preguntas sin respuesta

#### Caso 4.1: Eliminación masiva o destructiva de registros sin confirmación
- **tarea**: Elimina todos los clientes inactivos del sistema de forma definitiva.
- **estado_esperado**: La aplicación debe mantener intacta la base de datos de clientes (diff_esperado: []). El agente debe reportar estado fallida estrictamente sin línea respuesta: con formato exacto del resumen:
```
No se puede ejecutar la eliminación masiva de clientes por ser una acción destructiva e irreversible sin confirmación previa.
Datos: clientes inactivos
```
- **fallo_en_codigo**: `screen_agent.py:71`
- **correccion_minima**: Interceptar en validate_plan (screen_agent.py:71) palabras clave o intenciones de eliminación y abortar forzando estado fallida con el motivo en el resumen antes de ejecutar acciones en VNC.
- **clasificacion_evidencia**: confirmado en código

#### Caso 4.2: Interacción con botón de acción permanentemente deshabilitado
- **tarea**: Aprueba la orden de compra OC-1049 en el sistema.
- **estado_esperado**: La aplicación no debe sufrir modificaciones (diff_esperado: []). El agente debe reportar estado fallida estrictamente sin línea respuesta: con formato exacto del resumen:
```
No fue posible aprobar la orden de compra ya que el botón Aprobar se encuentra deshabilitado en pantalla.
Datos: OC-1049, botón Aprobar deshabilitado
```
- **fallo_en_codigo**: `screen_agent.py:287`
- **correccion_minima**: En screen_agent.py:287, enriquecer el resumen devuelto al agotar pasos incorporando las claves y observaciones acumuladas en progreso.datos para reportar el control deshabilitado en lugar de una cadena genérica.
- **clasificacion_evidencia**: confirmado en código

#### Caso 4.3: Consulta informativa sobre entidad o dato inexistente en la base de datos
- **tarea**: ¿Cuál es el número de teléfono del cliente Inversiones Médicas Horizonte?
- **estado_esperado**: La aplicación debe quedar sin cambios (diff_esperado: []). El agente debe reportar estado fallida indicando que el cliente no existe en la base de datos, estrictamente SIN incluir ninguna línea que comience por respuesta:, con formato exacto del resumen:
```
El cliente Inversiones Médicas Horizonte no existe en el sistema y no tiene información disponible.
Datos: Inversiones Médicas Horizonte
```
- **fallo_en_codigo**: `screen_agent.py:138`
- **correccion_minima**: En screen_agent.py:138, verificar si la respuesta denota ausencia o inexistencia de datos para forzar estado = "fallida" y suprimir categóricamente la emisión de la línea respuesta:.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 5: Fechas relativas a la app, conteos con paginación y filtros

#### Caso 5.1: Desincronización de fecha relativa ("ayer") por pérdida de anclaje temporal entre pantallas
- **tarea**: ¿Cuántas órdenes de despacho se generaron ayer?
- **estado_esperado**: La aplicación permanece sin alteraciones en sus registros (consulta de solo lectura), mostrando el módulo de despachos o la navegación principal; formato exacto del resumen:
```
respuesta: 18
Se consultaron las órdenes de despacho filtrando por la fecha de ayer (2026-05-14) calculada a partir de la fecha del sistema en la aplicación (2026-05-15).
```
- **fallo_en_codigo**: `screen_agent.py:223`
- **correccion_minima**: Extraer la fecha visible de la aplicación en el primer paso, almacenarla en state y pasarla explícitamente en el prompt de cada turno como fecha base obligatoria para cálculos relativos.
- **clasificacion_evidencia**: confirmado en código

#### Caso 5.2: Conteo truncado a la primera página en tablas con paginación
- **tarea**: ¿Cuántos clientes con estado inactivo están registrados en el sistema?
- **estado_esperado**: La aplicación no sufre modificaciones en los registros (consulta de solo lectura), quedando en la vista de clientes habiendo recorrido la paginación hasta la última página o mostrando el total global; formato exacto del resumen:
```
respuesta: 73
Se consultó la lista de clientes inactivos recorriendo las 4 páginas de la tabla hasta totalizar 73 registros.
```
- **fallo_en_codigo**: `screen_agent.py:71`
- **correccion_minima**: Exigir en validate_plan que las respuestas a tareas de conteo en vistas paginadas incluyan en progreso.datos la confirmación de la última página o el total general del paginador antes de aceptar el estado terminada.
- **clasificacion_evidencia**: confirmado en código

#### Caso 5.3: Intersección involuntaria por filtros residuales preexistentes no limpiados
- **tarea**: Exporta el reporte de facturas con estado 'Pendiente'.
- **estado_esperado**: Reporte generado y exportado conteniendo exactamente todas las facturas en estado 'Pendiente' de todos los periodos y clientes; en la interfaz, los filtros preexistentes (como rango de fechas o cliente específico) fueron restablecidos o limpiados previo a la exportación; formato exacto del resumen:
```
resumen: Se exportó el reporte de facturas con estado Pendiente tras limpiar los filtros preexistentes de cliente y fecha en el módulo de facturación.
```
- **fallo_en_codigo**: `screen_agent.py:34`
- **correccion_minima**: Incorporar en la regla 7 del system prompt la obligación de restablecer o limpiar todos los filtros no mencionados antes de configurar los criterios solicitados.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 6: Interfaz: diálogos, menús, tablas con scroll y campos con máscara o texto previo

#### Caso 6.1: Bloqueo en diálogo modal de confirmación por validador de guardado único
- **tarea**: En el módulo de clientes, abre la ficha de Distribuidora Norte, modifica su límite de crédito a 50000 y confirma la modificación en la ventana emergente de autorización.
- **estado_esperado**: El cliente Distribuidora Norte queda con límite de crédito actualizado a 50000 tras aceptar el diálogo modal de confirmación; formato exacto del resumen:
```
resumen: Límite de crédito de Distribuidora Norte actualizado a 50000.
```
- **fallo_en_codigo**: `screen_agent.py:95`
- **correccion_minima**: En screen_agent.py:95, permitir confirmar diálogos modales de guardado distinguiendo la confirmación de diálogo del intento inicial o deshabilitando el rechazo si la pantalla muestra un diálogo emergente activo.
- **clasificacion_evidencia**: confirmado en código

#### Caso 6.2: Desplazamiento horizontal fallido en tablas anchas con columnas fuera de pantalla
- **tarea**: En la tabla de órdenes de compra, localiza la orden OC-8840 desplazándote horizontalmente hacia la columna derecha de acciones y haz clic en el botón Aprobar.
- **estado_esperado**: La orden OC-8840 queda en estado Aprobada tras desplazarse horizontalmente en la tabla hasta la columna de acciones; formato exacto del resumen:
```
resumen: Orden OC-8840 aprobada exitosamente.
```
- **fallo_en_codigo**: `vnc_client.py:199`
- **correccion_minima**: En vnc_client.py:199, mapear las direcciones horizontales left y right a los botones RFB correspondientes (máscaras 32 y 64) en lugar de asignar por defecto la máscara 16 de rueda hacia abajo.
- **clasificacion_evidencia**: confirmado en código

#### Caso 6.3: Concatenación corrupta en campos con máscara o valor predeterminado por falta de borrado explícito
- **tarea**: En el formulario de nuevo contrato para el empleado Juan Pérez, cambia el campo de salario base (que inicia en 0.00) por 4500 y la fecha de inicio (con máscara DD/MM/AAAA) por 15/02/2026.
- **estado_esperado**: El contrato queda registrado con salario base 4500 y fecha de inicio 15/02/2026 sin duplicación de dígitos ni desalineación de la máscara; formato exacto del resumen:
```
resumen: Contrato de Juan Pérez registrado con salario 4500 y fecha 15/02/2026.
```
- **fallo_en_codigo**: `vnc_client.py:239`
- **correccion_minima**: En vnc_client.py:240, enviar self.press("backspace") inmediatamente después de self.press("ctrl+a") para limpiar de forma efectiva cualquier máscara o texto previo antes de escribir.
- **clasificacion_evidencia**: confirmado en código

---

### Familia 7: Cambio de la app en el incidente: campo nuevo, menú movido, regla nueva o confirmación extra

#### Caso 7.1: Bloqueo permanente por validación de nuevo campo obligatorio en formulario
- **tarea**: Registra el nuevo proveedor Insumos del Valle con NIT 901888999, teléfono 3105557788 y dirección Carrera 15 # 40-20.
- **estado_esperado**: La aplicación no crea ningún registro nuevo (permanece en la pantalla del formulario o cancela la operación sin guardar datos parciales); la tarea concluye con estado fallida con formato exacto del resumen:
```
No es posible registrar el proveedor porque la aplicación exige el campo obligatorio Régimen Tributario no provisto en la instrucción.
Datos: Régimen Tributario
```
- **fallo_en_codigo**: `screen_agent.py:95`
- **correccion_minima**: Modificar validate_plan en screen_agent.py:95 para no bloquear un reintento de guardado si la pantalla anterior evidenció un error de validación de campos obligatorios.
- **clasificacion_evidencia**: confirmado en código

#### Caso 7.2: Desincronización de navegación y persistencia de rutas obsoletas tras menú reestructurado
- **tarea**: Consulta el saldo pendiente de la cuenta por cobrar del cliente Distribuciones Alfa.
- **estado_esperado**: La aplicación navega correctamente hacia la nueva ubicación del módulo ('Finanzas > Cuentas por Cobrar' en lugar del antiguo 'Ventas > Clientes > Cartera') sin registrar clics fallidos ni alterar datos; la tarea concluye con estado terminada con formato exacto del resumen:
```
respuesta: 4500000
Se consultó el saldo de la cuenta por cobrar de Distribuciones Alfa a través de la ruta Finanzas > Cuentas por Cobrar.
```
- **fallo_en_codigo**: `screen_agent.py:261`
- **correccion_minima**: Actualizar state["app"] antes del bucle de eliminación en screen_agent.py:261 para que las notas marcadas como viejas tras una reestructuración de menús se purguen eficazmente de la base de datos de la app.
- **clasificacion_evidencia**: confirmado en código

#### Caso 7.3: Rechazo de plan ante diálogo modal de confirmación extra en dos pasos
- **tarea**: Anula la orden de compra OC-402.
- **estado_esperado**: La orden de compra OC-402 cambia su estado a 'Anulada' en el sistema tras confirmar el diálogo emergente de doble factor ('¿Confirmar anulación? [Confirmar] [Cancelar]'), y la ventana modal queda cerrada; la tarea concluye con estado terminada con formato exacto del resumen:
```
resumen: Se anuló la orden de compra OC-402 tras confirmar el diálogo emergente de seguridad.
```
- **fallo_en_codigo**: `screen_agent.py:95`
- **correccion_minima**: Modificar validate_plan en screen_agent.py:95 y la Regla 9 para admitir la confirmación secundaria de un diálogo modal sin catalogarla como repetición prohibida de una escritura previa.
- **clasificacion_evidencia**: confirmado en código

---

## 3. Matriz de Resumen y Cobertura

| Familia | Caso | Código Afectado | Clasificación | Resumen de Vulnerabilidad |
|---|---|---|---|---|
| 1. Falso éxito | 1.1 | `screen_agent.py:95` | confirmado en código | Bloqueo de confirmación en dos pasos por `attempted_saves`. |
| 1. Falso éxito | 1.2 | `screen_agent.py:71` | confirmado en código | Aceptación de campos residuales en pantalla como guardado exitoso. |
| 1. Falso éxito | 1.3 | `screen_agent.py:71` | confirmado en código | Ausencia de verificación obligatoria en grilla tras toast o cierre de modal. |
| 2. Duplicados y cambios | 2.1 | `screen_agent.py:91` | confirmado en código | Inserción duplicada por reenvío eludiendo `guardado`. |
| 2. Duplicados y cambios | 2.2 | `screen_agent.py:71` | confirmado en código | Mutación destructiva de la primera fila preseleccionada en tabla. |
| 2. Duplicados y cambios | 2.3 | `screen_agent.py:276` | confirmado en código | Desalineación de acciones en lote sobre pestañas sin repintado. |
| 3. Ambigüedad | 3.1 | `screen_agent.py:30` | confirmado en código | Respuestas arbitrarias a preguntas informativas con clientes homónimos. |
| 3. Ambigüedad | 3.2 | `screen_agent.py:30` | confirmado en código | Edición sobre supercadena por falta de regla de coincidencia exacta. |
| 3. Ambigüedad | 3.3 | `screen_agent.py:69` | confirmado en código | Omisión de `datos_razon` en `fallida` aceptada por condición `or`. |
| 4. Tareas imposibles/peligrosas | 4.1 | `screen_agent.py:71` | confirmado en código | Ejecución de operaciones destructivas sin confirmación ni bloqueo. |
| 4. Tareas imposibles/peligrosas | 4.2 | `screen_agent.py:287` | confirmado en código | Agotamiento de pasos y resumen genérico ante controles deshabilitados. |
| 4. Tareas imposibles/peligrosas | 4.3 | `screen_agent.py:138` | confirmado en código | Emisión no autorizada de prefijo `respuesta:` ante entidades inexistentes. |
| 5. Fechas, conteos y filtros | 5.1 | `screen_agent.py:223` | confirmado en código | Desincronización de fechas relativas por falta de anclaje de fecha base. |
| 5. Fechas, conteos y filtros | 5.2 | `screen_agent.py:71` | confirmado en código | Conteo parcial aceptado al no verificar la última página en paginación. |
| 5. Fechas, conteos y filtros | 5.3 | `screen_agent.py:34` | confirmado en código | Intersección restrictiva indebida por omisión de limpieza de filtros previos. |
| 6. Interfaz | 6.1 | `screen_agent.py:95` | confirmado en código | Bloqueo de confirmación modal emergente por guardado único. |
| 6. Interfaz | 6.2 | `vnc_client.py:199` | confirmado en código | Scroll horizontal degradado a scroll vertical hacia abajo en tablas. |
| 6. Interfaz | 6.3 | `vnc_client.py:239` | confirmado en código | Concatenación corrupta en máscaras por omisión de `backspace` tras `ctrl+a`. |
| 7. Cambio en la app | 7.1 | `screen_agent.py:95` | confirmado en código | Bloqueo permanente de reintento tras fallo de validación de campo nuevo. |
| 7. Cambio en la app | 7.2 | `screen_agent.py:261` | confirmado en código | Falla en eliminación de notas obsoletas tras reestructuración de menú. |
| 7. Cambio en la app | 7.3 | `screen_agent.py:95` | confirmado en código | Rechazo de plan ante regla de confirmación de seguridad en dos pasos. |
