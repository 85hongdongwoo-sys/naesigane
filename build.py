#!/usr/bin/env python3
"""내시간에 정적 사이트 생성기.

python3 build.py            -> _site/ 에 사이트를 만들어요.
데이터: data/raw/*.csv (공공데이터포털 전국자동차정비업체표준데이터, CP949 또는 UTF-8)
       data/raw/*.psv (샘플: 이름|종류|주소|위도|경도|등록일|면적|시작|종료|전화, 파일 이름으로 지역 지정)
공개 지역은 config.json 의 released_regions 로 정해요.
"""
import csv, glob, html, json, math, os, re, shutil, sys, datetime
from urllib.parse import quote
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, '_site')
CFG = json.load(open(os.path.join(ROOT, 'config.json'), encoding='utf-8'))
RELEASED = []  # main()에서 채움: 공개된 지역 전체
TODAY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()  # 한국 날짜
BASE = CFG['base_url'].rstrip('/')
E = html.escape

TYPE_NAMES = {'1': '자동차종합정비업', '2': '소형자동차종합정비업', '3': '자동차전문정비업', '4': '원동기전문정비업'}
TYPE_SHORT = {'1': '종합정비', '2': '소형 종합정비', '3': '전문정비', '4': '원동기 전문'}
TYPE_DESC = {
    '1': '모든 차종의 점검·정비와 큰 수리(판금·도장 포함)를 할 수 있어요.',
    '2': '승용차·소형 승합·소형 화물차의 점검·정비와 큰 수리를 할 수 있어요.',
    '3': '엔진오일·타이어·배터리·브레이크처럼 정해진 범위의 정비를 해요. 동네 카센터가 대부분 여기예요.',
    '4': '엔진(원동기) 정비를 전문으로 해요.',
}
SAMPLE_REGIONS = {'yeonsu': '인천광역시 연수구', 'jemulpo': '인천광역시 제물포구'}
SIDO_SHORT = {'서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천', '광주광역시': '광주', '대전광역시': '대전',
              '울산광역시': '울산', '세종특별자치시': '세종', '경기도': '경기', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남',
              '전북특별자치도': '전북', '전라남도': '전남', '전남광주통합특별시': '전남광주', '경상북도': '경북', '경상남도': '경남', '제주특별자치도': '제주'}

# ---------------------------------------------------------------- data

# 옛 시·도 이름 → 지금 이름 (2026.7.1 전남광주통합특별시 출범 등)
SIDO_RENAME = {'광주광역시': '전남광주통합특별시', '전라남도': '전남광주통합특별시', '강원도': '강원특별자치도', '전라북도': '전북특별자치도'}

def norm_addr(addr):
    a = addr.split(' ', 1)
    if len(a) == 2 and a[0] in SIDO_RENAME:
        return SIDO_RENAME[a[0]] + ' ' + a[1]
    return addr

def region_of(addr):
    a = addr.split()
    if len(a) < 2:
        return None
    sido, sgg = a[0], a[1]
    if re.search(r'[시군]$', sgg) and len(a) > 2 and re.search(r'구$', a[2]):
        sgg = sgg + ' ' + a[2]
    if not re.search(r'[시군구]$', sgg):
        return None
    return sido + ' ' + sgg

def dong_of(addr):
    m = re.search(r'\(([가-힣0-9]{1,8}(?:동|읍|면|가))(?:[,)])', addr)
    return m.group(1).strip() if m and len(m.group(1)) >= 2 else ''

def norm_code(v):
    v = str(v or '').strip()
    return v.lstrip('0') or v

def load_shops():
    shops = []
    for path in glob.glob(os.path.join(ROOT, 'data', 'raw', '*.csv')):
        raw = open(path, 'rb').read()
        for enc in ('utf-8-sig', 'cp949'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        for r in csv.DictReader(text.splitlines()):
            addr = norm_addr((r.get('소재지도로명주소') or r.get('소재지지번주소') or '').strip())
            shops.append(dict(name=r.get('자동차정비업체명', '').strip(), type=norm_code(r.get('자동차정비업체종류')), addr=addr,
                              lat=r.get('위도'), lng=r.get('경도'), reg=r.get('사업등록일자', ''), area=r.get('면적', ''),
                              status=norm_code(r.get('영업상태')), open=r.get('운영시작시각', ''), close=r.get('운영종료시각', ''),
                              phone=(r.get('전화번호') or '').strip(), src_date=r.get('데이터기준일자', '')))
    if not shops:
        for path in glob.glob(os.path.join(ROOT, 'data', 'raw', '*.psv')):
            key = os.path.splitext(os.path.basename(path))[0]
            prefix = SAMPLE_REGIONS.get(key)
            for line in open(path, encoding='utf-8'):
                f = line.rstrip('\n').split('|')
                if len(f) < 10:
                    continue
                shops.append(dict(name=f[0], type=f[1], addr=prefix + ' ' + f[2], lat=f[3], lng=f[4], reg=f[5], area=f[6],
                                  status='1', open=f[7], close=f[8], phone=f[9], src_date=CFG['data_date']))
    ovr_path = os.path.join(ROOT, 'data', 'phone_overrides.json')
    ovr = {k: v for k, v in json.load(open(ovr_path, encoding='utf-8')).items() if not k.startswith('_')} if os.path.exists(ovr_path) else {}
    for s in shops:
        if not (s.get('phone') or '').strip():
            for k, v in ovr.items():
                nm, ad = k.split('|', 1)
                if s['name'] == nm and ad in s['addr']:
                    s['phone'] = v
    hid_path = os.path.join(ROOT, 'data', 'hidden_shops.json')
    hidden = [h.split('|', 1) for h in json.load(open(hid_path, encoding='utf-8')).get('hidden', [])] if os.path.exists(hid_path) else []
    shops = [s for s in shops if not any(s['name'] == nm and ad in s['addr'] for nm, ad in hidden)]
    out = []
    for s in shops:
        if s['status'] != '1' or not s['name'] or not s['addr']:
            continue
        try:
            s['lat'], s['lng'] = float(s['lat']), float(s['lng'])
        except (TypeError, ValueError):
            s['lat'] = s['lng'] = None
        s['region'] = region_of(s['addr'])
        if not s['region']:
            continue
        s['dong'] = dong_of(s['addr'])
        m = re.match(r'(\d{4})', s['reg'] or '')
        s['year'] = int(m.group(1)) if m else None
        s['phone'] = s['phone'] if re.search(r'\d{3,}', s['phone'] or '') else ''
        out.append(s)
    return out

# ---------------------------------------------------------------- helpers

def slug_region(region):
    sido, rest = region.split(' ', 1)
    return sido + '/' + rest.replace(' ', '-')

def url_path(*parts):
    return '/' + '/'.join(p.strip('/') for p in parts if p) + '/'

def abs_url(path):
    return BASE + quote(path)

def short_region(region):
    sido, rest = region.split(' ', 1)
    return SIDO_SHORT.get(sido, sido) + ' ' + rest

def gu_name(region):
    return region.split(' ', 1)[1]

def josa(word, a, b):
    ch = word[-1]
    if '가' <= ch <= '힣':
        return a if (ord(ch) - 0xAC00) % 28 else b
    return a

def km(a, b):
    return math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 88)

# ---------------------------------------------------------------- layout

def page(title, desc, path, body, crumbs=None, jsonld=None, extra_head='', noindex=False, scripts=''):
    canonical = abs_url(path)
    ld = ''
    items = list(jsonld or [])
    if crumbs:
        items.append({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': abs_url(p)} for i, (n, p) in enumerate(crumbs)]})
    for it in items:
        ld += '<script type="application/ld+json">' + json.dumps(it, ensure_ascii=False) + '</script>\n'
    crumb_html = ''
    if crumbs:
        crumb_html = '<nav class="crumbs" aria-label="현재 위치">' + ' › '.join(
            ('<a href="%s">%s</a>' % (E(p), E(n)) if i < len(crumbs) - 1 else '<span>%s</span>' % E(n)) for i, (n, p) in enumerate(crumbs)) + '</nav>'
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
{'<meta name="robots" content="noindex, follow">' if noindex else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="내시간에">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
<meta name="theme-color" content="#1B64DA">
<meta name="naver-site-verification" content="97956313d2e74474464ffa2d5116351dfbe48f90">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="/s.css">
{extra_head}{ld}</head>
<body>
<header class="top"><a class="brand" href="/"><img class="logo" src="/favicon.svg" alt="" width="28" height="28"><b>내시간에</b></a><a class="top-owner" href="{E(url_path('사장님'))}">사장님이세요?</a></header>
<main>
{crumb_html}
{body}
</main>
<footer class="foot">
<p><b>내시간에</b> · 원하는 시간을 먼저 정하면, 동네 업체가 맞춰 답해 드려요.</p>
<p><a href="{E(url_path('소개'))}">소개</a> · <a href="{E(url_path('정보-수정-삭제-요청'))}">정보 수정·삭제 요청</a> · <a href="{E(url_path('개인정보처리방침'))}">개인정보처리방침</a></p>
<p class="muted">업체 정보는 공공데이터를 바탕으로 하며 실제와 다를 수 있어요.</p>
</footer>
<script>window.NSG={{kakao:{json.dumps(CFG.get('kakao_js_key') or '')},api:{json.dumps(CFG.get('supabase_url') or '')},key:{json.dumps(CFG.get('supabase_anon_key') or '')},regions:{json.dumps(sorted(RELEASED) if path.startswith(url_path('요청')) else [], ensure_ascii=False)},sms:{'true' if CFG.get('sms_enabled') else 'false'}}};
window.NSG.call=function(fn,args){{return fetch(NSG.api+'/rest/v1/rpc/'+fn,{{method:'POST',headers:{{'apikey':NSG.key,'Authorization':'Bearer '+NSG.key,'Content-Type':'application/json'}},body:JSON.stringify(args)}}).then(function(r){{return r.json().then(function(j){{if(!r.ok)throw new Error((j&&j.message)||'잠시 뒤 다시 해 주세요');return j}})}})}};</script>
<script src="/app.js" defer></script>
{scripts}
</body>
</html>
'''

def faq_html(faqs):
    return '<section class="card"><h2>자주 묻는 질문</h2>' + ''.join(
        f'<details class="faq"><summary>{E(q)}</summary><p>{E(a)}</p></details>' for q, a in faqs) + '</section>'

def faq_ld(faqs):
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
        {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faqs]}

def owner_cta(what):
    return f'''<section class="card cta-owner">
<h2>{E(what)} 사장님이세요?</h2>
<p>무료로 등록하면 전화번호·영업시간을 직접 고칠 수 있고, 손님이 원하는 시간에 맞춘 예약 요청을 받을 수 있어요.</p>
<a class="btn dark" href="{E(url_path('사장님'))}">무료로 등록 신청하기</a>
</section>'''

# ---------------------------------------------------------------- region page

def hours_text(s):
    if s['open'] and s['close']:
        return f"{s['open']}~{s['close']}"
    return ''

def shop_card(s, i):
    name = E(s['name'])
    t = s['type']
    since = f"{s['year']}년 등록 · {TODAY.year - s['year'] + 1}년째" if s['year'] else ''
    hrs = hours_text(s)
    chips = [f'<span class="chip">{E(TYPE_SHORT.get(t, "정비"))}</span>']
    if hrs:
        chips.append(f'<span class="chip" data-hours="{E(s["open"])}-{E(s["close"])}">평일 {E(hrs)}</span>')
    if since:
        chips.append(f'<span class="chip">{E(since)}</span>')
    q = s['name'] + ' ' + gu_name(s['region']).split()[-1]
    if s['phone']:
        call = f'<a class="btn dark call" href="tel:{E(re.sub(r"[^0-9]", "", s["phone"]))}"><span aria-hidden="true">☎</span> 바로 전화 <small>{E(s["phone"])}</small></a>'
    else:
        call = (f'<button type="button" class="btn dark call lookup" data-name="{name}" data-q="{E(q)}" '
                f'data-lat="{s["lat"] or ""}" data-lng="{s["lng"] or ""}"><span aria-hidden="true">☎</span> 바로 전화</button>')
    nav = f'https://map.naver.com/p/search/{quote(q)}'
    return f'''<article class="shop" id="s{i}" data-type="{E(t)}" data-dong="{E(s['dong'])}" data-phone="{1 if s['phone'] else 0}" data-lat="{s['lat'] or ''}" data-lng="{s['lng'] or ''}">
<div class="shop-head"><span class="pin" aria-hidden="true">{i + 1}</span><h3>{name}</h3></div>
<p class="addr">{E(s['addr'].split(' ', 2)[2] if s['addr'].count(' ') >= 2 else s['addr'])}</p>
<div class="chips">{''.join(chips)}</div>
<div class="actions">{call}<a class="btn ghost" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>
<p class="lookup-note" hidden></p>
</article>'''

def region_page(region, shops, all_regions, region_centers):
    gu = gu_name(region)
    sr = short_region(region)
    n = len(shops)
    tc = Counter(s['type'] for s in shops)
    ph = sum(1 for s in shops if s['phone'])
    hrs = sum(1 for s in shops if s['open'])
    years = [s['year'] for s in shops if s['year']]
    old20 = sum(1 for y in years if TODAY.year - y >= 20)
    avg_age = round(sum(TODAY.year - y + 1 for y in years) / len(years)) if years else None
    newest = max(years) if years else None
    dongs = Counter(s['dong'] for s in shops if s['dong'])
    top_dongs = dongs.most_common(4)
    sat_note = ''
    shops = sorted(shops, key=lambda s: (s['phone'] == '', -(s['year'] or 0) * 0, s['type'], s['name']))
    path = url_path('자동차정비', slug_region(region))
    title = f'{sr} 자동차 정비소 {n}곳 - 전화번호·위치·정비 종류 | 내시간에'
    dong_txt = ', '.join(d for d, _ in top_dongs)
    desc = f'{region} 자동차 정비소 {n}곳의 전화번호, 위치, 정비 종류(종합·전문)를 한눈에. ' + (f'{dong_txt} 등 동네별로 찾고 바로 전화하세요.' if dong_txt else '바로 전화하세요.')

    stat = f'''<div class="stats">
<div><b>{n}곳</b><span>영업 중인 정비소</span></div>
<div><b>{tc.get('1', 0) + tc.get('2', 0)}곳</b><span>종합정비(큰 수리)</span></div>
<div><b>{tc.get('3', 0) + tc.get('4', 0)}곳</b><span>전문정비(카센터)</span></div>
</div>'''
    facts = []
    if top_dongs:
        facts.append(f"가장 많은 동네는 <b>{E(top_dongs[0][0])}</b>({top_dongs[0][1]}곳)이고, " + ', '.join(f'{E(d)} {c}곳' for d, c in top_dongs[1:]) + ' 순이에요.' if len(top_dongs) > 1 else f"정비소가 모인 동네는 <b>{E(top_dongs[0][0])}</b>예요.")
    if avg_age:
        facts.append(f'등록한 지 평균 <b>{avg_age}년</b> 된 곳들이고, 20년 넘게 자리를 지킨 곳이 <b>{old20}곳</b>이에요.' + (f' 가장 최근에 문을 연 곳은 {newest}년 등록이에요.' if newest else ''))
    facts.append(f'전화번호가 공개된 곳은 {ph}곳이에요. 나머지도 <b>바로 전화</b>를 누르면 번호를 찾아 연결해요.' if ph < n else f'{n}곳 모두 전화번호가 공개돼 있어요. 누르면 바로 전화가 걸려요.')
    if hrs:
        facts.append(f'영업시간이 공개된 곳은 {hrs}곳이에요. 토·일 영업은 업체마다 달라서 전화로 확인해 주세요.')

    filters = ['<button type="button" class="f on" data-f="all" aria-pressed="true">전체</button>']
    if tc.get('1', 0) + tc.get('2', 0):
        filters.append('<button type="button" class="f" data-f="big" aria-pressed="false">큰 수리(종합)</button>')
    filters.append('<button type="button" class="f" data-f="small" aria-pressed="false">카센터(전문)</button>')
    if hrs:
        filters.append('<button type="button" class="f" data-f="open" aria-pressed="false">지금 영업 중</button>')
    for d, _ in top_dongs:
        filters.append(f'<button type="button" class="f" data-f="dong:{E(d)}" aria-pressed="false">{E(d)}</button>')

    cards = '\n'.join(shop_card(s, i) for i, s in enumerate(shops))
    pts = [[s['lat'], s['lng'], i + 1] for i, s in enumerate(shops) if s['lat']]
    # nearby regions
    me = region_centers.get(region)
    near = []
    if me:
        near = sorted((km(me, c), r) for r, c in region_centers.items() if r != region and r in all_regions)[:6]
    near_html = ''
    if near:
        near_html = '<section class="card"><h2>가까운 동네 정비소</h2><div class="links">' + ''.join(
            f'<a href="{E(url_path("자동차정비", slug_region(r)))}">{E(short_region(r))} 정비소</a>' for _, r in near) + '</div></section>'

    types_html = '<section class="card"><h2>정비소 종류, 이렇게 달라요</h2><dl class="types">' + ''.join(
        f'<dt>{E(TYPE_NAMES[k])} <span class="muted">{gu} {tc.get(k, 0)}곳</span></dt><dd>{E(TYPE_DESC[k])}</dd>' for k in ('1', '2', '3', '4') if tc.get(k)) + '</dl></section>'

    faqs = [
        (f'{gu}에 자동차 정비소는 몇 곳 있나요?', f'{region}에 등록된 자동차 정비업체 중 영업 중인 곳은 {n}곳이에요. 종합정비(큰 수리 가능) {tc.get("1", 0) + tc.get("2", 0)}곳, 전문정비(카센터) {tc.get("3", 0) + tc.get("4", 0)}곳이에요.'),
        ('사고 수리나 판금·도장은 어디서 하나요?', '판금·도장 같은 큰 수리는 자동차종합정비업이나 소형자동차종합정비업으로 등록된 곳에서 할 수 있어요. 위 목록에서 "큰 수리(종합)"를 누르면 그런 곳만 보여요.'),
        ('엔진오일·타이어 교체는 어디가 편한가요?', '엔진오일, 타이어, 배터리 교체는 동네 카센터(자동차전문정비업)에서 대부분 할 수 있어요. 기다리는 시간을 줄이려면 전화로 미리 시간을 맞추세요.'),
        ('여기 정보는 어디서 가져왔나요?', f'국토교통부 전국자동차정비업체표준데이터(지자체 등록 정보, {CFG["data_date"]} 기준)를 바탕으로 해요. 실제와 다르면 정보 수정·삭제 요청으로 알려 주세요.'),
    ]
    ld = [{'@context': 'https://schema.org', '@type': 'ItemList', 'name': f'{region} 자동차 정비소', 'numberOfItems': n,
           'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'item': {
               '@type': 'AutoRepair', 'name': s['name'],
               'address': {'@type': 'PostalAddress', 'streetAddress': s['addr'], 'addressRegion': region.split()[0], 'addressLocality': gu, 'addressCountry': 'KR'},
               **({'telephone': s['phone']} if s['phone'] else {}),
               **({'geo': {'@type': 'GeoCoordinates', 'latitude': s['lat'], 'longitude': s['lng']}} if s['lat'] else {}),
               **({'openingHours': f"Mo-Fr {s['open']}-{s['close']}"} if s['open'] and s['close'] else {})}}
               for i, s in enumerate(shops)]}, faq_ld(faqs)]
    body = f'''<section class="hero">
<h1>{E(gu)} 자동차 정비소</h1>
<p class="lead">{E(region)}에서 영업 중인 정비소 {n}곳의 전화번호·위치·정비 종류를 모았어요. 누르면 바로 전화가 걸려요.</p>
</section>
{stat}
<section class="card facts"><h2>{E(gu)} 정비소 한눈에</h2><ul>{''.join(f'<li>{f}</li>' for f in facts)}</ul></section>
<section class="list-wrap">
<div id="members" data-region="{E(region)}" data-trade="자동차 정비" hidden></div>
<h2 class="list-title">{E(gu)} 정비소 목록</h2>
<div class="filters" role="group" aria-label="정비소 거르기">{''.join(filters)}</div>
<div id="map" class="map" role="img" aria-label="{E(gu)} 정비소 위치 지도" data-pts='{json.dumps(pts)}'><button type="button" class="btn ghost map-load">지도에서 위치 보기</button></div>
<p class="count" aria-live="polite"><span id="shown">{n}</span>곳</p>
<div class="shops" data-page="20">
{cards}
</div>
<button type="button" class="btn ghost wide more" hidden>더 보기</button>
</section>
<section class="card soon"><h2>원하는 시간에 맞춰 예약하는 기능, 준비 중이에요</h2><p>시간을 정해 요청하면 {E(gu)} 정비소 사장님이 가능한 시간과 예상 가격으로 답해 주는 기능을 만들고 있어요. 사장님 가입이 시작되면 이 동네부터 열려요. <a href="{E(url_path('요청'))}?t={quote('자동차 정비')}&amp;r={quote(region)}">어떻게 요청하는지 미리 보기</a></p></section>
{types_html}
{faq_html(faqs)}
{near_html}
{owner_cta(gu + ' 정비소')}
<p class="source">업체 이름·주소·정비 종류·전화번호·영업시간: 국토교통부 전국자동차정비업체표준데이터({E(region)}, {E(CFG['data_date'])} 기준). 실제와 다를 수 있어요. 번호가 없는 곳의 '바로 전화'는 누를 때 지도 서비스에서 번호를 찾아 연결하며, 그 번호는 저장하지 않아요. <a href="{E(url_path('정보-수정-삭제-요청'))}">정보 수정·삭제 요청</a></p>'''
    crumbs = [('홈', '/'), ('자동차 정비', url_path('자동차정비')), (short_region(region).split()[0], url_path('자동차정비')), (gu, path)]
    crumbs = [crumbs[0], crumbs[1], (gu, path)]
    head = '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin>'
    return path, page(title, desc, path, body, crumbs, ld, extra_head=head)

# ---------------------------------------------------------------- guide pages

GUIDES = json.load(open(os.path.join(ROOT, 'data', 'guides.json'), encoding='utf-8'))

def guide_page(kind, region, ctx=None):
    G = GUIDES[kind]
    gu = gu_name(region)
    ctx = ctx or {}
    dongs = ctx.get('dongs') or []
    local = ''
    if dongs:
        local = (f'<section class="card"><h2>{E(gu)} 어디서든 부를 수 있게</h2><p>{E(gu)}에는 {E("·".join(dongs[:12]))} 같은 동네가 있어요. '
                 f'업체에 전화하거나 요청할 때 <b>동 이름과 아파트·건물 이름</b>을 함께 말하면 이동 시간과 출장비를 더 정확히 들을 수 있어요.</p></section>')
    near = ctx.get('near') or []
    near_html = ''
    if near:
        near_html = f'<section class="card"><h2>가까운 지역 {E(G["name"])}</h2><div class="links">' + ''.join(
            f'<a href="{E(url_path("안내", kind, r.replace(" ", "-")))}">{E(short_region(r))}</a>' for r in near) + '</div></section>'
    car = ''
    if ctx.get('shops'):
        car = f'<p class="muted">차 문제라면 <a href="{E(url_path("자동차정비", slug_region(region)))}">{E(gu)} 자동차 정비소 {ctx["shops"]}곳</a>도 볼 수 있어요.</p>'
    fill = lambda t: t.replace('{gu}', gu).replace('{region}', region)
    path = url_path('안내', kind, region.replace(' ', '-'))
    title = fill(G['title']).replace('{sr}', short_region(region)) + ' | 내시간에'
    desc = fill(G['desc'])
    warn = f'<div class="warn">{G["warn"]}</div>' if G.get('warn') else ''
    steps = ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in G['steps'])
    when = ''.join(f'<li>{E(w)}</li>' for w in G['call_when'])
    extra = ''.join(f'<section class="card"><h2>{E(fill(h))}</h2><p>{fill(b)}</p></section>' for h, b in G.get('sections', []))
    ask = ''.join(f'<li>{E(a)}</li>' for a in G.get('ask', []))
    faqs = [(fill(q), fill(a)) for q, a in G['faqs']]
    others = ''.join(f'<a href="{E(url_path("안내", k, region.replace(" ", "-")))}">{E(gu)} {E(GUIDES[k]["name"])}</a>' for k in GUIDES if k != kind)
    body = f'''<section class="hero"><h1>{E(gu)} {E(G['name'])},<br>{E(G['h1_tail'])}</h1>
<p class="lead">{E(fill(G['lead']))}</p></section>
{warn}
<section class="card"><h2>{E(G['steps_title'])}</h2><ol class="steps">{steps}</ol></section>
<section class="card"><h2>이럴 땐 업체를 부르세요</h2><ul class="plain">{when}</ul></section>
{extra}
{f'<section class="card"><h2>업체에 전화할 때 꼭 물어볼 것</h2><ul class="plain">{ask}</ul></section>' if ask else ''}
<section class="card soon"><h2>원하는 시간에 맞춰 부르는 기능, 준비 중이에요</h2><p>시간과 예산을 정해 요청하면 {E(gu)} 업체 사장님들이 가능한 시간과 예상 가격으로 답해 주는 기능을 만들고 있어요. <a href="{E(url_path('요청'))}?t={quote(G['name'])}&amp;r={quote(region)}">어떻게 요청하는지 미리 보기</a></p></section>
{local}
{faq_html(faqs)}
<section class="card"><h2>{E(gu)}의 다른 급한 일</h2><div class="links">{others}</div>{car}</section>
{near_html}
{owner_cta(gu + ' ' + G['name'])}
<p class="source">이 안내는 일반적인 정보예요. 집 상태에 따라 방법과 비용이 달라질 수 있어요. 위험하다고 느껴지면 혼자 하지 말고 전문가를 부르세요.</p>'''
    crumbs = [('홈', '/'), (G['name'], url_path('안내', kind)), (f'{gu} {G["name"]}', path)]
    return path, page(title, desc, path, body, crumbs, [faq_ld(faqs)])

# ---------------------------------------------------------------- simple pages

def mail_link(subject):
    em = CFG.get('contact_email') or 'contact@example.com'
    return f'mailto:{em}?subject={quote(subject)}'

def static_pages():
    em = E(CFG.get('contact_email') or '[이메일 주소 설정 필요]')
    pages = {}
    p = url_path('사장님')
    pages[p] = page('사장님 무료 등록 신청 | 내시간에', '내시간에에 업체를 무료로 등록하고 손님 예약 요청을 문자로 받아 보세요.', p, f'''<section class="hero"><h1>사장님, 손님이 원하는 시간에<br>맞춰 답해 보세요</h1>
<p class="lead">손님이 먼저 시간을 정해 요청하면, 사장님은 문자 버튼 세 개로 "가능 / 다른 시간 / 어려움"만 누르면 돼요.</p></section>
<section class="card"><h2>등록하면 이렇게 바뀌어요</h2><ul class="plain"><li>전화번호·영업시간·가격대를 직접 고칠 수 있어요.</li><li>업체 목록에 '예약 답변 업체'로 표시되고, 손님 예약 요청을 문자로 받아요.</li><li>사업자등록 확인을 거친 업체만 등록돼요.</li></ul></section>
<section class="card"><h2>지금은 등록 신청을 받고 있어요</h2><p>아래 버튼으로 업체 이름, 사업자등록번호, 연락받을 휴대폰 번호를 보내 주시면 확인 후 연락드려요. 신청은 무료예요.</p>
<div id="join-mail"><a class="btn dark" href="{E(mail_link('내시간에 사장님 등록 신청'))}">이메일로 등록 신청하기</a><p class="muted">받는 곳: {em}</p></div>
<form id="join" class="form" hidden>
<label class="fld"><span>업체 이름</span><input name="biz_name" required maxlength="60"></label>
<label class="fld"><span>사업자등록번호 (10자리)</span><input name="biz_no" required inputmode="numeric" placeholder="000-00-00000"></label>
<label class="fld"><span>대표자 이름</span><input name="owner_name" maxlength="30"></label>
<label class="fld"><span>요청 알림 받을 휴대폰</span><input name="mobile" required type="tel" inputmode="tel" placeholder="010-0000-0000"></label>
<label class="fld"><span>손님에게 보일 업체 전화 (선택)</span><input name="public_phone" type="tel" placeholder="032-000-0000"></label>
<label class="fld"><span>업종</span><select name="trade" required>{''.join(f'<option>{E(t)}</option>' for t in ['자동차 정비','하수구 막힘','보일러 고장','수도 동파','누수','열쇠·도어락','정전·전기 고장','유리·창문 파손','정화조 청소','방역·해충'])}</select></label>
<label class="fld"><span>지역</span><select name="region" required>{''.join(f'<option>{E(r)}</option>' for r in sorted(RELEASED))}</select></label>
<label class="fld"><span>업체 주소</span><input name="address" maxlength="120"></label>
<label class="fld"><span>대표 가격대 (선택)</span><input name="price_note" maxlength="100" placeholder="예: 엔진오일 5만~7만 원(공임 포함)"></label>
<label class="agree"><input type="checkbox" name="sms_consent" required><span>손님 예약 요청 알림 문자를 받는 데 동의해요. 언제든 그만 받을 수 있어요.</span></label>
<p id="join-msg" class="err" aria-live="polite"></p>
<button type="submit" class="btn blue wide">무료 등록 신청하기</button></form></section>''', scripts='<script src="/flow.js" defer></script>')
    p = url_path('정보-수정-삭제-요청')
    pages[p] = page('업체 정보 수정·삭제 요청 | 내시간에', '내시간에에 실린 업체 정보의 수정이나 삭제를 요청하는 방법이에요.', p, f'''<section class="hero"><h1>업체 정보 수정·삭제 요청</h1>
<p class="lead">내시간에의 업체 정보는 공공데이터(국토교통부 표준데이터 등)를 바탕으로 해요. 정보가 틀렸거나, 사장님이 정보 게시를 원하지 않으시면 알려 주세요.</p></section>
<section class="card"><h2>요청 방법</h2><ol class="steps"><li><b>업체 이름과 주소</b><span>어느 업체인지 알 수 있게 적어 주세요.</span></li><li><b>원하시는 것</b><span>수정(무엇을 어떻게) 또는 삭제를 적어 주세요.</span></li><li><b>보내기</b><span>요청을 받으면 확인 후 바로 처리하고 결과를 알려 드려요.</span></li></ol>
<a class="btn dark" href="{E(mail_link('내시간에 업체 정보 수정·삭제 요청'))}">이메일로 요청하기</a><p class="muted">받는 곳: {em}</p></section>
<section class="card"><h2>정보를 어디서 가져왔나요?</h2><p>공개된 공공데이터에서 업체 이름, 주소, 업종, 전화번호, 영업시간을 가져와요. 전화번호가 없는 업체는 손님이 '바로 전화'를 누를 때만 지도 서비스에서 찾아 화면에 보여 주며, 그 번호를 저장하지 않아요. 개인정보 보호법 제20조에 따라 요청하시면 수집 출처와 이용 목적을 알려 드리고, 처리 정지를 요청하실 수 있어요.</p></section>''')
    p = url_path('개인정보처리방침')
    pages[p] = page('개인정보처리방침 | 내시간에', '내시간에 개인정보처리방침', p, f'''<section class="hero"><h1>개인정보처리방침</h1><p class="lead">시행일: {TODAY.isoformat()}</p></section>
<section class="card"><h2>1. 손님 정보</h2><p>지금 내시간에는 손님에게 회원가입이나 개인정보 입력을 받지 않아요. 예약 요청 기능이 열리면 요청 전달과 답변 문자 발송에 필요한 휴대폰 번호만 동의를 받아 받고, 30일 뒤 지워요.</p></section>
<section class="card"><h2>2. 업체 정보</h2><p>업체 이름, 주소, 업종, 전화번호, 영업시간은 공공데이터에서 가져온 공개 정보예요. 출처: 국토교통부 전국자동차정비업체표준데이터. 수집 출처·이용 목적 안내와 처리 정지 요청은 <a href="{E(url_path('정보-수정-삭제-요청'))}">정보 수정·삭제 요청</a>으로 할 수 있어요.</p></section>
<section class="card"><h2>3. 외부 서비스</h2><p>위치 지도는 오픈스트리트맵, 전화번호 찾기는 카카오 지도 서비스를 쓸 수 있어요. 이때 손님 브라우저가 해당 서비스에 직접 접속해요. 방문 통계를 위해 쿠키를 쓰는 분석 도구를 붙이면 이곳에 알려 드려요.</p></section>
<section class="card"><h2>4. 문의</h2><p>개인정보 관련 문의: {em}</p></section>''')
    p = url_path('요청')
    pages[p] = page('원하는 시간에 예약 요청 (미리 보기) | 내시간에', '원하는 날짜·시간·예산을 정해 동네 업체에 한 번에 요청하는 화면 미리 보기예요.', p,
        '<div id="req" aria-live="polite"><noscript>이 화면은 자바스크립트가 필요해요.</noscript></div>', noindex=True, scripts='<script src="/req.js" defer></script>')
    p = url_path('내-요청')
    pages[p] = page('내 요청 | 내시간에', '내 예약 요청과 업체 답변', p, '<div id="my" aria-live="polite"></div>', noindex=True, scripts='<script src="/flow.js" defer></script>')
    p = url_path('답변')
    pages[p] = page('손님 요청에 답하기 | 내시간에', '사장님 답변 화면', p, '<div id="reply" aria-live="polite"></div>', noindex=True, scripts='<script src="/flow.js" defer></script>')
    p = url_path('소개')
    pages[p] = page('내시간에 소개 | 원하는 시간에 맞춰 답하는 동네 업체', '손님이 원하는 시간을 먼저 정하면 동네 업체가 맞춰 답하는 서비스, 내시간에를 소개해요.', p, f'''<section class="hero"><h1>돈 내는 손님이<br>시간을 먼저 정해요</h1><p class="lead">내시간에는 동네 업체를 찾고, 원하는 시간에 맞춰 예약할 수 있게 돕는 서비스예요.</p></section>
<section class="card"><h2>지금 할 수 있는 것</h2><ul class="plain"><li>지역별 자동차 정비소 목록, 전화번호, 위치, 정비 종류 보기</li><li>번호를 눌러 바로 전화하기</li><li>막힘·누수처럼 급한 일에 먼저 해 볼 것 안내</li></ul></section>
<section class="card"><h2>곧 열리는 것</h2><ul class="plain"><li>원하는 시간과 예산을 정해 여러 업체에 한 번에 요청하기</li><li>사장님이 가능한 시간과 가격대로 답하고, 손님이 비교해서 고르기</li><li>예약 확인된 손님만 쓰는 업체 후기</li></ul></section>''')
    return pages

# ---------------------------------------------------------------- index pages

def guide_index(kind, regions):
    G = GUIDES[kind]
    path = url_path('안내', kind)
    by_sido = defaultdict(list)
    for r in sorted(regions):
        by_sido[r.split()[0]].append(r)
    secs = ''.join(f'<section class="card" id="{E(sd)}"><h2>{E(sd)}</h2><div class="links">' + ''.join(
        f'<a href="{E(url_path("안내", kind, r.replace(" ", "-")))}">{E(gu_name(r))}</a>' for r in rs) + '</div></section>' for sd, rs in by_sido.items())
    body = f'''<section class="hero"><h1>{E(G['name'])}, {E(G['h1_tail'])}</h1><p class="lead">사는 지역을 고르면 {E(G['name'])} 때 할 일과 업체에 물어볼 것을 지역에 맞춰 볼 수 있어요.</p></section>{secs}'''
    return path, page(f'{G["name"]} 지역별 안내 | 내시간에', f'{G["name"]} 때 바로 할 일과 업체 부르는 법을 시·군·구별로 안내해요.', path, body, [('홈', '/'), (G['name'], path)])

def trade_index(regions_count):
    path = url_path('자동차정비')
    by_sido = defaultdict(list)
    for r, c in sorted(regions_count.items()):
        by_sido[r.split()[0]].append((r, c))
    secs = ''.join(f'<section class="card" id="{E(sido)}"><h2>{E(sido)}</h2><div class="links">' + ''.join(
        f'<a href="{E(url_path("자동차정비", slug_region(r)))}">{E(gu_name(r))} <span class="muted">{c}곳</span></a>' for r, c in rs) + '</div></section>'
        for sido, rs in by_sido.items())
    body = f'''<section class="hero"><h1>지역별 자동차 정비소</h1><p class="lead">동네를 고르면 정비소 전화번호·위치·정비 종류를 볼 수 있어요.</p></section>{secs}'''
    return path, page('지역별 자동차 정비소 찾기 | 내시간에', '시·군·구별 자동차 정비소 전화번호와 위치, 정비 종류를 찾아보세요.', path, body, [('홈', '/'), ('자동차 정비', path)])

def home(regions_count, region_centers, guides):
    # 검색용 색인: 공개된 모든 페이지 (업종 + 동네)
    idx = []
    for r, c in regions_count.items():
        idx.append({'t': '자동차 정비', 'n': f'{short_region(r)} 자동차 정비소', 's': f'{c}곳 · 전화번호·위치', 'u': url_path('자동차정비', slug_region(r)),
                    'k': f'자동차 정비 정비소 카센터 엔진오일 타이어 배터리 {r}', 'lat': region_centers[r][0], 'lng': region_centers[r][1]})
    for kind, g in guides:
        G = GUIDES[kind]; reg = g.strip('/').split('/')[-1].replace('-', ' ')
        ctr = region_centers.get(reg, (0, 0))
        idx.append({'t': G['tile'], 'n': f'{short_region(reg)} {G["name"]}', 's': G['h1_tail'], 'u': g,
                    'k': f'{G["name"]} {G["tile"]} {reg}', 'lat': ctr[0], 'lng': ctr[1]})
    live = {'자동차 정비': url_path('자동차정비')}
    for kind, g in guides:
        live.setdefault(GUIDES[kind]['tile'], url_path('안내', kind) if CFG.get('guides_all') else g)
    order = ['보일러 고장', '수도 동파', '하수구 막힘', '누수 탐지', '열쇠·도어락', '정전·전기 고장', '유리·창문 파손', '정화조 청소', '방역·해충', '자동차 정비']
    hot = [t for t in order if t in live]
    icons = {'보일러 고장': '♨', '수도 동파': '❄', '하수구 막힘': '⤓', '누수 탐지': '💧', '열쇠·도어락': '🔑', '정전·전기 고장': '⚡', '유리·창문 파손': '🪟', '정화조 청소': '🚽', '방역·해충': '🐜', '자동차 정비': '🚗'}
    hot_html = ''.join(f'<a class="hot" href="{E(live[t])}"><span class="ic" aria-hidden="true">{icons.get(t, "•")}</span><b>{E(t)}</b></a>' for t in hot)
    chips = ''.join(f'<button type="button" class="qchip" data-q="{E(t.split("·")[0].split()[0])}">{E(t)}</button>' for t in hot)
    groups = [
        ('집 수리·고장', ['정전·전기 고장', '유리·창문 파손', '에어컨 고장·청소', '수전·싱크대 교체', '옥상·외벽 방수', '정화조 청소']),
        ('청소·정리·방역', ['입주·이사청소', '줄눈·탄성코트', '유품정리·특수청소', '방역·해충', '비둘기·벌집']),
        ('상가·업소', ['사다리차', '셔터·자동문 수리', '업소용 냉장고', '간판 수리', '팝업 인테리어']),
    ]
    soon = ''.join(f'<p class="soon-row"><b>{E(n)}</b> {" · ".join(E(i) for i in items if i not in live)}</p>' for n, items in groups)
    if len(regions_count) <= 12:
        open_regions = ''.join(f'<a href="{E(url_path("자동차정비", slug_region(r)))}">{E(short_region(r))}</a>' for r in regions_count)
    else:
        sc = Counter(r.split()[0] for r in regions_count)
        open_regions = ''.join(f'<a href="{E(url_path("자동차정비"))}#{E(sd)}">{E(SIDO_SHORT.get(sd, sd))} <span class="muted">{n}개 지역</span></a>' for sd, n in sorted(sc.items(), key=lambda x: -x[1]))
    body = f'''<section class="hero home"><h1>내 시간에<br><span class="hl">예약방문, 전화</span>하세요</h1><p class="lead">보일러·하수구·누수 같은 출장 수리부터 자동차 정비까지, 동네 업체를 모았어요. 원하는 시간에 맞춰 예약하고 방문하거나, 지금 바로 전화하세요.</p></section>
<section class="card find"><h2>무엇이 필요하세요?</h2>
<label class="search"><span class="sr">업종이나 동네 검색</span><input id="q" type="search" placeholder="예: 보일러, 하수구, 연수구 정비" autocomplete="off"></label>
<button type="button" id="near" class="btn ghost wide">내 위치에서 가까운 곳</button>
<div id="results" class="results" aria-live="polite"></div></section>
<section class="card"><h2>지금 바로 찾을 수 있어요</h2><div class="hots">{hot_html}</div></section>
<section class="card req-cta"><h2>원하는 시간을 먼저 정하세요</h2><p>날짜·시간·예산을 정해 요청하면, 동네 업체 사장님이 가능한 시간과 가격으로 답해요.</p><a class="btn blue wide" href="{E(url_path('요청'))}">시간 정해 예약 요청하기</a></section>
<section class="card"><h2>열린 동네</h2><div class="links">{open_regions}</div><p class="muted">동네와 업종은 차례로 늘어나요.</p></section>
<section class="card"><h2>곧 열려요</h2>{soon}</section>
{owner_cta('동네 업체')}
<script type="application/json" id="regions" data-src="/search.json">[]</script>'''
    open(os.path.join(OUT, 'search.json'), 'w', encoding='utf-8').write(json.dumps(idx, ensure_ascii=False, separators=(',', ':')))
    ld = [{'@context': 'https://schema.org', '@type': 'WebSite', 'name': '내시간에', 'url': BASE + '/'}]
    return '/', page('내시간에 - 내 시간에 예약방문, 전화하세요 | 동네 정비소·출장 업체', '내 시간에 예약방문, 전화하세요. 보일러·하수구·누수·열쇠 같은 출장 수리와 자동차 정비소를 동네별로 찾고, 원하는 시간에 맞춰 예약하세요.', '/', body, None, ld)

# ---------------------------------------------------------------- write

def write(path, content):
    fp = os.path.join(OUT, path.strip('/'), 'index.html') if path != '/' else os.path.join(OUT, 'index.html')
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    open(fp, 'w', encoding='utf-8').write(content)

def release_list(by_region, centers):
    """공개할 지역 목록.
    순서는 data/release_order.json 에 한 번 정해 두고 계속 써요 (데이터가 바뀌어도 이미 연 지역이 닫히지 않게).
    config.json release_plan: start 날짜부터 첫날 first 곳, 그 뒤 하루 per_day 곳씩 열어요. release_all 이 true 면 전부 열어요."""
    ok = {r for r, ss in by_region.items() if len(ss) >= 3 and r in centers}
    order_path = os.path.join(ROOT, 'data', 'release_order.json')
    order = json.load(open(order_path, encoding='utf-8')) if os.path.exists(order_path) else []
    pinned = [r for r in CFG['released_regions'] if r in ok]
    def score(r):
        ss = by_region[r]
        return (-round(sum(1 for s in ss if s['phone']) / len(ss), 1), -len(ss), r)
    new = sorted((r for r in ok if r not in order and r not in pinned), key=score)
    if new or any(r not in order for r in pinned):
        order = pinned + [r for r in order if r not in pinned] + new
        json.dump(order, open(order_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    order = [r for r in order if r in ok]
    plan = CFG.get('release_plan') or {}
    if CFG.get('release_all') or not plan:
        n = len(order) if CFG.get('release_all') else len(pinned)
    else:
        days = (TODAY - datetime.date.fromisoformat(plan['start'])).days
        n = 0 if days < 0 else plan.get('first', 50) + plan.get('per_day', 30) * days
    return order[:max(n, len(pinned))]

def main():
    shops = load_shops()
    by_region = defaultdict(list)
    for s in shops:
        by_region[s['region']].append(s)
    centers = {}
    for r, ss in by_region.items():
        pts = [(s['lat'], s['lng']) for s in ss if s['lat']]
        if pts:
            centers[r] = (round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4))
    released = release_list(by_region, centers)
    RELEASED[:] = released
    missing = [r for r in CFG['released_regions'] if r not in released]
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, 'static'), OUT)
    urls = []
    for r in released:
        p, h = region_page(r, by_region[r], set(released), centers)
        write(p, h); urls.append(p)
    guides = []
    gregs = released if CFG.get('guides_all') else [g.split('/')[1].replace('-', ' ', 1) for g in CFG.get('released_guides', [])]
    gkinds = list(GUIDES) if CFG.get('guides_all') else list(dict.fromkeys(g.split('/')[0] for g in CFG.get('released_guides', [])))
    for reg in gregs:
        ss = by_region.get(reg, [])
        dc = Counter(s['dong'] for s in ss if s['dong'])
        me = centers.get(reg)
        near = [r for _, r in sorted((km(me, centers[r]), r) for r in gregs if r != reg and r in centers)[:6]] if me else []
        ctx = {'dongs': [d for d, _ in dc.most_common()], 'near': near, 'shops': len(ss) if reg in released else 0}
        for kind in gkinds:
            if kind in GUIDES:
                p, h = guide_page(kind, reg, ctx)
                write(p, h); urls.append(p); guides.append((kind, p))
    for kind in gkinds:
        if CFG.get('guides_all') and kind in GUIDES:
            p, h = guide_index(kind, gregs); write(p, h); urls.append(p)
    rc = {r: len(by_region[r]) for r in released}
    p, h = trade_index(rc); write(p, h); urls.append(p)
    p, h = home(rc, centers, guides); write(p, h); urls.insert(0, p)
    for p, h in static_pages().items():
        write(p, h)
        if 'noindex' not in h: urls.append(p)
    write('/404', page('페이지를 찾을 수 없어요 | 내시간에', '페이지를 찾을 수 없어요.', '/404/', '<section class="hero"><h1>페이지를 찾을 수 없어요</h1><p class="lead"><a href="/">첫 화면으로 가기</a></p></section>', noindex=True))
    shutil.move(os.path.join(OUT, '404', 'index.html'), os.path.join(OUT, '404.html')); os.rmdir(os.path.join(OUT, '404'))
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(
        f'<url><loc>{E(abs_url(u))}</loc><lastmod>{TODAY.isoformat()}</lastmod></url>\n' for u in urls) + '</urlset>\n'
    open(os.path.join(OUT, 'sitemap.xml'), 'w', encoding='utf-8').write(sm)
    open(os.path.join(OUT, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n')
    host = re.sub(r'^https?://', '', BASE)
    if not host.endswith('github.io'):
        open(os.path.join(OUT, 'CNAME'), 'w').write(host + '\n')
    open(os.path.join(OUT, '.nojekyll'), 'w').write('')
    print(f'업체 {len(shops)}곳 / 지역 {len(by_region)}곳 / 공개 지역 {len(released)}곳 / 페이지 {len(urls)}쪽')
    if missing:
        print('공개 목록에 있지만 데이터가 없어 건너뛴 지역:', ', '.join(missing))
    if not CFG.get('contact_email'):
        print('주의: config.json 의 contact_email 이 비어 있어요. 공개 전에 꼭 넣어 주세요.')

if __name__ == '__main__':
    main()
