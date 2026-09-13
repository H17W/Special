import asyncio
from app.core.database import init_database
from app.user.client import start_user_client

if __name__ == '__main__':
    asyncio.run(start_user_client())
