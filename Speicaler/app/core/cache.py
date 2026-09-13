import time,asyncio
class TTLCache:
    def __init__(self,maxsize=256): self.maxsize=maxsize; self.data={}; self.lock=asyncio.Lock()
    async def get(self,key):
        async with self.lock:
            x=self.data.get(key)
            if not x:return None
            if x[1]<=time.monotonic(): self.data.pop(key,None); return None
            return x[0]
    async def set(self,key,val,ttl=60):
        async with self.lock:
            if len(self.data)>=self.maxsize:self.data.pop(next(iter(self.data)))
            self.data[key]=(val,time.monotonic()+ttl)
    async def clear(self):
        async with self.lock:self.data.clear()
cache=TTLCache()
