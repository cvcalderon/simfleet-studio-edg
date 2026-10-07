# SimFleet-EDG — F4.1d
## Production D_GEN Runtime Binding — DESIGN FREEZE v1

**Workflow:** `SIMFLEET_EDG_WORKFLOW_V2`  
**State:** `DESIGN_FROZEN`  
**Implementation:** `NOT YET AUTHORIZED`

## 1. Why F4.1d exists

F4.1b intentionally stopped at a pure adapter:

```text
already-generated D_GEN day/trip rows
→ PersonDayPlan
```

and explicitly deferred binding the accepted `P_CONSTR` runtime identities.

F4.2a cannot legitimately spatialize the F3 synthetic/reproduction cohort.

F4.1d therefore supplies the missing production runtime layer:

```text
accepted M1 state
+ scenario-known context
+ frozen selected D_GEN artifacts
→ generated runtime day/trip rows
→ PersonDayPlan
```

No model is refitted or reselected.

## 2. Frozen M1 input

```text
P_CONSTR_RMIN_V2_HD_U / M

households = 54,828
persons    = 100,000
resources  = 642,364
```

Exact hashes are frozen in the YAML contract.

## 3. Frozen M2 pipeline

```text
PA1
→ COUNT_REF
→ CHA2
→ TIME_B_TB2
→ DIST_REF_REFERENCE
```

All five model and artifact-manifest hashes are fixed.

F4.1d may only load those frozen artifacts.

## 4. Scenario-known context

Production D_GEN must receive an explicit caller-supplied:

```text
scenario_id
scenario_weekday ∈ 1..7
scenario_season  ∈ 1..4
```

The legacy model field names remain:

```text
source_weekday
source_season
```

only for compatibility with the frozen fitted encoders.

Their runtime values come exclusively from:

```text
scenario_weekday
scenario_season
```

Never from a MiD donor/reference day.

## 5. Runtime M1 feature binding

Direct M1 person fields:

```text
age_infr_class
sex
primary_activity_status
```

Household size:

```text
1..5       -> "1".."5"
generated >= 6 -> "6_PLUS"
```

No 6+ household is silently recoded to size 5 or claimed to be exactly six persons.

Household stocks/memberships and person access/memberships are reconstructed from the accepted M1 `resources.csv` using the same frozen categorical semantics used for F3 fitting.

## 6. 6+ / unseen policy

The definitive M1 population contains 6+ households whereas the strict fitting universe was narrower.

F4.1d therefore must audit frozen-model support explicitly.

```text
6_PLUS remains semantically 6_PLUS
frozen reserved unseen/backoff mechanism may handle it
silent coercion is forbidden
```

The RunBundle must report unseen/backoff counts by component and field.

If any selected frozen adapter cannot consume the runtime category under its already-frozen policy, execution blocks and returns to MAIN.

## 7. Identity

Runtime identities are the generated accepted M1 IDs.

The historical F4.1b day/trip schema retains column names:

```text
source_household_id
source_person_id
```

but in production they carry:

```text
accepted M1 household_id
accepted M1 person_id
```

They do not carry MiD donor IDs.

This closes the identity note left intentionally open in F4.1b.

## 8. RNG

Production runtime generation uses the already-frozen SHA-256 seed primitive with a new production namespace:

```text
master_seed = 20261007
scenario_id = caller-supplied scenario identity
person key  = accepted M1 person_id
```

It must not use `CAL_SCENARIO_ID`.

Generation is independent of dataframe iteration order.

## 9. F4.1d execution scope

F4.1d does **not** yet create the scientific full 100k demand realization for F4.2a.

Its official execution is an engineering binding verification on a deterministic 512-person subset:

```text
scenario_id      = F4_1D_BINDING_SMOKE_V1
scenario_weekday = 3
scenario_season  = 2
```

The smoke output is explicitly:

```text
NOT DOWNSTREAM AUTHORIZED
```

A second full smoke run must reproduce exact canonical output hashes.

After F4.1d closes, MAIN can freeze the actual scenario-day schedule for F4.2a and authorize a full D_GEN realization plus candidate execution.

## 10. Scientific boundary

Forbidden in F4.1d:

```text
CAL
MiD TEST
G1/G2 reopen
refit/recalibration/reselection
destination assignment
S_NEAR / S_DIST / S_ATTR
G3
mode
routing
execution outcomes
```
