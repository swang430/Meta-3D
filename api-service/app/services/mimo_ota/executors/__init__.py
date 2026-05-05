"""MIMO_OTA step executors.

Importing this module registers the 5 executors with the global
EXECUTOR_REGISTRY via @register_executor decorators. Order of imports
doesn't matter — registration is per-class.
"""
from app.services.mimo_ota.executors import precheck  # noqa: F401
from app.services.mimo_ota.executors import reference  # noqa: F401
from app.services.mimo_ota.executors import measure  # noqa: F401
from app.services.mimo_ota.executors import analysis  # noqa: F401
from app.services.mimo_ota.executors import report  # noqa: F401
