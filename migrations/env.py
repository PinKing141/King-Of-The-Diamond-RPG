import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 1. Add project root to path so we can import your code
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# 2. Import your configuration and models
from config import DB_PATH
from database.setup_db import Base

# 3. Alembic Config object
config = context.config

# 4. Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 5. Set the MetaData object for 'autogenerate' support
target_metadata = Base.metadata

# 6. Set the DB URL dynamically from your Python config
config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # IMPORTANT for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # IMPORTANT for SQLite
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
