import aiohttp
async def search_tracks(query,limit=8):
    url='https://api.deezer.com/search'
    async with aiohttp.ClientSession() as s:
        async with s.get(url,params={'q':query,'limit':limit},timeout=12) as r:
            data=await r.json()
    return [{'title':x['title'],'artist':x['artist']['name'],'url':x['link'],'cover':x['album']['cover_medium']} for x in data.get('data',[])]
