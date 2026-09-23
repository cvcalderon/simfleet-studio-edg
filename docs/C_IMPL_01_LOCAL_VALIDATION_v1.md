# C-IMPL-01 — verificación del paquete en el entorno de preparación

**Fecha:** 2026-09-23  
**Estado:** `PACKAGE_READY / VM_VERIFICATION_PENDING`.

Comprobaciones efectuadas durante la construcción del paquete:

- `python -m compileall` sobre `src/`, `scripts/`, `tests/`: sin errores de sintaxis.
- Importación y CLI de scaffold `python -m simfleet_edg --version`: `simfleet-edg 0.0.1`.
- `python -m pytest -q`: **3/3 PASS** tras instalación editable de prueba.

**Límite de esta evidencia:** estas comprobaciones se realizaron en un entorno de preparación con Python 3.13, no en la VM Ubuntu 24.04/Python 3.12 del usuario. `ruff` y la verificación real del entorno VM quedan pendientes; estas comprobaciones locales no cierran `C-IMPL-01` ni constituyen `R0`.

**Prueba pendiente:** ejecutar `docs/INSTALL_UBUNTU_24_04_PYCHARM.md` en la VM y devolver evidencia textual del entorno y del primer commit real.
