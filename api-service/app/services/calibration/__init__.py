"""Calibration cross-cutting helpers (P0).

Modules here sit between the chamber/topology models and the per-domain
calibration services (path-loss, RF chain, probe pattern). They exist so each
service doesn't re-implement "how do I figure out which probe, which port,
which cable for the current LabProfile + operating mode."
"""
