"""Clerk session verification. There is deliberately no local password fallback."""
import asyncio
import time

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import User


class ClerkVerifier:
    def __init__(self, settings):
        self.settings = settings
        self.keys, self.fetched_at = {}, 0
        self.lock = asyncio.Lock()

    async def verify(self, token, *, include_claims=False):
        settings = self.settings
        if not settings.clerk_issuer:
            raise HTTPException(503, 'Clerk authentication has not been configured.')
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
                raise jwt.InvalidTokenError()
            key = settings.clerk_jwt_key.replace('\\n', '\n')
            if not key:
                async with self.lock:
                    if time.time() - self.fetched_at > 300 or (header['kid'] not in self.keys and time.time() - self.fetched_at > 30):
                        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                            response = await client.get(settings.clerk_issuer.rstrip('/') + '/.well-known/jwks.json')
                            response.raise_for_status()
                            self.keys = {item['kid']: jwt.PyJWK.from_dict(item).key for item in response.json()['keys'] if item.get('kty') == 'RSA'}
                            self.fetched_at = time.time()
                    key = self.keys.get(header['kid'])
                if key is None:
                    raise jwt.InvalidTokenError()
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=settings.clerk_issuer.rstrip('/'),
                                audience=settings.clerk_audience or None, leeway=5,
                                options={'require': ['exp', 'nbf', 'iat', 'iss', 'sub', 'azp'],
                                         'verify_aud': bool(settings.clerk_audience)})
            if claims['azp'] not in settings.origins or not isinstance(claims['sub'], str) or len(claims['sub']) > 200:
                raise jwt.InvalidTokenError()
            return claims if include_claims else claims['sub']
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise HTTPException(401, 'Phiên đăng nhập không hợp lệ hoặc đã hết hạn.') from None
        except httpx.HTTPError:
            raise HTTPException(503, 'Không thể xác minh đăng nhập. Vui lòng thử lại.') from None


async def current_user(request: Request):
    authorization = request.headers.get('authorization', '')
    if not authorization.startswith('Bearer ') or len(authorization) > 12000:
        raise HTTPException(401, 'Vui lòng đăng nhập để tiếp tục.', headers={'WWW-Authenticate': 'Bearer'})
    verifier = request.app.state.verifier
    if isinstance(verifier, ClerkVerifier):
        claims = await verifier.verify(authorization[7:], include_claims=True)
        subject = claims['sub']
    else:
        subject = await verifier.verify(authorization[7:])
        claims = {}
    database = request.app.state.database
    async with database.sessions() as session:
        user = await session.scalar(select(User).where(User.external_auth_id == subject))
    if user is None:
        try:
            async with database.transaction() as session:
                user = User(external_auth_id=subject)
                session.add(user)
                await session.flush()
        except IntegrityError:
            async with database.sessions() as session:
                user = await session.scalar(select(User).where(User.external_auth_id == subject))
    if not user or not user.active:
        raise HTTPException(403, 'Tài khoản đã bị khóa.')
    from app.identity import sync_profile
    return await sync_profile(database,user,claims,request.app.state.settings)


async def staff_user(user=Depends(current_user)):
    if user.role not in ('ta', 'teacher', 'admin'):
        raise HTTPException(403, 'Bạn không có quyền thực hiện thao tác này.')
    return user
