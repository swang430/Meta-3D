# Dev fixtures

Site-specific or hardcoded-id seed scripts that should **not** ship to
customers as defaults. Live here instead of being registered with
`app/services/bootstrap/` so that:

- `python -m scripts.bootstrap` on a fresh customer install produces a
  clean, generic system — no CAICT-named LabProfile, no dummy
  calibration data tied to one specific chamber UUID.
- Internal devs can still seed their machines with realistic data by
  running these scripts manually:

  ```bash
  cd api-service
  .venv/bin/python scripts/dev-fixtures/seed_caict_lab_profile.py
  .venv/bin/python scripts/dev-fixtures/seed_caict_switch_topology.py
  .venv/bin/python scripts/dev-fixtures/seed_dummy_calibration.py
  ```

When CAICT-Lab-1 or any other site eventually needs an out-of-the-box
profile shipped to customers, the right move is to **generalize the
data** (parameterize names + IDs) and add a new generic seeder under
`app/services/bootstrap/`, not to promote one of these scripts as-is.
