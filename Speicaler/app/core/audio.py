import asyncio
from pathlib import Path
class AudioError(Exception): pass
async def to_voice(src:Path,dst:Path):
    proc=await asyncio.create_subprocess_exec('ffmpeg','-y','-i',str(src),'-vn','-c:a','libopus','-b:a','48k',str(dst),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    _,err=await proc.communicate()
    if proc.returncode!=0: raise AudioError(err.decode(errors='ignore')[-500:])
    return dst
