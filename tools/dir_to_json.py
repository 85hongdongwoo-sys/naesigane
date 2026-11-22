"""상가(상권)정보 CSV → data/dir.json (병원·전문가 묶음별·지역별 목록, 최대 100곳)
사용: python3 tools/dir_to_json.py <CSV 폴더>
"""
import sys, os, csv, glob, json, re
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build
META = json.load(open(os.path.join(ROOT, 'data', 'dir_meta.json'), encoding='utf-8'))
SUB = {sub: (sec, g) for sec, m in META.items() for g, gm in m['groups'].items() for sub in gm['subs']}
known = set(json.load(open(os.path.join(ROOT, 'data', 'release_order.json'), encoding='utf-8')))
known |= set(json.load(open(os.path.join(ROOT, 'data', 'apartments.json'), encoding='utf-8'))['regions'])
compact = {sd + ' ' + rest.replace('시 ', ''): r for r in known for sd, rest in [r.split(' ', 1)]}
out = {}
for fp in sorted(glob.glob(os.path.join(sys.argv[1], '*.csv'))):
    for x in csv.DictReader(open(fp, encoding='utf-8-sig')):
        k = SUB.get(x['상권업종소분류명'])
        if not k:
            continue
        addr = build.norm_addr(x['도로명주소'] or x['지번주소'])
        reg = build.region_of(addr)
        if reg not in known:
            reg = compact.get(reg) if reg else None
            if reg not in known:
                sg = build.SIDO_RENAME.get(x['시도명'], x['시도명']) + ' ' + x['시군구명']
                reg = sg if sg in known else compact.get(sg)
        if not reg:
            continue
        name = x['상호명'].strip() + (' ' + x['지점명'].strip() if x['지점명'].strip() else '')
        short = ' '.join(addr.split(' ')[2:]) if addr.count(' ') >= 2 else addr
        if reg.count(' ') >= 2 and short.startswith(reg.split(' ')[-1] + ' '):
            short = short.split(' ', 1)[1]
        try:
            lat, lng = round(float(x['위도']), 5), round(float(x['경도']), 5)
        except ValueError:
            lat = lng = None
        out.setdefault(k[0], {}).setdefault(k[1], {}).setdefault(reg, []).append([name, short, x['행정동명'] or x['법정동명'], lat, lng, x['상권업종소분류명']])
tot = {}
for sec in out:
    for g in out[sec]:
        for reg, lst in list(out[sec][g].items()):
            dc = Counter(r[2] for r in lst)
            lst = sorted({(r[0], r[1]): r for r in lst}.values(), key=lambda r: (-dc[r[2]], r[2], r[0]))
            out[sec][g][reg] = {'n': len(lst), 'list': lst[:100]}
            tot[g] = tot.get(g, 0) + len(lst)
date = re.search(r'(\d{6})', os.path.basename(glob.glob(os.path.join(sys.argv[1], '*.csv'))[0]))
json.dump({'_date': date.group(1) if date else '', 'sections': out}, open(os.path.join(ROOT, 'data', 'dir.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(tot)
