# SimFleet-EDG — Reproducción PRE-F3

**Estado:** C-IMPL-01 scaffold preparado; instalación/verificación en la VM pendiente.  
**Alcance:** reproducir el baseline F0–F2 sin alterar contratos científicos ni iniciar D_GEN.

La implementación core irá en `src/simfleet_edg/`; Jupyter será una interfaz de exploración. Los trabajos intensivos se ejecutarán en Proxmox desde funciones/CLI reproducibles, no como única lógica en celdas.

## Inicio rápido

Consulta `docs/INSTALL_UBUNTU_24_04_PYCHARM.md` para instalación y verificación paso a paso. Después guarda la salida de la verificación y el commit de Git en el registro local de la Parte C.

## Estructura

```text
configs/          Configs versionadas (sin rutas personales ni secretos)
src/              Código Python autoritativo
tests/            Validaciones automatizadas
notebooks/        Análisis y visualización; no algoritmos únicos
scripts/          Herramientas de ejecución/diagnóstico
data/             MiD/Zensus/LOR locales: no versionados
artifacts/        Runs y resultados grandes: no versionados
docs/             Instrucciones y trazabilidad
```

## Restricciones de C-IMPL-01

- No contiene datos MiD, Zensus ni LOR.
- No implementa `P_TRS`, `D_REPLAY`, `D_MATCH`, métricas ni `D_GEN`.
- No afirma que R0–R7 estén reproducidos.
- Mantiene TEST sellado para la futura validación formal.
