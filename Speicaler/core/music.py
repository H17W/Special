from __future__ import annotations
import aiohttp

async def search_tracks(query:str,limit=8):
    query=query.strip()
    if not query:return []
    url='https://api.deezer.com/search'
    async with aiohttp.ClientSession() as s:
        async with s.get(url,params={'q':query,'limit':limit},timeout=15) as r:
            r.raise_for_status(); data=await r.json()
    return [{'id':x['id'],'title':x.get('title',''),'artist':x.get('artist',{}).get('name',''),'album':x.get('album',{}).get('title',''),'cover':x.get('album',{}).get('cover_medium',''),'url':x.get('link','')} for x in data.get('data',[])]
