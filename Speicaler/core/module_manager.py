class ModuleManager:
    def __init__(self): self.modules={}
    def add(self,name,module): self.modules[name]=module
    async def start(self):
        for m in self.modules.values():
            fn=getattr(m,'start',None)
            if fn: await fn()
    async def stop(self):
        for m in reversed(list(self.modules.values())):
            fn=getattr(m,'stop',None)
            if fn: await fn()
