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

## `topology-templates/`

`SwitchTopology` is a much heavier structure than the other dev fixtures
(80+ nodes, 90+ connections, 5 operating modes per site). Rather than a
seed *script* per site we keep one *generator module* per site here. The
contract is simple — every file must export:

```python
def generate_topology_record() -> dict:
    """Returns kwargs ready for SwitchTopology(**record)."""
```

The API endpoint `POST /switch-topologies/import/from-template?template_id=<filename>`
loads these via `importlib.util.spec_from_file_location` at runtime, so:

- Commercial deploys that don't ship `scripts/dev-fixtures/` see
  `GET /switch-topologies/templates → []` and the GUI "重导入" button
  surfaces an error — operators are expected to build via the editor.
- Dev installs see the templates listed and can re-import any site's
  full V4.0 wiring with one click.

To add a new site: copy `caict_v4.py` → `<site>_<version>.py`, rewrite
the constants near the top (probe map, vertical ring, signal sources,
EMCenter config, topology metadata) and the per-call-site labels in
`generate_topology_record()` (`site_name`, `system_model`, etc.). The
GUI call site in `TopologyEditor.tsx` currently hardcodes
`template_id='caict_v4'` — when you add a second template, swap that
for a dropdown driven by `GET /switch-topologies/templates`.
