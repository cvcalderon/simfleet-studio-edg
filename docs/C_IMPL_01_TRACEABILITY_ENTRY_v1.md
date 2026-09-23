# C-IMPL-01 — entrada de trazabilidad

**Work package:** C-IMPL-01 — Repository Scaffold  
**Fecha:** 2026-09-23  
**Estado del paquete:** BUILT_AND_LOCALLY_CHECKED / AWAITING_VM_VERIFICATION  
**Gates afectados:** ninguno; G1 sigue abierto y G2 no evaluado.

## Referencias autoritativas

- `SimFleet_EDG_Part_C_Reproducibility_WorkPackage_v1`: arquitectura `Python-library-first` y plan R0–R7.
- `SimFleet_EDG_Distributed_Workflow_v1`: MAIN/Worker/Proxmox/Analysis y reglas de reproducibilidad.

## Delta implementado

- Repositorio Python 3.12 bajo `src/` y metadata `pyproject.toml`.
- Paquetes vacíos para módulos científicos futuros; no se añade lógica F0–F2 ni D_GEN.
- `pytest` smoke tests, `ruff` y verificador de scaffold.
- Jerarquía de configs y anclas históricas de referencia (no un execution contract ejecutable).
- Directorios para fuentes locales ignoradas y artefactos grandes ignorados.
- Instrucciones Ubuntu 24.04/XFCE/PyCharm, inicialización Git e intérprete `.venv`.

## Qué NO se declara

- No se ha instalado todavía en la VM del usuario.
- No se han reproducido R0–R7.
- No hay backend FastAPI ni frontend.
- No se han validado datos originales ni resultados científicos.
- No existe commit real del repositorio en la VM hasta que se ejecute la instalación.

## Evidencia para cierre

1. Python 3.12 activo en la VM y PyCharm apuntando a `.venv/bin/python`.
2. Import, pruebas y linter PASS en el entorno VM.
3. Git inicializado, primer commit creado y working tree limpio.
4. Log de `scripts/verify_scaffold.py` con todas las comprobaciones PASS.
5. Commit/hash registrados en un informe `C_IMPL_01_VM_VERIFICATION`.

**Transición:** al verificar 1–5, iniciar C-IMPL-02 (entorno de reproducción) y R0 con un execution contract explícito.
