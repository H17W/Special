from aiogram import BaseMiddleware
from app.core.database import account_scope

class AccountContextMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, 'from_user', None)
        uid = str(user.id) if user else 'owner'
        with account_scope(uid):
            return await handler(event, data)
