# P1-3 — PyVISA "not installed" investigation (2026-05-16)

## TL;DR

The "PyVISA missing" condition seen during ENA debugging was **IDE
interpreter-path drift**, not a runtime issue. PyVISA is correctly
installed in the project venv and works fine for every actual code
path. The IDE's static analysis was resolving `import pyvisa` against
the system Python's site-packages (where it isn't installed) instead
of the venv. Same root cause as the IDE-diagnostics noise backlog
entry from 2026-05-14.

## Reproduction

Three Python contexts on the dev box (macOS, Python 3.13):

| Context | Path | `import pyvisa` |
|---------|------|----------------|
| Project venv | `api-service/.venv/bin/python` | ✅ pyvisa 1.16.2 |
| System Python (Homebrew) | `/opt/homebrew/bin/python3` | ❌ ModuleNotFoundError |
| Shell default `python3` | resolves to system Python above | ❌ ModuleNotFoundError |

The IDE (VSCode on this machine) defaults to the first interpreter on
`PATH` unless `.vscode/settings.json` overrides it — which here is the
system Python, where pyvisa is not installed. Any in-editor "go to
definition" / autocomplete / inline error squiggle uses that
interpreter, so it reports `pyvisa` (and `sqlalchemy`,
`pydantic_settings`, etc) as missing.

## What runs in production

- `uvicorn app.main:app` launched from `api-service/.venv/bin/uvicorn`
  → reaches venv site-packages → pyvisa available.
- `pytest` invoked after `source .venv/bin/activate` → venv reaches
  → pyvisa available.
- HAL drivers (e.g. `app/hal/keysight_ena.py`) that import pyvisa
  at runtime succeed; no driver has ever actually failed to load
  because of "missing pyvisa" — only the IDE claimed missing.

## What was misread as a runtime failure

During ENA driver debugging the operator saw an IDE squiggle on
`import pyvisa` and assumed the runtime was broken too. Not the
case — the driver loaded and ran. Worth noting because the next
ENA / other VISA driver debug session may hit the same false
signal and waste 15 min chasing a non-existent install issue.

## Remediation (NOT done in this PR)

Real fix is the IDE-diagnostics backlog entry from 2026-05-14:
add `.vscode/settings.json` with
`"python.defaultInterpreterPath": "${workspaceFolder}/api-service/.venv/bin/python"`.
Deferred because `.vscode/` is in `.gitignore` — committing it
would be a per-contributor preference change that belongs in its
own scoped PR + a `.gitignore` adjustment discussion.

## Acceptance

Per [roadmap P1-3](../roadmap-first-call.md#p1-3--pyvisa-not-installed-investigation):
root cause documented. This file is the artifact.
