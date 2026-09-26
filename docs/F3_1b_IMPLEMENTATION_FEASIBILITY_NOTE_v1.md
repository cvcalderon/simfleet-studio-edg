# F3.1b — implementation feasibility note v1

This note is **non-authoritative implementation context**, not empirical evidence.

At the 2026-09-26 design cut, current Python libraries expose the required broad capabilities: statsmodels documents Negative-Binomial/Poisson count families and truncated/hurdle count models; current gradient-boosting libraries document binary, Poisson and quantile objectives plus weighted fitting. F3.1b deliberately does not pin a library/version because scientific family selection should not be defined by whichever package happens to be installed.

The primary count design uses a Negative-Binomial model on `K-1` specifically so implementation does not depend on a zero-truncated count API. Library/version pins belong to the later ModelArtifact/implementation freeze.
