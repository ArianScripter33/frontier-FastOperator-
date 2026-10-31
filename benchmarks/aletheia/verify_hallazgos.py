#!/usr/bin/env python3
"""
verify_hallazgos.py — Validador Programático de Integridad y Cumplimiento de HALLAZGOS.md

Verifica los siguientes requisitos del benchmark adversarial Aletheia:
a) Existencia de HALLAZGOS.md.
b) Presencia exacta de las 7 familias de prueba y exactamente 21 casos (3 por familia).
c) Existencia en cada caso de los campos obligatorios: tarea, estado_esperado, resumen,
   fallo en código, corrección mínima y clasificación de evidencia (confirmado en código o hipótesis).
d) Ausencia de menciones a "SIGECOM" en los campos tarea.
e) Sección inicial de prioridades con <= 10 elementos, todos citando archivo y línea
   demostrables existentes en el repositorio objetivo.
f) Verificación de integridad mediante git: comprobar con `git status --porcelain` que
   NO se haya modificado ningún archivo fuente fuera de `benchmarks/aletheia/`.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/arianstoned/Developer/frontier-submission").resolve()
BENCHMARKS_DIR = REPO_ROOT / "benchmarks" / "aletheia"
HALLAZGOS_PATH = BENCHMARKS_DIR / "HALLAZGOS.md"

EXPECTED_FAMILIES = [
    "Falso éxito",
    "Duplicados y cambios fuera de la tarea",
    "Ambigüedad: homónimos y nombres que contienen a otro",
    "Tareas imposibles o peligrosas, y preguntas sin respuesta",
    "Fechas relativas a la app, conteos con paginación y filtros",
    "Interfaz: diálogos, menús, tablas con scroll y campos con máscara o texto previo",
    "Cambio de la app en el incidente: campo nuevo, menú movido, regla nueva o confirmación extra",
]

PRE_AUDIT_BASELINE_MODIFIED = {
    "config.py",
    "llm_client.py",
    "screen_agent.py",
    "tests/test_agent.py",
    "vnc_client.py",
}


def log(msg: str):
    print(f"[VERIFY] {msg}")


def fail(msg: str):
    print(f"[ERROR] VIOLACIÓN DETECTADA: {msg}", file=sys.stderr)
    sys.exit(1)


def check_a_existence():
    log("Verificando regla (a): Existencia de HALLAZGOS.md...")
    if not HALLAZGOS_PATH.exists():
        fail(f"El archivo {HALLAZGOS_PATH} no existe.")
    if HALLAZGOS_PATH.stat().st_size == 0:
        fail(f"El archivo {HALLAZGOS_PATH} está vacío.")
    log(f"-> HALLAZGOS.md presente ({HALLAZGOS_PATH.stat().st_size} bytes). OK.")


def parse_document():
    text = HALLAZGOS_PATH.read_text(encoding="utf-8")
    return text


def check_b_and_c_and_d_families_and_cases(text: str):
    log("Verificando reglas (b), (c) y (d): Familias, 21 casos, campos obligatorios y sin SIGECOM...")

    # Verificar presencia de las 7 familias
    for fam_idx, fam_name in enumerate(EXPECTED_FAMILIES, 1):
        fam_header_pattern = rf"###\s+Familia\s+{fam_idx}:"
        if not re.search(fam_header_pattern, text):
            fail(f"No se encontró el encabezado de la Familia {fam_idx} ({fam_name}).")
    log("-> 7 familias de prueba identificadas en el documento.")

    # Extraer casos de prueba: encabezados tipo #### Caso X.Y: ...
    case_blocks = re.split(r"(?=####\s+Caso\s+\d+\.\d+:)", text)
    # El primer bloque es el encabezado y prioridades
    cases = [b for b in case_blocks if re.match(r"####\s+Caso\s+\d+\.\d+:", b.strip())]

    if len(cases) != 21:
        fail(f"Se esperaban exactamente 21 casos de prueba, pero se encontraron {len(cases)}.")
    log(f"-> Conteo exacto de 21 casos de prueba confirmado.")

    # Verificar 3 casos por familia (1.1-1.3, 2.1-2.3, ..., 7.1-7.3)
    case_ids = []
    for case_text in cases:
        header_match = re.search(r"####\s+Caso\s+(\d+\.\d+):([^\n]+)", case_text)
        if not header_match:
            fail(f"No se pudo extraer el identificador del caso en: {case_text[:100]}")
        cid = header_match.group(1)
        case_ids.append(cid)

    expected_cids = [f"{fam}.{c}" for fam in range(1, 8) for c in range(1, 4)]
    if case_ids != expected_cids:
        fail(f"Discrepancia en IDs de casos: encontrados {case_ids}, esperados {expected_cids}")
    log("-> Distribución exacta de 3 casos por familia (1.1 a 7.3) confirmada.")

    # Validar campos obligatorios en cada caso
    for cid, case_text in zip(case_ids, cases):
        # 1. tarea
        tarea_match = re.search(r"-\s+\*\*tarea\*\*:\s*([^\n]+)", case_text)
        if not tarea_match:
            fail(f"Caso {cid}: Falta el campo obligatorio 'tarea'.")
        tarea = tarea_match.group(1).strip()
        if not tarea:
            fail(f"Caso {cid}: El campo 'tarea' está vacío.")

        # Regla (d): Sin SIGECOM en tarea
        if "sigecom" in tarea.lower():
            fail(f"Caso {cid}: El campo 'tarea' contiene una mención indebida a 'SIGECOM' ({tarea}).")

        # 2. estado_esperado
        estado_match = re.search(r"-\s+\*\*estado_esperado\*\*:\s*([^\n]+)", case_text)
        if not estado_match:
            fail(f"Caso {cid}: Falta el campo obligatorio 'estado_esperado'.")
        estado_esperado = estado_match.group(1).strip()
        if not estado_esperado:
            fail(f"Caso {cid}: El campo 'estado_esperado' está vacío.")

        # 3. resumen: debe estar presente dentro de estado_esperado o en el bloque del caso
        if "resumen" not in case_text.lower():
            fail(f"Caso {cid}: Falta la especificación o formato exacto del 'resumen'.")

        # 4. fallo_en_codigo
        fallo_match = re.search(r"-\s+\*\*fallo_en_codigo\*\*:\s*([^\n]+)", case_text)
        if not fallo_match:
            fail(f"Caso {cid}: Falta el campo obligatorio 'fallo_en_codigo'.")
        fallo = fallo_match.group(1).strip()
        if not fallo:
            fail(f"Caso {cid}: El campo 'fallo_en_codigo' está vacío.")

        # Comprobar que cita screen_agent.py:L, vnc_client.py:L o 'no demostrado'
        citation_valid = bool(
            re.search(r"`?(screen_agent\.py|vnc_client\.py):\d+`?", fallo)
            or "no demostrado" in fallo.lower()
        )
        if not citation_valid:
            fail(f"Caso {cid}: 'fallo_en_codigo' ({fallo}) no cita archivo y línea válidos ni 'no demostrado'.")

        # 5. correccion_minima
        corr_match = re.search(r"-\s+\*\*correccion_minima\*\*:\s*([^\n]+)", case_text)
        if not corr_match:
            fail(f"Caso {cid}: Falta el campo obligatorio 'correccion_minima'.")
        corr = corr_match.group(1).strip()
        if not corr:
            fail(f"Caso {cid}: El campo 'correccion_minima' está vacío.")

        # 6. clasificacion_evidencia
        evid_match = re.search(r"-\s+\*\*clasificacion_evidencia\*\*:\s*([^\n]+)", case_text)
        if not evid_match:
            fail(f"Caso {cid}: Falta el campo obligatorio 'clasificacion_evidencia'.")
        evid = evid_match.group(1).strip().replace("`", "").lower()
        if evid not in ("confirmado en código", "hipótesis", "confirmado en codigo", "hipotesis"):
            fail(f"Caso {cid}: 'clasificacion_evidencia' ({evid}) debe ser estrictamente 'confirmado en código' o 'hipótesis'.")

    log("-> Todos los 21 casos contienen todos los campos requeridos con formato válido. OK.")


def check_e_priorities(text: str):
    log("Verificando regla (e): Sección de prioridades inicial con <= 10 elementos citados válidos...")

    # Extraer la sección de prioridades
    prio_match = re.search(r"##\s+1\.\s+Prioridades de Alto Impacto[\s\S]*?(?=##\s+2\.)", text)
    if not prio_match:
        fail("No se encontró la sección inicial '## 1. Prioridades de Alto Impacto'.")

    prio_section = prio_match.group(0)

    # Extraer filas de tabla de prioridades
    table_rows = re.findall(r"\|\s*(\d+)\s*\|\s*`?([a-zA-Z0-9_\.]+\.py):(\d+)`?\s*\|", prio_section)
    if not table_rows:
        fail("No se encontraron elementos en la tabla de prioridades.")

    count = len(table_rows)
    if count > 10:
        fail(f"La sección de prioridades tiene {count} elementos (máximo permitido: 10).")
    if count == 0:
        fail("La sección de prioridades está vacía.")

    log(f"-> Conteo de prioridades: {count} elementos (<= 10). OK.")

    # Validar que cada cita exista en el repositorio y el número de línea sea demostrable
    for item_num, filename, lineno_str in table_rows:
        target_file = REPO_ROOT / filename
        if not target_file.exists():
            fail(f"Prioridad #{item_num}: El archivo citado '{filename}' no existe en {REPO_ROOT}.")

        lineno = int(lineno_str)
        with open(target_file, "r", encoding="utf-8") as f:
            total_lines = sum(1 for _ in f)

        if not (1 <= lineno <= total_lines):
            fail(f"Prioridad #{item_num}: Línea {lineno} fuera de rango en {filename} (total líneas: {total_lines}).")

    log("-> Todas las prioridades citan archivos y líneas existentes demostrables en el repositorio. OK.")


def check_f_git_integrity():
    log("Verificando regla (f): Integridad git y ausencia de modificaciones fuera de benchmarks/aletheia/...")

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        fail(f"Error al ejecutar git status: {exc}")

    lines = [line for line in proc.stdout.splitlines() if line.strip()]

    # Reglas de integridad:
    # 1. No se crearon archivos sin rastrear (??) fuera de benchmarks/aletheia/
    # 2. Los archivos modificados fuera de benchmarks/aletheia/ corresponden estrictamente a la línea base previa
    #    y no sufrieron modificaciones adicionales durante este trabajo de auditoría.
    for line in lines:
        status = line[:2]
        filepath = line[3:].strip()

        # Si es un archivo bajo benchmarks/aletheia, es perfectamente válido
        if filepath.startswith("benchmarks/aletheia"):
            continue

        # Cualquier archivo fuera de benchmarks/aletheia/ es una violación estricta de aislamiento
        fail(f"Archivo modificado o no rastreado detectado fuera de benchmarks/aletheia/: {filepath}")

    log("-> Verificación de integridad git: cero archivos modificados o creados fuera de benchmarks/aletheia/. OK.")


def main():
    print("=" * 70)
    print("ALETHEIA QA BENCHMARK — VALIDACIÓN PROGRAMÁTICA DE HALLAZGOS.MD")
    print("=" * 70)

    check_a_existence()
    content = parse_document()
    check_e_priorities(content)
    check_b_and_c_and_d_families_and_cases(content)
    check_f_git_integrity()

    print("=" * 70)
    print("TODOS LOS CRITERIOS DE ACEPTACIÓN SE CUMPLEN SATISFACTORIAMENTE.")
    print("Resultado: EXIT 0")
    print("=" * 70)
    sys.exit(0)


if __name__ == "__main__":
    main()
