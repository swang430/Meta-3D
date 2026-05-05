"""3GPP MIMO OTA test execution — TestCase-native implementation.

Replaces the legacy `commissioning_service` module by:
1. Treating MIMO_OTA as a TestCase derivative (test_type='MIMO_OTA').
2. Splitting the 5 phases into 5 IStepExecutor classes registered with the
   ExecutorRegistry.
3. Sourcing chamber/instrument/calibration config from the bound LabProfile
   instead of hard-coded constants.

Importing this package registers the 5 executors with the global registry —
keep this import in app startup so registrations happen exactly once.
"""
# Import for side-effect: registers the 5 executors with EXECUTOR_REGISTRY.
from app.services.mimo_ota import executors  # noqa: F401
from app.services.mimo_ota.factory import build_mimo_ota_test_case

__all__ = ["build_mimo_ota_test_case"]
