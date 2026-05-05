"""TRP test_type service: factory + executors.

Phase 3a (2026-05-05): 第二个使用 TestCase + ExecutorRegistry 架构的
test_type, 验证 RECONCILIATION NOTE 命名约定经得起新场景。

Importing this package registers TRP executors with EXECUTOR_REGISTRY —
keep this import in app startup so registrations happen exactly once.
"""
from app.services.trp import executors  # noqa: F401  - register decorator side-effect
from app.services.trp.factory import build_trp_test_case

__all__ = ["build_trp_test_case"]
