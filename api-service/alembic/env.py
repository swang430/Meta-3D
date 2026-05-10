from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Wire alembic to the project's settings + Base.metadata. Importing
# app.models executes app/models/__init__.py which imports every model
# module — that's what populates Base.metadata for autogenerate.
import importlib
import pkgutil

from app.config import settings
from app.db.database import Base
import app.models as _models_pkg

# Walk every module under app/models/ and import it. Each import has the
# side effect of registering its Base subclasses on Base.metadata, which
# is what alembic's autogenerate compares against the live DB. We do this
# here (instead of relying on app/models/__init__.py to re-export every
# class) so that adding a new model file is enough — no extra bookkeeping.
for _module_info in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module(f"{_models_pkg.__name__}.{_module_info.name}")

config = context.config
# Default to ``settings.database_url`` (the project's normal config
# source) unless the caller already set a URL on this Config — e.g.
# tests building a Config in-process against a throwaway SQLite DB, or
# operators running ``alembic -x dburl=... upgrade head`` for one-offs.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
