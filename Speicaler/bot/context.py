from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Session:
    mode:str=''
    data:dict|None=None

SESSIONS:dict[int,Session]={}

def session(uid): return SESSIONS.setdefault(uid,Session(data={}))
def clear(uid): SESSIONS.pop(uid,None)
