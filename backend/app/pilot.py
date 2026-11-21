"""Deployment entry point: uvicorn app.pilot:app. No research/demo routes."""
import asyncio
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text
from starlette.exceptions import HTTPException

from app.auth import ClerkVerifier
from app.config import ROOT
from app.database import Database
from app.pilot_config import PilotSettings
from app.providers.base import ProviderError
from app.routers.pilot import router
from app.routers.teacher import router as teacher_router
from app.services.provider import PilotProvider
from app.worker import Worker
from app.models import Job, Submission


class PublicFrontend(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code == 404 and path.split('/')[0] in {'join', 'classes', 'profile', 'admin', 'overview', 'topics', 'practice', 'check', 'skill-practice', 'history', 'assessment'}:
                return await super().get_response('index.html', scope)
            raise


class SecurityMiddleware:
    def __init__(self, app, production=False, clerk_issuer=''):
        self.app, self.production, self.clerk_issuer = app, production, clerk_issuer
        self.write_bursts = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            content_length = int(headers.get(b'content-length', b'0') or b'0')
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if content_length > 65536:
            return await JSONResponse({'detail': 'Request body is too large.'}, status_code=413)(scope, receive, send)
        if scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE'):
            ip = (scope.get('client') or ('unknown',))[0]
            now = time.monotonic()
            recent = [at for at in self.write_bursts.pop(ip, []) if at > now - 60]
            if len(recent) >= 300:
                self.write_bursts[ip] = recent
                return await JSONResponse({'detail': 'Too many requests. Try again shortly.'}, status_code=429, headers={'Retry-After': '60'})(scope, receive, send)
            self.write_bursts[ip] = [*recent, now]
            while len(self.write_bursts) > 10000: self.write_bursts.popitem(last=False)
        body, size = [], 0
        # Bound streamed bodies too; Content-Length alone is not a security limit.
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=15)
            except TimeoutError:
                return await JSONResponse({'detail': 'Request body timed out.'}, status_code=408)(scope, receive, send)
            if message['type'] == 'http.disconnect': return
            size += len(message.get('body', b''))
            if size > 65536:
                return await JSONResponse({'detail': 'Request body is too large.'}, status_code=413)(scope, receive, send)
            body.append(message)
            if not message.get('more_body'): break
        async def replay():
            if body: return body.pop(0)
            return await receive()
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([(b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'same-origin'), (b'x-frame-options', b'DENY'),
                    (b'permissions-policy', b'camera=(), microphone=(), geolocation=()')])
                if scope['path'].startswith('/api/'):
                    message['headers'].append((b'cache-control', b'no-store'))
                if self.production:
                    message['headers'].append((b'strict-transport-security', b'max-age=31536000; includeSubDomains'))
                    csp = ("default-src 'self'; script-src 'self' " + self.clerk_issuer + " https://challenges.cloudflare.com; "
                           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: https://img.clerk.com https://*.clerk.com; "
                           "connect-src 'self' " + self.clerk_issuer + "; frame-src " + self.clerk_issuer + " https://challenges.cloudflare.com; "
                           "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
                    message['headers'].append((b'content-security-policy', csp.encode()))
            await send(message)
        return await self.app(scope, replay, secure_send)


def create_pilot_app(settings=None, *, database=None, provider_factory=None, verifier=None):
    settings = settings or PilotSettings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings
        app.state.database = database or Database(settings.database_url.get_secret_value())
        app.state.verifier = verifier or ClerkVerifier(settings)
        semaphore = asyncio.Semaphore(settings.gemini_max_concurrent)
        factory = provider_factory or (lambda small: PilotProvider(app.state.database, settings, semaphore, small=small))
        app.state.provider, app.state.answer_provider = factory(False), factory(True)
        workers = [Worker(app.state.database, settings, app.state.provider, app.state.answer_provider) for _ in range(settings.worker_count)]
        app.state.workers = workers
        tasks = [asyncio.create_task(worker.run()) for worker in workers] if settings.worker_enabled else []
        app.state.worker_tasks = tasks
        async def maintenance():
            while True:
                try:
                    async with app.state.database.transaction() as session:
                        running = select(Job.submission_id).where(Job.status == 'RUNNING')
                        await session.execute(delete(Submission).where(Submission.created_at < time.time() - settings.retention_days * 86400,
                                                                       ~Submission.id.in_(running)))
                except Exception as error:
                    logging.getLogger('fogwrite').error('retention_cleanup_failed type=%s', type(error).__name__)
                await asyncio.sleep(3600)
        maintenance_task = asyncio.create_task(maintenance()) if settings.worker_enabled else None
        try:
            yield
        finally:
            for task in tasks: task.cancel()
            if maintenance_task: maintenance_task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if maintenance_task: await asyncio.gather(maintenance_task, return_exceptions=True)
            await app.state.provider.close()
            if app.state.answer_provider is not app.state.provider: await app.state.answer_provider.close()
            if database is None: await app.state.database.close()

    app = FastAPI(title='FogWrite Pilot API', version='2.0.0', lifespan=lifespan,
                  docs_url=None if settings.app_env == 'production' else '/docs',
                  redoc_url=None, openapi_url=None if settings.app_env == 'production' else '/openapi.json')
    app.add_middleware(SecurityMiddleware, production=settings.app_env == 'production', clerk_issuer=settings.clerk_issuer)
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                       allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
                       allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # FastAPI's default may echo submitted values in validation errors. Avoid PII echoes.
        return JSONResponse({'detail': [{'loc': item['loc'], 'msg': item['msg'], 'type': item['type']} for item in error.errors()]}, status_code=422)

    @app.exception_handler(ProviderError)
    async def provider_error(request, error):
        return JSONResponse({'detail': {'code': error.code, 'message': 'AI service is temporarily unavailable.'}}, status_code=503)

    @app.get('/health')
    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'mode': 'pilot'}

    @app.get('/ready')
    async def ready():
        try:
            from app.services.scorer import baseline_config
            baseline_config()
            async with asyncio.timeout(5):
                async with app.state.database.sessions() as session:
                    await session.execute(text('SELECT 1 FROM users LIMIT 1'))
            tasks = app.state.worker_tasks
            if settings.worker_enabled and any(task.done() for task in tasks): raise RuntimeError()
        except Exception:
            return JSONResponse({'status': 'not_ready'}, status_code=503)
        return {'status': 'ready'}

    app.include_router(router)
    app.include_router(teacher_router)
    from app.routers.admin import router as admin_router
    app.include_router(admin_router)
    dist = ROOT / 'frontend' / 'dist'
    if (dist / 'index.html').is_file():
        app.mount('/', PublicFrontend(directory=dist, html=True), name='frontend')
    return app


app = create_pilot_app()
