import asyncio
from alembic import context
from app.database import Database
from app.models import Base
from app.pilot_config import PilotSettings


def migrations(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    settings = PilotSettings()
    database = Database((settings.migration_database_url or settings.database_url).get_secret_value())
    try:
        async with database.engine.connect() as connection:
            await connection.run_sync(migrations)
    finally:
        await database.close()


if context.is_offline_mode():
    settings = PilotSettings()
    context.configure(
        url=(settings.migration_database_url or settings.database_url).get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
