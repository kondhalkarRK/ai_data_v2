import asyncio
import os

os.environ['ENVIRONMENT'] = 'development'
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-that-is-long-enough-for-tests-xx'
os.environ['CORS_ALLOWED_ORIGINS'] = 'http://localhost:3000'
os.environ['RATE_LIMIT_LOGIN_PER_MINUTE'] = '5'
os.environ['AUTH_BYPASS'] = 'false'
os.environ['TRUSTED_HOSTS'] = 'testserver,localhost'
os.environ['COOKIE_DOMAIN'] = ''
os.environ['COOKIE_SAMESITE'] = 'lax'

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.deps import get_app_session, get_registry
from app.auth.rate_limit import FixedWindowRateLimiter
from app.core.config import get_settings
from app.main import create_app
from app.models import Base
from app.models.user import User
from app.auth.passwords import hash_password
from app.models.enums import Role, Industry

async def main():
    settings = get_settings()
    app = create_app(settings)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_session():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    class StubRegistry:
        async def check_app_database(self):
            return True, 'ok'
        async def check_analytics_database(self, industry):
            return False, 'not_configured_in_tests'

    app.dependency_overrides[get_app_session] = override_session
    app.dependency_overrides[get_registry] = StubRegistry
    app.state.login_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)

    async with session_factory() as session:
        session.add(User(
            email='admin@example.com', username='admin', full_name='Test Admin',
            password_hash=hash_password('Vh7!kRq2$mTx9pLw'), role=Role.ADMIN,
            default_industry=Industry.INSURANCE, is_active=True,
        ))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        r = await client.post('/api/v1/auth/login', json={'username': 'admin@example.com', 'password': 'Vh7!kRq2$mTx9pLw'})
        print('status', r.status_code)
        print('set-cookie list', r.headers.get_list('set-cookie'))
        print('jar keys', list(client.cookies))
        print('jar', client.cookies)
        print('csrf', client.cookies.get('nql_csrf'))
        print('body', r.text)
        me = await client.get('/api/v1/auth/me')
        print('me status', me.status_code)
        print('me headers', dict(me.headers))
        print('me body', me.text)

asyncio.run(main())
