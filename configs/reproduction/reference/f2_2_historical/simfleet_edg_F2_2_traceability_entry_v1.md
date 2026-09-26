# Traceability entry — F2.2

- **ID:** F2.2
- **Objetivo:** validar diagnósticamente D_REPLAY/D_MATCH y congelar las definiciones de métricas reutilizables en G2.
- **Entradas:** F2.1 bridge; strict TRAIN MiD evidence; F0.3 eligibility semantics.
- **Evidencia:** person-day, trip purpose, temporal, transition and distance references with P_GEW/W_GEW.
- **Decisiones:** separar replay fidelity, complete-diary selection bias y matching distortion; D_MATCH no se considera baseline de validez para D_GEN; LOW_N explícito; no thresholds de aceptación en F2.
- **Pendientes:** F3 D_GEN; numeric G2 thresholds before TEST; G1 formal.
- **Salida:** metric protocol, reference inventory, global/distribution/conditional metrics, selection-bias audit, diagnostic issues.
- **Gate afectado:** F2 diagnóstico; G2 no evaluado.
- **Estado:** SUPERADO.
- **Impacto:** congela métrica/eligibility para la futura evaluación de D_GEN; no cambia contratos F0 ni gates formales.
