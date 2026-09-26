# MAIN update — F3.2c environment preparation

- Parent implementation commit: `1fe196a5495b5d9e0952273a4ebab3840e7aaca9`.
- F3.2b remains SUPERADO.
- Dependency gate observed: NumPy/Pandas available; SciPy/scikit-learn/statsmodels/LightGBM absent.
- Adds a dedicated `modeling` optional dependency group to `pyproject.toml`.
- Adds generated-output ignore rules for `artifacts/model_data/` and `artifacts/environment/`.
- No scientific model-family substitution is permitted.
- Exact resolved versions must be captured after install.
- TEST remains sealed; formal G2 remains NOT_EVALUATED.
