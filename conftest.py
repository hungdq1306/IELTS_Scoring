"""Explicit offline verification mode: real network and external databases are disabled."""
import socket
import pytest


def pytest_addoption(parser):
    parser.addoption('--offline', action='store_true', help='Block external socket connections during verification')
    parser.addoption('--windows-udp-wakeup', action='store_true', help='Use local UDP wakeups when the Windows sandbox blocks TCP socketpair')


@pytest.fixture(autouse=True)
def offline_network_guard(request, monkeypatch):
    if not request.config.getoption('--offline'):
        return
    # Windows asyncio creates its wakeup socket pair over loopback.
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    def guarded(original):
        def call(sock, address):
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1', 'localhost'):
                return original(sock, address)
            raise AssertionError('External network access is disabled by --offline')
        return call
    monkeypatch.setattr(socket.socket, 'connect', guarded(connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guarded(connect_ex))
    for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(key, raising=False)
    import httpx
    sync_request = httpx.HTTPTransport.handle_request
    async_request = httpx.AsyncHTTPTransport.handle_async_request
    def guard_http(transport, request):
        if request.url.host not in ('127.0.0.1', '::1', 'localhost'):
            raise AssertionError('Real external HTTP is disabled by --offline')
        return sync_request(transport, request)
    async def guard_async_http(transport, request):
        if request.url.host not in ('127.0.0.1', '::1', 'localhost'):
            raise AssertionError('Real external HTTP is disabled by --offline')
        return await async_request(transport, request)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', guard_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', guard_async_http)
    monkeypatch.setenv('GEMINI_LIVE_TEST', '0')
    for key in ('TEST_DATABASE_URL', 'MIGRATION_TEST_DATABASE_URL'):
        monkeypatch.delenv(key, raising=False)


def pytest_configure(config):
    import sys
    if not config.getoption('--windows-udp-wakeup'):
        return
    if not config.getoption('--offline') or sys.platform != 'win32':
        raise pytest.UsageError('--windows-udp-wakeup is a Windows offline-test adapter only')
    config._original_socketpair = socket.socketpair
    def local_pair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        if family != socket.AF_INET or type != socket.SOCK_STREAM or proto:
            raise ValueError('Only the default asyncio wakeup pair is supported by the offline adapter')
        a, b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            a.bind(('127.0.0.1', 0)); b.bind(('127.0.0.1', 0))
            a.connect(b.getsockname()); b.connect(a.getsockname())
            return a, b
        except BaseException:
            a.close(); b.close()
            raise
    socket.socketpair = local_pair
    # Sandboxed loopback wakeups may be dropped. Bound the IOCP wait so queued
    # callbacks from SQLite/AnyIO worker threads are still serviced.
    from asyncio.windows_events import IocpProactor
    config._original_iocp_select = IocpProactor.select
    def bounded_select(proactor, timeout=None):
        return config._original_iocp_select(proactor, .001 if timeout is None else min(timeout, .001))
    IocpProactor.select = bounded_select


def pytest_unconfigure(config):
    if hasattr(config, '_original_socketpair'):
        socket.socketpair = config._original_socketpair
        from asyncio.windows_events import IocpProactor
        IocpProactor.select = config._original_iocp_select
