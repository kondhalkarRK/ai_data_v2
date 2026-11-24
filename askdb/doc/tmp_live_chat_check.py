import json
from pathlib import Path
import httpx

base = 'http://127.0.0.1:8123'
out_path = Path(__file__).with_name('tmp_live_chat_output.txt')

lines = []
client = httpx.Client(base_url=base, follow_redirects=True, timeout=60)

health = client.get('/health')
lines.append(f'HEALTH_STATUS {health.status_code}')
lines.append(f'HEALTH_BODY {json.dumps(health.json(), indent=2, default=str)}')

login = client.post('/api/v1/auth/login', json={'username': 'admin@example.com', 'password': 'Vh7!kRq2$mTx9pLw'})
lines.append(f'LOGIN_STATUS {login.status_code}')
lines.append(f'LOGIN_BODY {login.text[:1200]}')

me = client.get('/api/v1/auth/me')
lines.append(f'ME_STATUS {me.status_code}')
lines.append(f'ME_BODY {me.text[:1200]}')

chat = client.post('/api/v1/chat/ask-sync', json={'question': 'Show total sales per year', 'conversation_id': None, 'web_retrieval': False})
lines.append(f'CHAT_STATUS {chat.status_code}')
lines.append(f'CHAT_BODY {chat.text[:2000]}')

client.close()
out_path.write_text('\n\n'.join(lines), encoding='utf-8')
