"""Drop a sequence module here and restart — the loader picks it up.

Each module must export `metadata: SequenceMetadata` and
`async def run(ctx, hal, params, *, log) -> SequenceRunResult`.
"""
