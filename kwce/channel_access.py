"""Guards for synthetic channel fixtures used inside the isolated test runtime."""
import hashlib,json
from pathlib import Path,PurePosixPath

def validate_fixtures(root,channel):
    root=Path(root).resolve()
    meta=json.loads((root/'fixture-manifest.json').read_text(encoding='utf-8'))
    if meta.get('channel')!=channel or meta.get('synthetic')is not True:raise ValueError('Wrong synthetic fixture identity')
    rows=meta['files'];names=[r['path']for r in rows]
    if not rows or len(rows)>200 or len(set(names))!=len(names):raise ValueError('Invalid fixture list')
    for row in rows:
        rel=PurePosixPath(row['path'])
        if rel.is_absolute()or'..'in rel.parts or len(rel.parts)!=1:raise ValueError('Fixture traversal refused')
        p=root/row['path']
        if p.is_symlink()or p.is_junction()or not p.resolve().is_relative_to(root):raise ValueError('Indirect fixture path')
        data=p.read_bytes()
        if len(data)!=row['size']or len(data)>16*1024*1024 or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Fixture hash or size differs')
    routes=(root/'routes.tsv').read_bytes()
    if hashlib.sha256(routes).hexdigest()!=meta['routes_sha256']:raise ValueError('Route manifest differs')
    seen=set()
    for line in routes.decode('ascii').splitlines():
        if not line or line.startswith('#'):continue
        route,name=line.split('\t')
        if route in seen or name not in names:raise ValueError('Duplicate or unlisted route')
        seen.add(route)
        method,path=route.split(' ',1)
        if method not in['*','GET','HEAD','POST']or not path.startswith('/')or'..'in path or'?'in path:raise ValueError('Unsafe fixture route')
    if not seen:raise ValueError('No local routes')
    return len(rows),len(seen)
