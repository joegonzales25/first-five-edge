# First Five Edge Agent Guide

First Five Edge is a Streamlit MLB betting intelligence prototype. Treat model outputs as informational only, not betting advice.

## Rules

- Do not rewrite the app architecture unless explicitly asked.
- Preserve existing file names and public function names.
- Do not remove existing columns unless explicitly asked.
- Prefer small, testable changes.
- Keep UI and data-model changes narrowly scoped to the request.
- Maintain existing Streamlit flows, including game cards and analysis expanders, unless explicitly asked to change them.

## Validation

After changes, run:

```powershell
python mlb_agent.py
python -m streamlit run app.py
```

If `python` is unavailable in the current shell, use the available project Python executable and document that substitution.
