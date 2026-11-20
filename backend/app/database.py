import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class Database:
    def __init__(self, url):
        url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        self.sqlite = url.startswith('sqlite')
        options = {}
        if not self.sqlite:
            # Neon PgBouncer supports protocol-level prepare. Do not silently switch providers.
            if '?sslmode=' in url or '&sslmode=' in url:
                from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
                parsed = urlsplit(url)
                pairs = [(k, v) for k, v in parse_qsl(parsed.query) if k not in ('sslmode', 'channel_binding')]
                url = urlunsplit(parsed._replace(query=urlencode(pairs)))
                options['ssl'] = True
            options.update(statement_cache_size=0, prepared_statement_cache_size=0,
                           timeout=10, command_timeout=15,
                           prepared_statement_name_func=lambda: '__fogwrite_' + uuid4().hex)
        self.engine = create_async_engine(url, pool_pre_ping=True, **(
            {'poolclass': NullPool, 'connect_args': options} if not self.sqlite else {}
        ))
        if self.sqlite:
            @event.listens_for(self.engine.sync_engine, 'connect')
            def sqlite_setup(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA busy_timeout=10000')
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._connection_slots = asyncio.Semaphore(10)
        self._sqlite_write_lock = asyncio.Lock()

    @asynccontextmanager
    async def sessions(self):
        async with self._connection_slots:
            async with self._sessions() as session:
                yield session

    @asynccontextmanager
    async def transaction(self):
        # SQLite is only a deterministic local/test adapter, never the production queue.
        if self.sqlite:
            async with self._sqlite_write_lock:
                async with self.sessions() as session:
                    async with session.begin():
                        yield session
        else:
            async with self.sessions() as session:
                async with session.begin():
                    yield session

    async def close(self):
        await self.engine.dispose()
