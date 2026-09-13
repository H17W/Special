from dataclasses import dataclass, field
from collections import defaultdict
@dataclass
class Nav:
    stack:list[str]=field(default_factory=list)
    data:dict=field(default_factory=dict)
class Navigation:
    def __init__(self): self._s=defaultdict(Nav)
    def push(self,uid,screen): self._s[uid].stack.append(screen)
    def current(self,uid): return self._s[uid].stack[-1] if self._s[uid].stack else 'main'
    def back(self,uid):
        n=self._s[uid]
        if n.stack:n.stack.pop()
        return n.stack[-1] if n.stack else 'main'
    def clear(self,uid): self._s.pop(uid,None)
    def set(self,uid,key,val): self._s[uid].data[key]=val
    def get(self,uid,key,default=None): return self._s[uid].data.get(key,default)
nav=Navigation()
