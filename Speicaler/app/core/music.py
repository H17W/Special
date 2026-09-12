"""Safe music search/download from Internet Archive items that expose downloadable audio.
Only files explicitly exposed by the source are used; no DRM/circumvention is attempted.
"""
import asyncio, json, urllib.parse, urllib.request
from pathlib import Path

BASE = 'https://archive.org'

def _get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'SpecialBot/1.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

def _download(url, path):
    req = urllib.request.Request(url, headers={'User-Agent':'SpecialBot/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
        while True:
            chunk = r.read(1024*256)
            if not chunk: break
            f.write(chunk)

def _search(query, rows=8):
    q = urllib.parse.quote(f'({query}) AND mediatype:audio')
    url = f'{BASE}/advancedsearch.php?q={q}&fl[]=identifier&fl[]=title&rows={rows}&page=1&output=json'
    data = _get_json(url)
    return data.get('response', {}).get('docs', [])

def _audio_file(identifier):
    data = _get_json(f'{BASE}/metadata/{urllib.parse.quote(identifier)}')
    files = data.get('files') or []
    preferred = []
    for item in files:
        name = str(item.get('name',''))
        if name.lower().endswith(('.mp3','.ogg','.m4a','.wav','.flac')):
            preferred.append(item)
    preferred.sort(key=lambda x: (0 if str(x.get('name','')).lower().endswith('.mp3') else 1, int(x.get('size') or 10**18)))
    if not preferred: return None
    name = preferred[0]['name']
    return f'{BASE}/download/{urllib.parse.quote(identifier)}/{urllib.parse.quote(name)}', name

async def search_music(query, limit=8):
    return await asyncio.to_thread(_search, query, limit)

async def download_music(identifier, output_dir):
    info = await asyncio.to_thread(_audio_file, identifier)
    if not info: return None
    url, name = info
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    safe = ''.join(c for c in name if c.isalnum() or c in '._- ')[:120] or 'audio.mp3'
    path = output_dir / safe
    await asyncio.to_thread(_download, url, path)
    return path
