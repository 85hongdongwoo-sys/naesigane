"""소상공인시장진흥공단 상가(상권)정보 CSV들 → data/stores.json (업종별·지역별 업체 이름 목록)
사용: python3 tools/sbiz_to_json.py <CSV 폴더>
전화번호는 없어요. 화면에서 '전화'를 누를 때 카카오에서 찾아 연결해요.
"""
import sys, os, csv, glob, json, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build

REPAIR = {'가전제품 수리업', '그 외 기타 개인/가정용품 수리업', '사업시설 유지·관리 서비스업', '철물/공구 소매업',
          '건설/건축자재 소매업', '기타 건설/건축자재 소매업', '인테리어 디자인업', '가전제품 소매업',
          '산업설비; 운송장비 및 공공장소 청소업', '건축물 일반 청소업', '소독; 구충 및 방제 서비스업',
          '전기용품/조명장치 소매업', '주방/가정용품 소매업', '기타 엔지니어링 서비스업'}
# 업종: (허용 소분류, 상호 정규식) — 정규식이 None이면 소분류만 맞으면 됨
RULES = {
    '보일러-고장': (REPAIR, r'보일러|나비엔|린나이|귀뚜라미|난방'),
    '수도-동파': (REPAIR, r'설비|배관|수도|동파'),
    '하수구-막힘': (REPAIR, r'하수구|배관|뚫어|막힘|변기'),
    '누수-탐지': (REPAIR, r'누수'),
    '수전-교체': (REPAIR, r'설비|수전|욕실|수도'),
    '열쇠-도어락': (REPAIR | {'기타 개인/가정용품 대여업'}, r'열쇠|도어락|자물쇠|게이트맨|키\s|키$|^키'),
    '전기-고장': (REPAIR, r'전기|전업사|전력'),
    '유리-파손': (REPAIR, r'유리|샷시|섀시|창호|새시'),
    '정화조-청소': (REPAIR, r'정화조|분뇨|환경위생'),
    '방역-해충': ({'소독; 구충 및 방제 서비스업'}, None),
    '비둘기-벌집': ({'소독; 구충 및 방제 서비스업'} | REPAIR, r'비둘기|조류|벌집|퇴치'),
    '에어컨-고장': (REPAIR, r'에어컨|냉난방|공조'),
    '방수': (REPAIR, r'방수'),
    '입주청소': ({'건축물 일반 청소업'}, None),
    '줄눈-탄성코트': (REPAIR, r'줄눈|탄성'),
    '유품정리': ({'건축물 일반 청소업', '기타 개인/가정용품 대여업'} | REPAIR, r'유품|특수청소'),
    '사다리차': ({'건설기계/장비 대여업', '기타 운송장비 대여업', '기타 산업용 기계/장비 대여업'}, r'사다리|스카이'),
    '셔터-자동문': (REPAIR, r'셔터|자동문'),
    '업소용-냉장고': (REPAIR, r'냉장|냉동|쇼케이스'),
    '간판-수리': ({'명함/간판/광고물 제작', '광고물 설계/제작업', '옥외/전시 광고 대행업'}, None),
    '팝업-인테리어': ({'인테리어 디자인업', '전시/컨벤션/행사 대행 서비스업'}, None),
}
RX = {k: re.compile(v[1]) if v[1] else None for k, v in RULES.items()}
known = set(json.load(open(os.path.join(ROOT, 'data', 'release_order.json'), encoding='utf-8')))
apts = json.load(open(os.path.join(ROOT, 'data', 'apartments.json'), encoding='utf-8'))['regions']
known |= set(apts)
compact = {}
for r in known:
    sd, rest = r.split(' ', 1)
    compact[sd + ' ' + rest.replace('시 ', '')] = r
    compact[sd + ' ' + rest.split(' ')[-1]] = compact.get(sd + ' ' + rest.split(' ')[-1], r)

out, miss = {}, {}
for fp in sorted(glob.glob(os.path.join(sys.argv[1], '*.csv'))):
    for x in csv.DictReader(open(fp, encoding='utf-8-sig')):
        sub = x['상권업종소분류명']
        kinds = [k for k, (cats, _) in RULES.items() if sub in cats and (RX[k] is None or RX[k].search(x['상호명']))]
        if not kinds:
            continue
        addr = build.norm_addr(x['도로명주소'] or x['지번주소'])
        sd = addr.split(' ', 1)[0]
        reg = build.region_of(addr)
        if reg not in known:
            reg = compact.get(reg, reg) if reg else None
            if reg not in known:
                sg = build.SIDO_RENAME.get(x['시도명'], x['시도명']) + ' ' + x['시군구명']
                reg = sg if sg in known else compact.get(sg)
        if not reg:
            miss[x['시도명'] + ' ' + x['시군구명']] = miss.get(x['시도명'] + ' ' + x['시군구명'], 0) + 1
            continue
        name = x['상호명'].strip() + (' ' + x['지점명'].strip() if x['지점명'].strip() else '')
        short = ' '.join(addr.split(' ')[2:]) if addr.count(' ') >= 2 else addr
        if reg.count(' ') >= 2 and short.startswith(reg.split(' ')[-1]):
            short = short.split(' ', 1)[1] if ' ' in short else short
        try:
            lat, lng = round(float(x['위도']), 5), round(float(x['경도']), 5)
        except ValueError:
            lat = lng = None
        rec = [name, short, x['행정동명'] or x['법정동명'], lat, lng]
        for k in kinds:
            out.setdefault(k, {}).setdefault(reg, []).append(rec)
for k in out:
    for reg, lst in out[k].items():
        seen, uniq = set(), []
        for r in lst:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key); uniq.append(r)
        out[k][reg] = sorted(uniq, key=lambda r: r[0])
date = re.search(r'(\d{6})', os.path.basename(glob.glob(os.path.join(sys.argv[1], '*.csv'))[0]))
json.dump({'_source': '소상공인시장진흥공단 상가(상권)정보', '_date': date.group(1) if date else '', 'kinds': out},
          open(os.path.join(ROOT, 'data', 'stores.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print({k: sum(len(v) for v in out[k].values()) for k in RULES})
print('지역 못 찾음', sorted(miss.items(), key=lambda x: -x[1])[:15])
