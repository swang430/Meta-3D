"""TRP step executors. Importing this package registers them with ExecutorRegistry."""
from app.services.trp.executors import precheck  # noqa: F401  - register decorator side-effect
