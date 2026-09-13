from .client import manager
async def start_user_client(): return await manager.start()
async def stop_user_client(): await manager.stop()
