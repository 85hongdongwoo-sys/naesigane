"""K-apt '단지 기본정보' 엑셀 → data/apartments.json (지역별 단지 목록)
사용: python3 tools/kapt_to_json.py 20261120_단지_기본정보.xlsx
"""
import sys, json, os, re, warnings
import openpyxl
warnings.filterwarnings('ignore')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build

wb = openpyxl.load_workbook(sys.argv[1], read_only=True)
ws = wb.worksheets[0]; ws.reset_dimensions()
rows = list(ws.iter_rows(values_only=True))
hdr = rows[1]; ix = {h: i for i, h in enumerate(hdr)}
ours = {s['region'] for s in build.load_shops()}
compact = {}
for r in ours:
    sd, rest = r.split(' ', 1)
    compact[sd + ' ' + rest.replace('시 ', '')] = r
out = {}
for r in rows[2:]:
    g = lambda k: (r[ix[k]] or '') if ix.get(k) is not None else ''
    sd = build.SIDO_RENAME.get(g('시도'), g('시도')); sg = g('시군구')
    if not sd or not sg or sg == 'None':
        continue
    reg = f'{sd} {sg}'
    reg = reg if reg in ours else compact.get(reg, reg)
    try: hh = int(float(g('세대수') or 0))
    except ValueError: hh = 0
    try: dis = int(float(g('연간소독횟수') or 0))
    except ValueError: dis = 0
    year = int(str(g('사용승인일'))[:4]) if re.match(r'\d{4}', str(g('사용승인일'))) else 0
    out.setdefault(reg, []).append([g('단지명').strip(), g('동리') or g('읍면'), year, hh, g('난방방식'), g('복도유형'), dis])
for v in out.values():
    v.sort(key=lambda x: -x[3])
meta = {'_source': '국토교통부 K-apt 관리비공개의무단지 기본정보', '_date': re.sub(r'\D', '', os.path.basename(sys.argv[1]))[:8]}
json.dump({**meta, 'regions': out}, open(os.path.join(ROOT, 'data', 'apartments.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(len(out), '지역', sum(len(v) for v in out.values()), '단지')
