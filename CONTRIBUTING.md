# Contributing

Contributions are welcome.

## Suggested workflow

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and add or update tests where relevant.
4. Run the test suite locally.
5. Open a pull request with a clear summary of the change.

## Local verification

```powershell
python -m pytest -q
```

The test suite is configured through pyproject.toml. Install the project dependencies first with:

```powershell
python -m pip install -r requirements.txt
```

For a behavior-level smoke check, run:

```powershell
python deployment_readiness_demo.py
```
