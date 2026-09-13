from __future__ import annotations
import asyncio, shutil, subprocess
from pathlib import Path

class AudioError(RuntimeError):pass

async def to_voice(src:Path,dst:Path):
    if not shutil.which('ffmpeg'): raise AudioError('ffmpeg غير مثبت')
    cmd=['ffmpeg','-y','-i',str(src),'-vn','-c:a','libopus','-b:a','48k','-vbr','on',str(dst)]
    p=await asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    out,err=await p.communicate()
    if p.returncode!=0: raise AudioError(err.decode(errors='ignore')[-1500:])
    return dst
