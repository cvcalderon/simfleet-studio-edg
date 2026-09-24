# MAIN update — C-IMPL-03 / R1 preparation

Status: IMPLEMENTATION PREPARED; VM verification pending.

No F0/F1/F2 scientific decision is changed.

R1 operationalises the frozen F0 source manifest in `simfleet-studio-edg` and requires exact source-byte identity before R2 eligibility/split reproduction.

Expected sequence:

1. apply overlay;
2. run quality gates;
3. commit/push on clean `main`;
4. place raw source files under `data/raw/{mid,zensus,lor}`;
5. run `--precheck`;
6. execute official R1;
7. return compact R1 RunBundle for audit/closure.

Raw MiD data remain outside Git and must not be included in handoff ZIPs.
