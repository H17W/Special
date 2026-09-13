import asyncio
class JobQueue:
    def __init__(self,workers=3): self.q=asyncio.Queue(); self.tasks=[]; self.workers=workers
    async def start(self):
        if self.tasks:return
        self.tasks=[asyncio.create_task(self._worker()) for _ in range(self.workers)]
    async def _worker(self):
        while True:
            fn,args,kwargs=await self.q.get()
            try: await fn(*args,**kwargs)
            except Exception: pass
            finally:self.q.task_done()
    async def put(self,fn,*args,**kwargs): await self.q.put((fn,args,kwargs))
    async def stop(self):
        for t in self.tasks:t.cancel()
        self.tasks=[]
queue=JobQueue()
