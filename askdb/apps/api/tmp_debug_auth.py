import asyncio, os
os.environ['ENVIRONMENT']='development'
os.environ['JWT_SECRET_KEY']='test-secret-key-that-is-long-enough-for-tests-xx'
os.environ['CORS_ALLOWED_ORIGINS']='http://localhost:3000'
os.environ['RATE_LIMIT_LOGIN_PER_MINUTE']='5'
os.environ['AUTH_BYPASS']='false'
os.environ['TRUSTED_HOSTS']='testserver,localhost'

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

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
        async def check_app_database(self): return True, 'ok'
        async def check_analytics_database(self, industry): return False, 'not_configured_in_tests'

    app.dependency_overrides[get_app_session] = override_session
    app.dependency_overrides[get_registry] = StubRegistry
    app.state.login_limiter = FixedWindowRateLimiter(limit=5, window_seconds=60)

    async with session_factory() as session:
        session.add(User(
            email='admin@askdb.local',
            username='admin',
            full_name='Admin',
            password_hash=hash_password('Admin123!'),
            role=Role.ADMIN,
            default_industry=Industry.AUTOMOTIVE,
            is_active=True,
        ))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        r = await client.post('/api/v1/auth/login', json={'username':'admin@askdb.local','password':'Admin123!','remember_me':True})
        print('status', r.status_code)
        print('json', r.text)
        print('set-cookie', r.headers.get_list('set-cookie'))
        print('cookies', client.cookies)
        print('access cookie in jar', client.cookies.get('nql_access'))
        print('csrf cookie in jar', client.cookies.get('nql_csrf'))
        r2 = await client.get('/api/v1/auth/me')
        print('me status', r2.status_code)
        print('me body', r2.text)
        print('me request headers', r2.request.headers)

asyncio.run(main())
