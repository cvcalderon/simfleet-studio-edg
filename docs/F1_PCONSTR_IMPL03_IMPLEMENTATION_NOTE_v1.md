# F1-P_CONSTR-IMPL-03 — Implementation note v1

## 1. Why equivalence classes are joint

The final P_CONSTR freeze superseded the early F1.1 marginal-only target semantics. The active fit basis is the reconciled joint cube:

```text
Bezirk × age_zensus_11_v1 × sex × HSHGR2
```

For exact household sizes 1..5, each TRAIN household is therefore represented by the complete 22-cell age×sex contribution vector within its exact size.

## 2. Fitting

The continuous class mass starts from TRAIN `H_GEW` class totals. IPU updates are proportional to the household's fractional contribution to each person control. Each full sweep is renormalized to the exact household count.

Integerization then:

1. floors class weights;
2. assigns remaining households by fractional remainder with canonical class-ID ties;
3. performs deterministic one-for-one class swaps only when they strictly reduce person-cell L1 error.

The exact number of households and persons is never changed by the repair.

## 3. Materialization ablation

The fitted class-count plan is shared by `HD_U` and `HD_W`. This guarantees their R_min fit is identical. Only the within-class source household draw differs.

## 4. P_TRS comparison

P_TRS uses the same Bezirk person frame and the same common 6+ branch, but the strict 1..5 branch is a global TRAIN `H_GEW` whole-household draw. It does not inspect local target composition.

## 5. Common 6+ branch

The H6 household-size realization remains the frozen IMPL-02 output. IMPL-03 adds only source templates and static person donors. Target age×sex slots are permuted deterministically and matched exactly to TRAIN private-person donors. Therefore the 6+ demographic contribution is identical across P_TRS, HD_U, and HD_W.

## 6. Geography

IMPL-03 stops at Bezirk. `home_zone_level=BEZIRK` is provisional by design. PLR allocation belongs to the later spatial task and cannot affect the IMPL-03 candidate fit.

## 7. NoFutureInformation

The raw MiD source readers request an explicit static-field allowlist. Mobility outcome fields are not donor matching inputs. Only TRAIN household IDs may produce donor/template/person records.
