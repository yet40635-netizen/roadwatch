from alembic import context

from backend import models  # noqa: F401
from backend.config import settings
from backend.db import Base, engine

if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
