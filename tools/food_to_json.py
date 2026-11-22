"""상가(상권)정보 CSV → data/food.json (음식점 묶음별·지역별 목록, 지역·묶음당 최대 150곳)
사용: python3 tools/food_to_json.py <CSV 폴더>
"""
import sys, os, csv, glob, json, re
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build
GROUPS = {
    '고기집': ['돼지고기 구이/찜', '소고기 구이/찜', '닭/오리고기 구이/찜', '곱창 전골/구이'],
    '한식당': ['백반/한정식', '국/탕/찌개류', '국수/칼국수', '냉면/밀면', '기타 한식 음식점', '전/부침개'],
    '횟집': ['횟집', '해산물 구이/찜', '일식 회/초밥', '복 요리 전문'],
    '중식당': ['중국집', '마라탕/훠궈'],
    '족발-보쌈': ['족발/보쌈'],
    '치킨': ['치킨'],
    '피자': ['피자'],
    '분식': ['김밥/만두/분식'],
    '일식-돈가스': ['일식 카레/돈가스/덮밥', '일식 면 요리', '기타 일식 음식점'],
    '양식': ['경양식', '파스타/스테이크', '패밀리레스토랑', '기타 서양식 음식점'],
    '뷔페': ['뷔페'],
    '아시아음식': ['베트남식 전문', '기타 동남아식 전문'],
}
SUB = {s: g for g, ss in GROUPS.items() for s in ss}
CAP = 150
known = set(json.load(open(os.path.join(ROOT, 'data', 'release_order.json'), encoding='utf-8')))
known |= set(json.load(open(os.path.join(ROOT, 'data', 'apartments.json'), encoding='utf-8'))['regions'])
compact = {}
for r in known:
    sd, rest = r.split(' ', 1)
    compact[sd + ' ' + rest.replace('시 ', '')] = r
out, total = {}, Counter()
for fp in sorted(glob.glob(os.path.join(sys.argv[1], '*.csv'))):
    for x in csv.DictReader(open(fp, encoding='utf-8-sig')):
        if x['상권업종대분류명'] != '음식':
            continue
        g = SUB.get(x['상권업종소분류명'])
        if not g:
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
        out.setdefault(g, {}).setdefault(reg, []).append([name, short, x['행정동명'] or x['법정동명'], lat, lng, x['상권업종소분류명']])
for g in out:
    for reg, lst in list(out[g].items()):
        total[g] += len(lst)
        dc = Counter(r[2] for r in lst)
        lst = sorted({(r[0], r[1]): r for r in lst}.values(), key=lambda r: (-dc[r[2]], r[2], r[0]))
        out[g][reg] = {'n': len(lst), 'list': lst[:CAP]}
date = re.search(r'(\d{6})', os.path.basename(glob.glob(os.path.join(sys.argv[1], '*.csv'))[0]))
json.dump({'_source': '소상공인시장진흥공단 상가(상권)정보', '_date': date.group(1) if date else '', 'groups': out},
          open(os.path.join(ROOT, 'data', 'food.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(dict(total))
