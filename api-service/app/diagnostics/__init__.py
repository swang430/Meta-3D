"""Workshop-tier diagnostic sequences (SCPI multi-step + helpers).

Modules under `sequences/` are first-class Python files — edit them in
your IDE, push, restart, run. Each sequence exports:

  - metadata: SequenceMetadata
      module-level dict of {name, description, required_categories,
      params_schema, kind}
  - async def run(ctx, hal, params, *, log) -> dict
      runs the actual commands; returns a dict that the UI shows verbatim
      and that goes into diagnostic_runs.output_excerpt as JSON.

The runner picks them up via `app.diagnostics.loader.list_sequences()`.

This is intentionally not a DB-backed builder — sequences live in code so
they're auditable via git, not via row history. If you need to share one
across ops, push it.
"""
