"""유사도 5% 미만 페이지만 검색에 남긴다 (배포 마지막 단계).
data-sim 브랜치 sim.json 의 keep 목록(이미 남긴 페이지 모두와 겹침 5% 미만)에 없는 페이지는
robots noindex,follow + hl-sim-hold 표시를 달고, sitemap*.xml·rss.xml 에서 뺀다.
다음 유사도 측정 때 hl-sim-hold 페이지도 다시 재므로, 고쳐서 5% 미만이 되면 자동으로 풀린다.
사용: python3 build/patch_simgate.py _site sim.json"""
import json, os, re, sys, urllib.parse
root, simf = sys.argv[1], sys.argv[2]
B = 'https://naesigane.co.kr'
try:
    d = json.load(open(simf, encoding='utf-8'))
    keep = {urllib.parse.unquote(u) for u in d['keep']}
except Exception as e:
    print('simgate: no keep list, skipped', e); sys.exit(0)
if len(keep) < 50:
    print('simgate: keep list too small, skipped'); sys.exit(0)
ROB = re.compile(r'<meta\s+name=["\'](robots|googlebot)["\'][^>]*>\s*', re.I)
held = 0; kept = 0
for dd, _, fs in os.walk(root):
    rel0 = os.path.relpath(dd, root).split(os.sep)[0]
    if rel0 in ('assets', 'widget', 'embed', '.well-known'):
        continue
    for fn in fs:
        if not fn.endswith('.html') or fn == '404.html':
            continue
        f = os.path.join(dd, fn)
        rel = '/' + os.path.relpath(f, root).replace(os.sep, '/')
        u = rel[:-10] if rel.endswith('/index.html') else rel
        s = open(f, encoding='utf-8', errors='ignore').read()
        if 'http-equiv="refresh"' in s.lower() or '<head' not in s:
            continue
        if u in keep or rel in keep:
            kept += 1; continue
        s2 = ROB.sub('', s)
        s2 = re.sub(r'(<head[^>]*>)', r'\1<meta name="robots" content="noindex,follow"><meta name="hl-sim-hold" content="1">', s2, count=1)
        open(f, 'w', encoding='utf-8').write(s2); held += 1
def keep_url(loc):
    p = urllib.parse.unquote(loc[len(B):] if loc.startswith(B) else loc)
    return (p or '/') in keep or (p + 'index.html') in keep
for fn in os.listdir(root):
    fp = os.path.join(root, fn)
    if fn.startswith('sitemap') and fn.endswith('.xml'):
        s = open(fp, encoding='utf-8').read()
        s2 = re.sub(r'\s*<url>\s*<loc>([^<]+)</loc>.*?</url>', lambda m: m.group(0) if keep_url(m.group(1).strip()) else '', s, flags=re.S)
        open(fp, 'w', encoding='utf-8').write(s2)
    elif fn == 'rss.xml':
        s = open(fp, encoding='utf-8').read()
        s2 = re.sub(r'<item>.*?<link>([^<]+)</link>.*?</item>', lambda m: m.group(0) if keep_url(m.group(1).strip()) else '', s, flags=re.S)
        open(fp, 'w', encoding='utf-8').write(s2)
print('simgate: kept', kept, 'held (noindex)', held)
