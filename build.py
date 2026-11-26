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
FOOD_PAGES = []
import hashlib
def V(name):  # 정적 파일 캐시 갱신용 버전
    return hashlib.md5(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', name), 'rb').read()).hexdigest()[:8]
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
{(f'<script async src="https://www.googletagmanager.com/gtag/js?id={CFG["ga_id"]}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag("js",new Date());gtag("config","{CFG["ga_id"]}");</script>') if CFG.get('ga_id') else ''}
<link rel="manifest" href="/manifest.webmanifest">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="/s.css?v={V('s.css')}">
{extra_head}{ld}</head>
<body>
<header class="top"><a class="brand" href="/"><img class="logo" src="/favicon.svg" alt="" width="28" height="28"><b>내시간에</b></a><a class="top-owner" href="{E(url_path('사장님'))}">사장님이세요?</a></header>
<main>
{crumb_html}
{body}
</main>
<footer class="foot">
<p><b>내시간에</b> · 원하는 시간을 먼저 정하면, 동네 업체가 맞춰 답해 드려요.</p>
<p><a href="{E(url_path('소개'))}">소개</a> · <a href="{E(url_path('정보'))}">생활 정보</a> · <a href="{E(url_path('정보-수정-삭제-요청'))}">정보 수정·삭제 요청</a> · <a href="{E(url_path('개인정보처리방침'))}">개인정보처리방침</a></p>
<p class="muted">업체 정보는 공공데이터를 바탕으로 하며 실제와 다를 수 있어요.</p>
</footer>
<script>window.NSG={{kakao:{json.dumps(CFG.get('kakao_js_key') or '')},api:{json.dumps(CFG.get('supabase_url') or '')},key:{json.dumps(CFG.get('supabase_anon_key') or '')},regions:{json.dumps(sorted(RELEASED) if path.startswith(url_path('요청')) else [], ensure_ascii=False)},sms:{'true' if CFG.get('sms_enabled') else 'false'},reqLive:{'true' if CFG.get('requests_live') else 'false'}}};
window.NSG.call=function(fn,args){{return fetch(NSG.api+'/rest/v1/rpc/'+fn,{{method:'POST',headers:Object.assign({{'apikey':NSG.key,'Content-Type':'application/json'}},/^eyJ/.test(NSG.key)?{{'Authorization':'Bearer '+NSG.key}}:{{}}),body:JSON.stringify(args)}}).then(function(r){{return r.json().then(function(j){{if(!r.ok)throw new Error((j&&j.message)||'잠시 뒤 다시 해 주세요');return j}})}})}};</script>
<script src="/app.js?v={V('app.js')}" defer></script>
<script src="/tools.js?v={V('tools.js')}" defer></script>
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

def qv(t):
    """한글은 그대로 두고 URL에 문제 되는 글자만 바꿔요 (페이지 용량 줄이기)."""
    return re.sub(r'[%&#?+/"<>\s]', lambda m: '+' if m.group(0) == ' ' else '%%%02X' % ord(m.group(0)), str(t))

def naver_nav(q):
    return 'https://map.naver.com/p/search/' + qv(q).replace('+', '%20')

def book_btn(trade, region, name=''):
    href = url_path('요청') + '?t=' + qv(trade) + '&r=' + qv(region) + ('&s=' + qv(name) if name else '')
    return f'<a class="btn book" href="{E(href)}">예약 요청<span class="dev">개발 중</span></a>'

NO_BOOK = {'약국', '동물병원'}

LIVE = bool(CFG.get('requests_live'))  # 예약 요청 기능이 열리기 전에는 예약 버튼을 숨겨요

def act_row(trade, region, name, call_html, nav):
    if trade in NO_BOOK or not LIVE:
        return (f'<div class="actions act2">{call_html}'
                f'<a class="btn ghost sm" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>')
    return (f'<div class="actions act3">{book_btn(trade, region, name)}{call_html}'
            f'<a class="btn ghost sm" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>')

def lookup_btn(name, q, lat, lng, car=False):
    return (f'<button type="button" class="btn ghost sm call lookup" data-name="{E(name)}" data-q="{E(q)}" '
            f'data-lat="{lat or ""}" data-lng="{lng or ""}"{" data-car=\"1\"" if car else ""}><span aria-hidden="true">☎</span> 전화</button>')

FOOD = json.load(open(os.path.join(ROOT, 'data', 'food_meta.json'), encoding='utf-8')) if os.path.exists(os.path.join(ROOT, 'data', 'food_meta.json')) else {}

def food_card(rec, i, g, region):
    name, short, dong, lat, lng, sub = rec
    gu = gu_name(region)
    q = name + ' ' + gu.split()[-1]
    nav = naver_nav(name + " " + gu + " " + short)
    base = url_path('요청') + '?r=' + qv(region) + '&s=' + qv(name)
    chips = ''.join(f'<span class="chip">{E(c)}</span>' for c in (sub, dong) if c)
    return (f'<article class="shop" id="s{i}"><div class="shop-head"><span class="pin" aria-hidden="true">{i + 1}</span><h3>{E(name)}</h3></div>'
            f'<p class="addr">{E(short)}</p><div class="chips">{chips}</div>'
            + (f'<div class="actions two-btn"><a class="btn book" href="{E(base + "&t=" + qv("단체 예약"))}">단체 예약 요청</a>'
            f'<a class="btn book" href="{E(base + "&t=" + qv("포장 예약"))}">포장 예약</a></div>' if LIVE else '') +
            f'<div class="actions two-btn">{lookup_btn(name, q, lat, lng)}<a class="btn ghost sm" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>'
            f'<p class="lookup-note" hidden></p></article>')

def food_page(g, region, entry, ctx):
    M = FOOD[g]; gu = gu_name(region); sr = short_region(region)
    path = url_path('음식점', g, region.replace(' ', '-'))
    lst = entry['list'][:60]; n = entry['n']
    cards = ''.join(food_card(r, i, g, region) for i, r in enumerate(lst))
    dongs = [d for d, _ in Counter(r[2] for r in entry['list'] if r[2]).most_common(10)]
    others = ''.join(f'<a href="{E(url_path("음식점", k, region.replace(" ", "-")))}">{E(gu)} {E(FOOD[k]["name"])}</a>' for k in FOOD if k != g and k in ctx.get('groups_here', ()))
    near = ''.join(f'<a href="{E(url_path("음식점", g, r.replace(" ", "-")))}">{E(short_region(r))}</a>' for r in ctx.get('near', []))
    sd = ctx.get('date', '')
    body = f'''<section class="hero"><h1>{E(gu)} {E(M['name'])},<br>단체 예약·포장 전화</h1>
<p class="lead">{E(region)}의 {E(M['what'])} {n}곳이에요. 모임 인원이나 포장할 시간을 정해서 바로 전화하세요.</p></section>
<section class="card"><h2>{E(gu)} {E(M['name'])} {n}곳</h2>
<div id="members" data-region="{E(region)}" data-trade="{E(M['name'])}" hidden></div>
<p class="muted">'전화'를 누르면 번호를 찾아 바로 걸려요.</p>
<div class="shops" data-page="20">{cards}</div><button type="button" class="btn ghost wide more" hidden>더 보기</button>
{f'<p class="muted">그 외 {n - len(lst)}곳은 네이버 지도에서 찾아보세요.</p>' if n > len(lst) else ''}
<p class="source">가게 이름·주소: 소상공인시장진흥공단 상가(상권)정보{(" (" + sd[:4] + "." + sd[4:6] + ")") if sd else ""}. 영업 상황이 바뀌었을 수 있어요.</p></section>
{view_section(gu, [(r[3], r[4], i + 1) for i, r in enumerate(lst) if len(r) > 4], None, '가게')}
<section class="card"><h2>단체 예약 전화할 때</h2><p>{E(M['group'])} 날짜·시간·인원·예산을 한 번에 말하면 통화가 짧아져요.</p></section>
<section class="card"><h2>포장 예약할 때</h2><p>{E(M['pack'])}</p></section>
{f'<section class="card"><h2>{E(gu)} 어느 동네에 많아요?</h2><p>{E(" · ".join(dongs))} 순으로 많아요.</p></section>' if dongs else ''}
{f'<section class="card"><h2>{E(gu)} 다른 음식점</h2><div class="links">{others}</div></section>' if others else ''}
{f'<section class="card"><h2>가까운 지역 {E(M["name"])}</h2><div class="links">{near}</div></section>' if near else ''}
{owner_cta(gu + ' ' + M['name'])}'''
    title = f'{sr} {M["name"]} {n}곳 - 단체 예약·포장 전화번호 | 내시간에'
    desc = f'{region} {M["what"]} {n}곳. 단체 예약·포장 주문 전에 바로 전화하고 길찾기까지 한 번에.'
    return path, page(title, desc, path, body, [('홈', '/'), ('음식점', url_path('음식점')), (M['name'], url_path('음식점', g)), (f'{gu} {M["name"]}', path)])

def food_index(g, regions):
    M = FOOD[g]; path = url_path('음식점', g)
    by = defaultdict(list)
    for r in sorted(regions): by[r.split()[0]].append(r)
    secs = ''.join(f'<section class="card" id="{E(sd)}"><h2>{E(sd)}</h2><div class="links">' + ''.join(
        f'<a href="{E(url_path("음식점", g, r.replace(" ", "-")))}">{E(gu_name(r))}</a>' for r in rs) + '</div></section>' for sd, rs in by.items())
    body = f'<section class="hero"><h1>{E(M["name"])} 단체 예약·포장</h1><p class="lead">지역을 고르면 {E(M["what"])} 목록과 바로 전화 버튼이 나와요.</p></section>{secs}'
    return path, page(f'{M["name"]} 지역별 단체 예약·포장 | 내시간에', f'시·군·구별 {M["what"]} 목록과 전화·길찾기.', path, body, [('홈', '/'), ('음식점', url_path('음식점')), (M['name'], path)])

def food_home():
    path = url_path('음식점')
    tiles = ''.join(f'<a class="hot" href="{E(url_path("음식점", g))}"><span class="ic" aria-hidden="true">{M["icon"]}</span><b>{E(M["name"])}</b></a>' for g, M in FOOD.items())
    body = f'<section class="hero"><h1>음식점 단체 예약·포장</h1><p class="lead">회식·모임 자리 잡기, 포장 주문 전에 동네 가게에 바로 전화하세요.</p></section><section class="card"><div class="hots">{tiles}</div></section>'
    return path, page('음식점 단체 예약·포장 전화 | 내시간에', '동네 고기집·한식당·횟집·중식당 단체 예약과 포장 주문 전화번호를 지역별로 찾아보세요.', path, body, [('홈', '/'), ('음식점', path)])

DIRM = json.load(open(os.path.join(ROOT, 'data', 'dir_meta.json'), encoding='utf-8')) if os.path.exists(os.path.join(ROOT, 'data', 'dir_meta.json')) else {}
DIR_PAGES = []

def dir_card(rec, i, sec, gm, region):
    name, short, dong, lat, lng, sub = rec
    gu = gu_name(region)
    nav = naver_nav(name + " " + gu + " " + short)
    chips = ''.join(f'<span class="chip">{E(c)}</span>' for c in (sub, dong) if c)
    call = lookup_btn(name, name + ' ' + gu.split()[-1], lat, lng)
    if DIRM[sec]['kind'] == 'pro' and LIVE:
        acts = (f'<div class="actions one">{book_btn("상담 예약", region, name).replace(">예약 요청<", ">상담 예약 요청<")}</div>'
                f'<div class="actions two-btn">{call}<a class="btn ghost sm" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>')
    else:
        acts = f'<div class="actions two-btn">{call}<a class="btn ghost sm" href="{E(nav)}" target="_blank" rel="noopener">길찾기</a></div>'
    return (f'<article class="shop" id="s{i}"><div class="shop-head"><span class="pin" aria-hidden="true">{i + 1}</span><h3>{E(name)}</h3></div>'
            f'<p class="addr">{E(short)}</p><div class="chips">{chips}</div>{acts}<p class="lookup-note" hidden></p></article>')

def dir_page(sec, g, region, entry, ctx):
    S = DIRM[sec]; gm = S['groups'][g]; gu = gu_name(region); sr = short_region(region)
    path = url_path(sec, g, region.replace(' ', '-'))
    lst = entry['list'][:40]; n = entry['n']
    cards = ''.join(dir_card(r, i, sec, gm, region) for i, r in enumerate(lst))
    dongs = [d for d, _ in Counter(r[2] for r in entry['list'] if r[2]).most_common(10)]
    others = ''.join(f'<a href="{E(url_path(sec, k, region.replace(" ", "-")))}">{E(gu)} {E(S["groups"][k]["name"])}</a>' for k in S['groups'] if k != g and k in ctx.get('here', ()))
    near = ''.join(f'<a href="{E(url_path(sec, g, r.replace(" ", "-")))}">{E(short_region(r))}</a>' for r in ctx.get('near', []))
    tips = ''.join(f'<section class="card"><h2>{E(h)}</h2><p>{E(t)}</p></section>' for h, t in S['tips'])
    sd = ctx.get('date', '')
    pro = S['kind'] == 'pro'
    body = f'''<section class="hero"><h1>{E(gu)} {E(gm['name'])}<br>{'상담 전화·위치' if pro else '전화번호·위치'}</h1>
<p class="lead">{E(region)}의 {E(gm['name'])} {n}곳이에요. 누르면 바로 전화가 걸려요.</p></section>
<div class="warn">{E(S['intro'])}</div>
<section class="card"><h2>{E(gu)} {E(gm['name'])} {n}곳</h2>
{'<p class="muted">' + chr(39) + '상담 예약 요청' + chr(39) + '은 원하는 시간을 정해 사무소에 요청하는 기능이에요. 이용료는 받지 않아요.</p>' if pro and LIVE else ''}
<div class="shops" data-page="20">{cards}</div><button type="button" class="btn ghost wide more" hidden>더 보기</button>
{f'<p class="muted">그 외 {n - len(lst)}곳은 네이버 지도에서 찾아보세요.</p>' if n > len(lst) else ''}
<p class="source">이름·주소: 소상공인시장진흥공단 상가(상권)정보{(" (" + sd[:4] + "." + sd[4:6] + ")") if sd else ""}. 목록 순서는 동네별 정리일 뿐 추천 순위가 아니에요.</p></section>
{view_section(gu, [(r[3], r[4], i + 1) for i, r in enumerate(lst) if len(r) > 4], None, '병원' if not pro else '사무소')}
{tips}
{f'<section class="card"><h2>{E(gu)} 어느 동네에 많아요?</h2><p>{E(" · ".join(dongs))} 순으로 많아요.</p></section>' if dongs else ''}
{f'<section class="card"><h2>{E(gu)} 다른 {E(S["label"])}</h2><div class="links">{others}</div></section>' if others else ''}
{f'<section class="card"><h2>가까운 지역 {E(gm["name"])}</h2><div class="links">{near}</div></section>' if near else ''}'''
    title = f'{sr} {gm["name"]} {n}곳 - {"상담 " if pro else ""}전화번호·위치 | 내시간에'
    desc = f'{region} {gm["name"]} {n}곳의 위치와 전화 연결. 동네별로 정리했어요.'
    return path, page(title, desc, path, body, [('홈', '/'), (S['label'], url_path(sec)), (gm['name'], url_path(sec, g)), (f'{gu} {gm["name"]}', path)])

def dir_index(sec, g, regions):
    S = DIRM[sec]; gm = S['groups'][g]; path = url_path(sec, g)
    by = defaultdict(list)
    for r in sorted(regions): by[r.split()[0]].append(r)
    secs = ''.join(f'<section class="card" id="{E(sd)}"><h2>{E(sd)}</h2><div class="links">' + ''.join(
        f'<a href="{E(url_path(sec, g, r.replace(" ", "-")))}">{E(gu_name(r))}</a>' for r in rs) + '</div></section>' for sd, rs in by.items())
    body = f'<section class="hero"><h1>지역별 {E(gm["name"])}</h1><p class="lead">지역을 고르면 {E(gm["name"])} 목록과 전화 버튼이 나와요.</p></section>{secs}'
    return path, page(f'지역별 {gm["name"]} 찾기 | 내시간에', f'시·군·구별 {gm["name"]} 위치와 전화.', path, body, [('홈', '/'), (S['label'], url_path(sec)), (gm['name'], path)])

def dir_home(sec):
    S = DIRM[sec]; path = url_path(sec)
    tiles = ''.join(f'<a class="hot" href="{E(url_path(sec, g))}"><span class="ic" aria-hidden="true">{gm["icon"]}</span><b>{E(gm["name"])}</b></a>' for g, gm in S['groups'].items())
    body = f'<section class="hero"><h1>{E(S["label"])}</h1><p class="lead">{E(S["intro"])}</p></section><section class="card"><div class="hots">{tiles}</div></section>'
    return path, page(f'{S["label"]} 지역별 찾기 | 내시간에', f'동네 {S["label"]} 위치와 전화번호를 시·군·구별로 찾아보세요.', path, body, [('홈', '/'), (S['label'], path)])

def store_card(rec, i, trade, region):
    name, short, dong, lat, lng = rec
    gu = gu_name(region)
    q = name + ' ' + gu.split()[-1]
    nav = naver_nav(name + " " + gu + " " + short)
    chips = f'<div class="chips"><span class="chip">{E(dong)}</span></div>' if dong else ''
    return (f'<article class="shop" id="s{i}"><div class="shop-head"><span class="pin" aria-hidden="true">{i + 1}</span><h3>{E(name)}</h3></div>'
            f'<p class="addr">{E(short)}</p>{chips}{act_row(trade, region, name, lookup_btn(name, q, lat, lng), nav)}'
            f'<p class="lookup-note" hidden></p></article>')

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
        call = f'<a class="btn ghost sm call" href="tel:{E(re.sub(r"[^0-9]", "", s["phone"]))}"><span aria-hidden="true">☎</span> 전화</a>'
    else:
        call = lookup_btn(s['name'], q, s['lat'], s['lng'], car=True)
    nav = naver_nav(q)
    return f'''<article class="shop" id="s{i}" data-type="{E(t)}" data-dong="{E(s['dong'])}" data-phone="{1 if s['phone'] else 0}" data-lat="{s['lat'] or ''}" data-lng="{s['lng'] or ''}">
<div class="shop-head"><span class="pin" aria-hidden="true">{i + 1}</span><h3>{name}</h3></div>
<p class="addr">{E(s['addr'].split(' ', 2)[2] if s['addr'].count(' ') >= 2 else s['addr'])}</p>
<div class="chips">{''.join(chips)}</div>
{f'<p class="tel">☎ {E(s["phone"])}</p>' if s['phone'] else ''}{act_row('자동차 정비', s['region'], s['name'], call, nav)}
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
{view_section(gu, pts, region_centers.get(region), '정비소')}
{photo_section('_car', '정비소에서는 이렇게 해요')}
<section class="card"><h2>정비소 가기 전까지 이렇게 하세요</h2>
<p>{E(gu)}에서 차가 갑자기 이상해졌을 때, 정비소에 맡기기 전까지 안전하게 버티는 방법이에요.</p>
<ol class="steps"><li><b>빨간 경고등이면 바로 세우세요</b><span>엔진 온도, 엔진오일, 브레이크 경고등이 빨갛게 켜지면 안전한 곳에 차를 세우고 시동을 꺼요. 노란 경고등은 천천히 정비소까지 가도 되는 경우가 많지만 사진은 찍어 두세요.</span></li>
<li><b>고속도로·큰길에서는 사람부터 피하세요</b><span>비상등을 켜고 갓길에 세운 뒤, 사람은 가드레일 밖으로 나가요. 고속도로는 한국도로공사 긴급견인(1588-2504)을 무료로 부를 수 있어요.</span></li>
<li><b>보험 긴급출동을 먼저 확인하세요</b><span>배터리 방전, 타이어 펑크, 잠금, 견인은 자동차보험 긴급출동으로 무료이거나 싸게 해결되는 경우가 많아요. 보험사 앱이나 증권에 있는 번호로 부르세요.</span></li>
<li><b>증상을 기록해 두세요</b><span>언제부터, 어떤 소리·냄새·떨림이 있는지, 경고등 사진을 정비소에 보여 주면 점검 시간이 줄고 엉뚱한 수리를 막을 수 있어요.</span></li></ol>
<p class="muted">정비소에 갈 때는 견적서를 먼저 받고, 바꾼 부품은 돌려받거나 보여 달라고 하세요. 큰 수리는 두 곳 이상에서 견적을 비교하는 게 좋아요.</p></section>
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

GROUPS = [
    ('급한 출장 수리', ['보일러-고장', '수도-동파', '하수구-막힘', '누수-탐지', '열쇠-도어락', '전기-고장', '유리-파손']),
    ('집 수리', ['에어컨-고장', '가전-수리', '수전-교체', '창호-샷시', '도배-장판', '집수리', '방수', '정화조-청소']),
    ('청소·정리·방역', ['입주청소', '줄눈-탄성코트', '유품정리', '폐기물-철거', '방역-해충', '비둘기-벌집']),
    ('차·반려동물·약국', ['타이어-출동', '동물병원', '약국']),
    ('상가·업소', ['사다리차', '셔터-자동문', '업소용-냉장고', '간판-수리', '팝업-인테리어']),
]
def group_of(kind):
    for n, ks in GROUPS:
        if kind in ks:
            return n, ks
    return '다른 업종', list(GUIDES)


GX = json.load(open(os.path.join(ROOT, 'data', 'guides_extra.json'), encoding='utf-8'))

def wait_section(kind, gu, near=None):
    X = GX.get(kind)
    if not X:
        return ''
    far = ''
    if gu.endswith('군') and near:
        far = (f'<p>{E(gu)}처럼 군 지역은 업체가 읍내에 모여 있어서 마을까지 오는 데 시간이 걸리고 출장비가 붙는 경우가 많아요. '
               f'가까운 {E("·".join(short_region(r) for r in near[:3]))} 업체도 함께 알아보면 더 빨리 올 수 있는 곳을 찾을 수 있어요. '
               f'전화할 때 마을 이름과 큰길 기준 위치를 말해 주세요.</p>')
    li = ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in X['wait'])
    prep = ('<ul class="plain"><li>고장 난 곳이나 현장 사진 2~3장</li><li>동 이름, 아파트·건물 이름, 몇 층인지와 엘리베이터 유무</li>'
            '<li>주차할 곳이 있는지 (없으면 근처 공영주차장 위치)</li><li>언제부터 그랬는지, 직접 해 본 방법이 있는지</li></ul>')
    return (f'<section class="card"><h2>업체가 올 때까지 이렇게 하세요</h2>'
            f'<p>{E(gu)}에서 업체를 불러도 바로 오지 못하는 경우가 많아요. 기다리는 동안 피해를 줄이는 방법이에요.</p>'
            f'<ol class="steps">{li}</ol>'
            f'<h3 class="sub">업체에 미리 알려 주면 좋은 것</h3>{prep}'
            f'<p class="muted">이걸 미리 보내면 업체가 맞는 부품과 장비를 챙겨 와서 한 번에 끝날 가능성이 높아지고, 출장비를 두 번 내는 일을 줄일 수 있어요.</p>{far}</section>')

def age_section(kind, gu, apts, slim=False):
    X = GX.get(kind)
    if not X:
        return ''
    A = X['aging']
    yr = TODAY.year
    ys = [a[2] for a in apts if a[2]]
    if len(ys) >= 3:
        o = sum(1 for y in ys if yr - y >= 30)
        m = sum(1 for y in ys if 15 <= yr - y < 30)
        n = len(ys) - o - m
        top = max((o, 'old'), (m, 'mid'), (n, 'new'))[1]
        avg = round(sum(ys) / len(ys))
        oldest = min((a for a in apts if a[2]), key=lambda a: a[2])
        lead = (f'{E(gu)} 아파트 {len(ys)}곳은 평균 <b>{avg}년</b>에 지어졌어요. 가장 오래된 곳은 {E(oldest[0])}({oldest[2]}년)이에요. '
                f'지은 지 30년 넘은 단지 <b>{o}곳</b>, 15~30년 <b>{m}곳</b>, 15년 안 된 단지 <b>{n}곳</b>이에요.')
        rows = [('old', f'30년 넘은 단지 ({o}곳)'), ('mid', f'15~30년 된 단지 ({m}곳)'), ('new', f'15년 안 된 단지 ({n}곳)')]
        rows.sort(key=lambda r: r[0] != top)
        tail = '내가 사는 단지가 어디에 해당하는지 보고, 업체에 전화할 때 \'몇 년에 지은 아파트\'인지 함께 말해 주세요.'
    else:
        lead = (f'{E(gu)}에는 관리비가 공개된 아파트 정보가 많지 않아요. 단독주택이나 빌라라면 정부24의 건축물대장에서 지은 해(사용승인일)를 확인할 수 있어요. '
                f'지은 햇수에 따라 생기는 문제가 달라요.')
        rows = [('old', '지은 지 30년 넘은 집'), ('mid', '15~30년 된 집'), ('new', '15년 안 된 집')]
        tail = '업체에 전화할 때 몇 년쯤 된 건물인지 함께 말하면 필요한 장비와 비용을 더 정확히 들을 수 있어요.'
    li = ''.join(f'<li><b>{E(t)}</b><span>{E(A[k])}</span></li>' for k, t in rows)
    if slim:
        li = ''; tail = ''
    return (f'<section class="card"><h2>{E(gu)} 건물 나이로 보는 {E(GUIDES[kind]["name"])}</h2><p>{lead}</p>'
            f'{decade_chart(gu, ys)}<ul class="steps age">{li}</ul><p class="muted">{tail}</p></section>')

NATIONAL_DECADES = {}
NATIONAL_OLD = 0

def decade_chart(gu, ys):
    """아파트 지은 연도를 10년 단위로, 우리 지역과 전국 평균을 나란히 세로 막대로 보여 줘요 (비율 %)."""
    if len(ys) < 3:
        return ''
    keys = list(range(1970, 2030, 10))
    def dist(L):
        c = Counter(min(max(y // 10 * 10, 1970), 2020) for y in L)
        return {k: c.get(k, 0) / len(L) * 100 for k in keys}
    me, nat = dist(ys), NATIONAL_DECADES
    mx = max(max(me.values()), max(nat.values()))
    yr = TODAY.year
    def lab(k):
        return "~1979" if k == 1970 else "2020~" if k == 2020 else str(k)[2:] + "년대"
    cols = ''.join(
        f'<div class="dc-col"><div class="dc-pair">'
        f'<span class="dc-b me{" old" if yr - (k + 9) >= 30 else ""}" style="height:{round(me[k] / mx * 82)}%"><i>{round(me[k])}</i></span>'
        f'<span class="dc-b nat" style="height:{round(nat[k] / mx * 82)}%"><i>{round(nat[k])}</i></span>'
        f'</div><span class="dc-x">{lab(k)}</span></div>' for k in keys)
    old_me = round(sum(1 for y in ys if yr - y >= 30) / len(ys) * 100)
    cmp = '더 많아요' if old_me > NATIONAL_OLD + 3 else '더 적어요' if old_me < NATIONAL_OLD - 3 else '비슷해요'
    return (f'<p>{E(gu)}{josa(gu, '은', '는')} 지은 지 30년 넘은 아파트가 <b>{old_me}%</b>로, 전국 평균 <b>{NATIONAL_OLD}%</b>보다 {cmp}.</p>'
            f'<figure class="dchart" role="img" aria-label="{E(gu)}와 전국 평균의 아파트 지은 연도 비율">'
            f'<div class="dc-legend"><span><i class="me"></i>{E(gu)}</span><span><i class="nat"></i>전국 평균</span></div>'
            f'<div class="dc-plot">{cols}</div><figcaption>{"단지 비율(%)" if SLIM_NOW[0] else "아파트 지은 연도별 단지 비율(%) · 진한 파랑은 지은 지 30년 넘은 단지예요"}</figcaption></figure>')

def choose_section(trade, gu):
    where = f'{E(gu)}에서 ' if gu else ''
    return (f'<section class="card"><h2>{E(trade)} 업체, 이렇게 비교해서 고르세요</h2>'
            f'<p>{where}{E(trade)} 업체를 처음 부를 때는 두세 곳에 같은 내용으로 물어보고 비교하는 게 가장 확실해요.</p>'
            '<ul class="plain"><li><b>출장비와 작업비를 나눠서</b> 물어보세요. 고치지 못해도 출장비를 받는지 미리 알아야 해요.</li>'
            '<li><b>사진을 보내고 대략 견적</b>을 받아 보세요. 와서 보고 값이 크게 달라지면 이유를 꼭 물어보세요.</li>'
            '<li><b>사업자등록이 된 업체</b>인지, 작업 뒤 <b>영수증이나 카드 결제</b>가 되는지 확인하세요. 나중에 하자가 생겼을 때 근거가 돼요.</li>'
            '<li><b>다시 고장 나면 무상으로 봐 주는 기간</b>이 있는지 물어보세요.</li></ul></section>')

_GP = os.path.join(ROOT, 'data', 'citygas.json')
CITYGAS = json.load(open(_GP, encoding='utf-8')) if os.path.exists(_GP) else {'regions': {}}

def gas_section(region):
    """그 지역을 맡은 도시가스 회사와 고객센터 번호 (한국도시가스협회 자료)."""
    gu = gu_name(region)
    L = CITYGAS['regions'].get(region)
    if L:
        rows = ''.join(f'<tr><td>{E(c)}</td><td><a href="tel:{E(p.replace("-", ""))}">{E(p)}</a></td></tr>' for c, p in L)
        many = f'<p class="muted">{E(gu)}{josa(gu, '은', '는')} 동네에 따라 맡은 회사가 나뉘어요. 가스 요금 고지서에 적힌 회사와 번호가 가장 정확해요.</p>' if len(L) > 1 else '<p class="muted">동네 끝자락은 맡은 회사가 다를 수 있어요. 가스 요금 고지서에 적힌 번호가 가장 정확해요.</p>'
        body = (f'<p>{E(gu)}에서 도시가스를 공급하는 회사예요. 가스 냄새가 나거나, 가스레인지도 불이 안 붙어서 가스가 안 들어오는 것 같을 때는 보일러 업체보다 <b>도시가스 회사에 먼저</b> 연락하세요.</p>'
                f'<div class="tbl"><table><thead><tr><th scope="col">도시가스 회사</th><th scope="col">고객센터</th></tr></thead><tbody>{rows}</tbody></table></div>{many}')
    else:
        body = (f'<p>한국도시가스협회 고객센터 목록에는 {E(gu)}{josa(gu, '을', '를')} 맡은 도시가스 회사가 나오지 않아요. 도시가스가 아직 안 들어온 동네가 많을 수 있어요.</p>'
                '<p>LPG(프로판 가스)를 쓰는 집이라면 가스통이나 계량기에 붙은 판매점 번호로 연락하세요. 도시가스를 쓰는 집이라면 가스 요금 고지서에 적힌 번호로 연락하면 돼요.</p>')
    if SLIM_NOW[0] and L:
        return (f'<section class="card"><h2>{E(gu)} 도시가스 회사 연락처</h2><div class="tbl"><table><thead><tr><th scope="col">도시가스 회사</th><th scope="col">고객센터</th></tr></thead><tbody>{rows}</tbody></table></div>'
                f'<p class="source">출처: 한국도시가스협회 ({E(CITYGAS.get("_date", ""))} 확인)</p></section>')
    return (f'<section class="card"><h2>{E(gu)} 도시가스 회사 연락처</h2>{body}'
            f'<p class="warn"><b>가스 냄새가 나면</b> 전기 스위치를 건드리지 말고 밸브를 잠근 뒤 밖에서 도시가스 회사나 119에 연락하세요.</p>'
            f'<p class="source">출처: 한국도시가스협회 도시가스 고객센터 찾기 ({E(CITYGAS.get("_date", ""))} 확인)</p></section>')

def spot_map(gu, trade, stores):
    """그 지역 업체가 어디 모여 있는지 카카오 지도 API로 바로 보여 줘요 (캡처 저장 없음, 볼 때마다 API가 그려요)."""
    pts = [[r[3], r[4]] for r in (stores or []) if len(r) > 4 and r[3] and r[4]][:200]
    if len(pts) < 3:
        return ''
    return (f'<section class="card"><h2>{E(gu)} {E(trade)} 업체 위치</h2>'
            + ('' if SLIM_NOW[0] else f'<p>점 하나가 업체 한 곳이에요. {E(gu)}에서 {E(trade)} 업체가 어디에 몰려 있는지 한눈에 볼 수 있어요.</p>')
            + f'<div class="spot" data-pts=\'{json.dumps(pts)}\'><p class="muted spot-wait">…</p></div>'
            + ('<p class="source">지도: 카카오맵</p></section>' if SLIM_NOW[0] else '<p class="source">지도: 카카오맵 · 위치는 공공데이터 주소 기준이라 실제와 조금 다를 수 있어요.</p></section>'))

def view_section(gu, pts, center=None, what='업체'):
    """카카오 지도 API로 위성(스카이뷰)·로드뷰를 그 자리에서 보여 줘요. 캡처 저장 없음."""
    pts = [p for p in pts if p and p[0] and p[1]][:60]
    if not center and pts:
        center = (round(sum(p[0] for p in pts) / len(pts), 5), round(sum(p[1] for p in pts) / len(pts), 5))
    if not center or not center[0]:
        return ''
    return (f'<section class="card"><h2>{E(gu)} 실제 모습 보기 (위성사진·로드뷰)</h2>'
            + ('' if SLIM_NOW[0] else f'<p>{E(gu)} 동네가 실제로 어떻게 생겼는지 위성사진과 거리 사진(로드뷰)으로 볼 수 있어요. '
            f'{E(what)} 위치 번호를 누르면 그 앞 도로 모습이 나와서, 처음 가는 곳도 입구와 주차할 곳을 미리 확인할 수 있어요.</p>')
            + f'<div class="kview" data-lat="{center[0]}" data-lng="{center[1]}" data-pts=\'{json.dumps([[p[0], p[1], p[2]] for p in pts], ensure_ascii=False)}\'>'
            f'<button type="button" class="btn ghost wide kv-load">위성사진·로드뷰 보기</button>'
            f'<div class="kv-map" hidden></div><div class="kv-rv" hidden></div>'
            f'<p class="muted kv-note" hidden>위성사진에서 원하는 도로를 누르면 그 자리 로드뷰가 나와요.</p></div>'
            f'<p class="source">지도·위성사진·로드뷰: 카카오맵. 촬영 시점에 따라 지금 모습과 다를 수 있어요.</p></section>')

def dong_section(trade, gu, dongs, apts):
    if not dongs:
        return ''
    dl = dongs[:30]
    p = [f'{E(gu)}의 주요 동네는 {E("·".join(dl))}{" 등" if len(dongs) > 30 else ""}이에요.']
    by = defaultdict(list)
    for a in apts:
        if a[1]:
            by[a[1]].append(a)
    rank = sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:6]
    items = ''
    if rank:
        def one(d, lst):
            ys = [a[2] for a in lst if a[2]]
            hh = sum(a[3] or 0 for a in lst)
            s = f'<li><b>{E(d)}</b><span>아파트 {len(lst)}곳'
            if hh: s += f', 약 {hh:,}세대'
            if ys: s += f', {min(ys)}~{max(ys)}년에 지음'
            return s + '</span></li>'
        items = '<h3 class="sub">아파트가 많은 동네</h3><ul class="steps">' + ''.join(one(d, l) for d, l in rank) + '</ul>'
        p.append(f'그중 아파트가 가장 많은 곳은 {E(rank[0][0])}이에요.')
    if not SLIM_NOW[0]: p.append(f'업체에 전화하거나 요청할 때 <b>동 이름과 아파트·건물 이름</b>을 함께 말하면 이동 시간과 출장비를 더 정확히 들을 수 있어요. '
             f'같은 {E(gu)} 안이라도 업체 위치에서 먼 동네는 출장비가 더 붙을 수 있으니 {E(trade)} 업체를 고를 때 가까운 곳을 먼저 보세요.')
    return f'<section class="card"><h2>{E(gu)} 동네별로 보면</h2><p>{" ".join(p)}</p>{items}</section>'

WORK_PHOTOS = json.load(open(os.path.join(ROOT, 'data', 'work_photos.json'), encoding='utf-8'))

_PS = os.path.join(ROOT, 'data', 'photo_slots.json')
PHOTO_SLOTS = json.load(open(_PS, encoding='utf-8')) if os.path.exists(_PS) else {}

def slot_fig(kind, slots, seed, title='', bare=False):
    """글의 해당 부분에 맞는 사진 1장. 지역(seed)마다 다른 사진이 골라져요."""
    S = PHOTO_SLOTS.get(kind)
    if not S:
        return ''
    if isinstance(slots, str):
        slots = [slots]
    pool = [x for sl in slots for x in S.get(sl, []) if os.path.exists(os.path.join(ROOT, 'static', 'img', x[0] + '.webp'))]
    if not pool:
        return ''
    h = int(hashlib.md5((seed + '|' + '+'.join(slots)).encode()).hexdigest(), 16)
    f, cap = pool[h % len(pool)]
    if SLIM_NOW[0] and not bare:
        cap1 = cap.split('. ')[0].rstrip('.') + '.'
        return (f'<section class="card sfig"><figure><img src="/img/{f}.webp" width="1200" height="675" alt="{E(cap)}" loading="lazy" decoding="async">'
                f'<figcaption>{E(cap1)} <span class="muted">(예시 이미지)</span></figcaption></figure></section>')
    if bare:
        return f'<figure class="sfig-in"><img src="/img/{f}.webp" width="1200" height="675" alt="{E(cap)}" loading="lazy" decoding="async"><figcaption>{E(cap)} <span class="muted">(예시 이미지)</span></figcaption></figure>'
    head = f'<h2>{E(title)}</h2>' if title else ''
    return (f'<section class="card sfig">{head}<figure><img src="/img/{f}.webp" width="1200" height="675" alt="{E(cap)}" loading="lazy" decoding="async">'
            f'<figcaption>{E(cap)}</figcaption></figure><p class="muted">예시 이미지예요. 실제 현장·업체와 다를 수 있어요.</p></section>')

def photo_section(key, title):
    w = WORK_PHOTOS.get(key)
    if not w or not os.path.exists(os.path.join(ROOT, 'static', 'img', f'{w[0]}-1.webp')):
        return ''
    figs = ''.join(f'<figure><img src="/img/{w[0]}-{i}.webp" width="1200" height="675" alt="{E(w[i])}" loading="lazy" decoding="async">'
                   f'<figcaption>{E(w[i])}</figcaption></figure>' for i in (1, 2))
    return f'<section class="card work"><h2>{E(title)}</h2><div class="work-figs">{figs}</div><p class="muted">사진은 이해를 돕는 예시예요. 실제 업체와 다를 수 있어요.</p></section>'

SLIM = set(GUIDES)
SLIM_NOW = [False]

def apt_table(kind, region, apts, lim=50):
    """그 지역 아파트 단지 표 (오래된 순). 지역마다 완전히 다른 실제 자료예요."""
    L = [a for a in apts if a[2]]
    if len(L) < 3:
        return ''
    gu = gu_name(region); yr = TODAY.year
    L = sorted(L, key=lambda a: (a[2], a[0]))[:lim]
    rows = ''.join(f'<tr><td>{E(a[0])}</td><td>{E(a[1] or "")}</td><td>{a[2]}<small> ({yr - a[2]}년)</small></td>'
                   f'<td>{(f"{a[3]:,}" if a[3] else "")}</td><td>{E((a[4] or "").replace("개별난방", "개별").replace("지역난방", "지역").replace("중앙난방", "중앙"))}</td></tr>' for a in L)
    more = f'<p class="muted">{len(apts)}곳 중 오래된 단지 {len(L)}곳만 보여 드려요.</p>' if len(apts) > len(L) else ''
    return (f'<section class="card"><h2>{E(gu)} 오래된 아파트 단지부터 보기</h2>'
            f'<div class="tbl"><table><thead><tr><th scope="col">단지</th><th scope="col">동</th><th scope="col">지은 해</th><th scope="col">세대</th><th scope="col">난방</th></tr></thead><tbody>{rows}</tbody></table></div>{more}'
            f'<p class="source">공동주택관리정보시스템(K-apt) 관리비 공개 단지 기준</p></section>')

def region_story(kind, region, ctx):
    """그 지역 자료로만 쓰는 이야기 (업체 분포·아파트·난방·도시가스·이웃 지역)."""
    G = GUIDES[kind]; gu = gu_name(region); yr = TODAY.year
    stores = ctx.get('stores') or []; apts = ctx.get('apts') or []
    P = []
    if stores:
        dc = Counter(r[2] for r in stores if r[2])
        top = dc.most_common(3)
        if top:
            share = round(sum(c for _, c in top) / len(stores) * 100)
            P.append(f'{E(gu)}에서 찾은 {E(G["name"])} 업체는 <b>{len(stores)}곳</b>이에요. '
                     + '·'.join(f'{E(d)}({c}곳)' for d, c in top) + f'에 전체의 {share}%가 모여 있어요. '
                     + (f'{E(top[0][0])} 쪽은 업체가 가까워요.' if top[0][1] >= 2 else ''))
    ys = [a[2] for a in apts if a[2]]
    if len(ys) >= 3:
        avg = round(sum(ys) / len(ys)); o = sum(1 for y in ys if yr - y >= 30)
        old = sorted((a for a in apts if a[2]), key=lambda a: a[2])[:2]
        new = sorted((a for a in apts if a[2]), key=lambda a: -a[2])[:2]
        P.append(f'{E(gu)} 아파트 {len(ys)}곳의 평균 준공 연도는 {avg}년이고, 지은 지 30년이 넘은 단지가 {o}곳이에요. '
                 f'오래된 단지로는 {"·".join(E(a[0]) + f"({a[2]})" for a in old)}, 새 단지로는 {"·".join(E(a[0]) + f"({a[2]})" for a in new)}이(가) 있어요.')
        indiv = [a for a in apts if a[4].startswith('개별')]
        central = [a for a in apts if a[4] in ('지역난방', '중앙난방')]
        if kind == '보일러-고장' and (indiv or central):
            ip = round(len(indiv) / len(apts) * 100)
            P.append(f'난방 방식은 개별난방 {len(indiv)}곳({ip}%), 지역·중앙난방 {len(central)}곳이에요. '
                     + (f'{E(central[0][0])} 같은 지역·중앙난방 단지는 관리사무소가 먼저예요.' if central else ''))
    if kind == '보일러-고장':
        L = CITYGAS['regions'].get(region)
        if L:
            P.append(f'{E(gu)}의 도시가스는 ' + '·'.join(f'{E(c)}({E(p)})' for c, p in L)
                     + ('가 동네별로 나눠 맡고 있어요. ' if len(L) > 1 else '이(가) 공급해요. ')
                     )
        else:
            P.append(f'{E(gu)}{josa(gu, "은", "는")} 협회 목록에 도시가스 회사가 없어 LPG를 쓰는 집이 많을 수 있어요.')
    near = ctx.get('near') or []
    if near:
        P.append(f'이웃한 {"·".join(E(short_region(r)) for r in near[:3])} 업체도 부를 수 있어요.')
    if not P:
        return ''
    return f'<section class="card"><h2>{E(gu)} {E(G["name"])}, 우리 동네는 이래요</h2>' + ''.join(f'<p>{x}</p>' for x in P) + '</section>'

def region_faq(kind, region, ctx):
    G = GUIDES[kind]; gu = gu_name(region); F = []
    stores = ctx.get('stores') or []; apts = ctx.get('apts') or []
    if stores:
        top = Counter(r[2] for r in stores if r[2]).most_common(1)
        F.append((f'{gu} {G["name"]} 업체는 몇 곳인가요?', f'공공데이터 기준 {len(stores)}곳이에요.' + (f' {top[0][0]}에 가장 많아요({top[0][1]}곳).' if top else '')))
    if kind == '보일러-고장':
        L = CITYGAS['regions'].get(region)
        if L:
            F.append((f'{gu} 도시가스 회사는 어디인가요?', ', '.join(f'{c}({p})' for c, p in L) + '예요. 가스 요금 고지서 번호가 가장 정확해요.'))
    ys = [a[2] for a in apts if a[2]]
    if len(ys) >= 3:
        o = round(sum(1 for y in ys if TODAY.year - y >= 30) / len(ys) * 100)
        F.append((f'{gu} 아파트는 오래된 편인가요?', f'아파트 {len(ys)}곳 중 지은 지 30년 넘은 단지가 {o}%예요. 전국 평균은 {NATIONAL_OLD}%예요.'))
    return F

def slim_lead(kind, region, ctx):
    gu = gu_name(region); n = len(ctx.get('stores') or []); a = len(ctx.get('apts') or [])
    L = CITYGAS['regions'].get(region)
    bits = [f'업체 {n}곳'] if n else []
    if a: bits.append(f'아파트 {a}곳의 나이·난방 방식')
    if L: bits.append(f'도시가스 {L[0][0]} 번호')
    return E(f'{gu}의 ' + ', '.join(bits) + '를 한 페이지에 모았어요.') if bits else E(f'{gu} {GUIDES[kind]["name"]} 때 볼 것을 모았어요.')

def slim_summary(kind, region):
    G = GUIDES[kind]; gu = gu_name(region)
    first = ' · '.join(t for t, _ in G['steps'][:3])
    return (f'<section class="card"><h2>{E(gu)}에서 업체 부르기 전에</h2>'
            f'<p><a class="btn" href="{E(url_path("진단", kind))}">증상 고르고 하나씩 확인하기</a> '
            f'<a class="btn ghost" href="{E(url_path("안내", kind))}">{E(G["name"])} 전체 안내</a></p></section>')

def guide_page(kind, region, ctx=None):
    G = GUIDES[kind]
    SLIM_NOW[0] = kind in SLIM
    gu = gu_name(region)
    ctx = ctx or {}
    dongs = ctx.get('dongs') or []
    local = dong_section(G['name'], gu, dongs, ctx.get('apts') or [])
    near = ctx.get('near') or []
    near_html = ''
    if near:
        near_html = f'<section class="card"><h2>가까운 지역 {E(G["name"])}</h2><div class="links">' + ''.join(
            f'<a href="{E(url_path("안내", kind, r.replace(" ", "-")))}">{E(short_region(r))}</a>' for r in near) + '</div></section>'
    ctr = ctx.get('center') or ('', '')
    stores = ctx.get('stores') or []
    if stores:
        dc = Counter(r[2] for r in stores if r[2])
        stores = sorted(stores, key=lambda r: (-dc.get(r[2], 0), r[2], r[0]))[:300]
        cards = ''.join(store_card(r, i, G['name'], region) for i, r in enumerate(stores))
        total = len(ctx.get('stores'))
        sd = ctx.get('store_date', '')
        live_static = (f'<section class="card"><h2>{E(gu)} {E(G["name"])} 업체 {total}곳</h2>'
            f'<div id="members" data-region="{E(region)}" data-trade="{E(G["name"])}" hidden></div>'
            + ('' if SLIM_NOW[0] else f'<p class="muted">\'전화\'를 누르면 번호를 찾아 바로 걸려요.</p>')
            + f'<div class="shops" data-page="20">{cards}</div>'
            f'<button type="button" class="btn ghost wide more" hidden>더 보기</button>'
            + (f'<p class="muted">그 외 {total - len(stores)}곳은 네이버에서 찾아보세요.</p>' if total > len(stores) else '')
            + (f'<p class="source">출처: 소상공인시장진흥공단 상가정보{(" (" + sd[:4] + "." + sd[4:6] + ")") if sd else ""}</p></section>' if SLIM_NOW[0] else
            f'<p class="source">업체 이름·주소: 소상공인시장진흥공단 상가(상권)정보{(" (" + sd[:4] + "." + sd[4:6] + ")") if sd else ""}. 영업 상황이 바뀌었을 수 있어요. '
            f'사장님이 등록하면 전화번호·영업시간을 직접 고칠 수 있어요. <a href="{E(url_path("사장님"))}">사장님 무료 등록</a></p></section>'))
    live = (f'<section class="card live-shops" data-kw="{E("|".join(G.get("kw", [G["name"]])))}" data-gu="{E(gu.split()[-1])}" data-must="{E(G.get('must', ''))}" data-area="{E(gu)}" data-trade="{E(G['name'])}" data-region="{E(region)}" data-lat="{ctr[0]}" data-lng="{ctr[1]}">'
            f'<h2>{E(gu)} {E(G["name"])} 업체</h2>'
            f'<div id="members" data-region="{E(region)}" data-trade="{E(G["name"])}" hidden></div>'
            f'<p class="muted live-note">누르면 바로 전화가 걸려요. 업체 목록은 카카오 지도에서 지금 찾아서 보여 줘요.</p>'
            f'<div class="live-list" aria-live="polite"><p class="muted">업체를 찾는 중이에요…</p></div>'
            f'<button type="button" class="btn ghost wide live-more" hidden>더 보기</button>'
            f'<p class="muted"><a href="https://m.search.naver.com/search.naver?query={quote(gu + " " + G.get("kw", [G["name"]])[0])}" target="_blank" rel="noopener">네이버에서 {E(gu)} {E(G["name"])} 더 찾기</a></p>'
            f'<p class="source">사장님이 등록하면 전화번호·영업시간을 직접 고칠 수 있어요. <a href="{E(url_path("사장님"))}">사장님 무료 등록</a></p></section>')
    if stores:
        live = live_static
    car = ''
    if ctx.get('shops'):
        car = f'<p class="muted">차 문제라면 <a href="{E(url_path("자동차정비", slug_region(region)))}">{E(gu)} 자동차 정비소 {ctx["shops"]}곳</a>도 볼 수 있어요.</p>'
    SOON = f'''<section class="card soon"><h2>원하는 시간에 맞춰 부르는 기능, 준비 중이에요</h2><p>시간과 예산을 정해 요청하면 {E(gu)} 업체 사장님들이 가능한 시간과 예상 가격으로 답해 주는 기능을 만들고 있어요. <a href="{E(url_path('요청'))}?t={quote(G['name'])}&amp;r={quote(region)}">어떻게 요청하는지 미리 보기</a></p></section>'''
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
    gname, gkinds = group_of(kind)
    others = ''.join(f'<a href="{E(url_path("안내", k, region.replace(" ", "-")))}">{E(gu)} {E(GUIDES[k]["name"])}</a>' for k in gkinds if k != kind and k in GUIDES)
    rest = ''.join(f'<a href="{E(url_path("안내", k, region.replace(" ", "-")))}">{E(GUIDES[k]["name"])}</a>' for k in GUIDES if k not in gkinds)
    body = f'''<section class="hero"><h1>{E(gu)} {E(G['name'])},<br>{E(G['h1_tail'])}</h1>
<p class="lead">{E(fill(G['lead'])) if kind not in SLIM else slim_lead(kind, region, ctx)}</p></section>
{warn}
{'' if kind in SLIM else slot_fig(kind, 'warn', region)}
{live}
{'' if kind in SLIM else view_section(gu, [(r[3], r[4], i + 1) for i, r in enumerate(stores[:60]) if len(r) > 4], ctx.get('center'))}
{frost_box(region) if kind in ('수도-동파', '보일러-고장') else ''}
{gas_section(region) if kind == '보일러-고장' else ''}
{spot_map(gu, G['name'], stores)}
{'' if kind in PHOTO_SLOTS else photo_section(kind, G['name'] + ' 현장은 이렇게 해요')}
{'' if kind in SLIM else related_articles(kind)}
{region_story(kind, region, ctx) if kind in SLIM else ''}
{slim_summary(kind, region) if kind in SLIM else f'<section class="card"><h2>{E(G["steps_title"])}</h2><ol class="steps">{steps}</ol></section>'}
{slot_fig(kind, 'check', region)}
{'' if kind in SLIM else wait_section(kind, gu, near)}
{slot_fig(kind, ['error', 'hotwater', 'heat'], region)}
{'' if kind in SLIM else f'<section class="card"><h2>이럴 땐 업체를 부르세요</h2><ul class="plain">{when}</ul></section>'}
{slot_fig(kind, 'pro', region)}
{'' if kind in SLIM else extra}
{f'<section class="card"><h2>업체에 전화할 때 꼭 물어볼 것</h2><ul class="plain">{ask}</ul></section>' if ask and kind not in SLIM else ''}
{'' if kind in SLIM or not LIVE else SOON}
{local}
{age_section(kind, gu, ctx.get('apts') or [], slim=kind in SLIM)}
{apt_table(kind, region, ctx.get('apts') or []) if kind in SLIM else ''}
{apt_section(kind, gu, ctx.get('apts'), ctx.get('apt_date', ''))}
{'' if kind in SLIM else choose_section(G['name'], gu)}
{slot_fig(kind, 'prevent', region)}
{faq_html(region_faq(kind, region, ctx) if kind in SLIM else faqs)}
<section class="card"><h2>{E(gu)} {E(gname)}</h2><div class="links">{others}</div>{car}</section>
{'' if kind in SLIM else f'<section class="card"><h2>{E(gu)} 다른 업종</h2><div class="links">{rest}</div></section>'}
{near_html}
{'' if kind in SLIM else owner_cta(gu + ' ' + G['name'])}
{'' if kind in SLIM else '<p class="source">이 안내는 일반적인 정보예요. 집 상태에 따라 방법과 비용이 달라질 수 있어요. 위험하다고 느껴지면 혼자 하지 말고 전문가를 부르세요.</p>'}'''
    crumbs = [('홈', '/'), (G['name'], url_path('안내', kind)), (f'{gu} {G["name"]}', path)]
    # 동네 업체가 3곳 미만인 안내 페이지는 지역 이름만 다른 비슷한 글이 되기 쉬워서 검색에서 빼 둬요
    thin = len(ctx.get('stores') or []) < 3
    if kind in SLIM and not thin:
        _t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<script.*?</script>', '', body, flags=re.S)))).strip()
        _ap = len([a for a in (ctx.get('apts') or []) if a[2]])
        thin = len(_t) < 3100 or _ap < 25
    return path, page(title, desc, path, body, crumbs, [faq_ld(faqs)], noindex=thin)

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
<section class="card"><h2>지금은 등록 신청을 받고 있어요</h2><p>업체 이름, 사업자등록번호, 연락받을 휴대폰 번호를 적어 신청해 주세요. 확인 후 연락드려요. 신청은 무료예요.</p>
<div id="join-mail"{' hidden' if CFG.get('supabase_url') else ''}><a class="btn dark" href="{E(mail_link('내시간에 사장님 등록 신청'))}">이메일로 등록 신청하기</a><p class="muted">받는 곳: {em}</p></div>
<form id="join" class="form" hidden>
<label class="fld"><span>업체 이름</span><input name="biz_name" required maxlength="60"></label>
<label class="fld"><span>사업자등록번호 (10자리)</span><input name="biz_no" required inputmode="numeric" placeholder="000-00-00000"></label>
<label class="fld"><span>대표자 이름</span><input name="owner_name" maxlength="30"></label>
<label class="fld"><span>요청 알림 받을 휴대폰</span><input name="mobile" required type="tel" inputmode="tel" placeholder="010-0000-0000"></label>
<label class="fld"><span>손님에게 보일 업체 전화 (선택)</span><input name="public_phone" type="tel" placeholder="032-000-0000"></label>
<label class="fld"><span>업종</span><select name="trade" required>{''.join(f'<option>{E(t)}</option>' for t in ['자동차 정비'] + [G['name'] for G in GUIDES.values()] + [M['name'] for M in FOOD.values()] + [gm['name'] for sec, S in DIRM.items() if S['kind'] == 'pro' for gm in S['groups'].values()])}</select></label>
<label class="fld"><span>지역</span><select name="region" required>{''.join(f'<option>{E(r)}</option>' for r in sorted(RELEASED))}</select></label>
<label class="fld"><span>업체 주소</span><input name="address" maxlength="120"></label>
<label class="fld"><span>대표 가격대 (선택)</span><input name="price_note" maxlength="100" placeholder="예: 엔진오일 5~7만 원"></label>
<label class="agree"><input type="checkbox" name="sms_consent" required><span>손님 예약 요청 알림 문자를 받는 데 동의해요. 언제든 그만 받을 수 있어요.</span></label>
<p id="join-msg" class="err" aria-live="polite"></p>
<button type="submit" class="btn blue wide">무료 등록 신청하기</button></form></section>''', scripts=f'<script src="/flow.js?v={V("flow.js")}" defer></script>')
    p = url_path('정보-수정-삭제-요청')
    pages[p] = page('업체 정보 수정·삭제 요청 | 내시간에', '내시간에에 실린 업체 정보의 수정이나 삭제를 요청하는 방법이에요.', p, f'''<section class="hero"><h1>업체 정보 수정·삭제 요청</h1>
<p class="lead">내시간에의 업체 정보는 공공데이터(국토교통부 표준데이터 등)를 바탕으로 해요. 정보가 틀렸거나, 사장님이 정보 게시를 원하지 않으시면 알려 주세요.</p></section>
<section class="card"><h2>요청 방법</h2><ol class="steps"><li><b>업체 이름과 주소</b><span>어느 업체인지 알 수 있게 적어 주세요.</span></li><li><b>원하시는 것</b><span>수정(무엇을 어떻게) 또는 삭제를 적어 주세요.</span></li><li><b>보내기</b><span>요청을 받으면 확인 후 바로 처리하고 결과를 알려 드려요.</span></li></ol>
<a class="btn dark" href="{E(mail_link('내시간에 업체 정보 수정·삭제 요청'))}">이메일로 요청하기</a><p class="muted">받는 곳: {em}</p></section>
<section class="card"><h2>정보를 어디서 가져왔나요?</h2><p>공개된 공공데이터에서 업체 이름, 주소, 업종, 전화번호, 영업시간을 가져와요. 전화번호가 없는 업체는 손님이 '바로 전화'를 누를 때만 지도 서비스에서 찾아 화면에 보여 주며, 그 번호를 저장하지 않아요. 개인정보 보호법 제20조에 따라 요청하시면 수집 출처와 이용 목적을 알려 드리고, 처리 정지를 요청하실 수 있어요.</p></section>''')
    p = url_path('개인정보처리방침')
    pages[p] = page('개인정보처리방침 | 내시간에', '내시간에 개인정보처리방침', p, f'''<section class="hero"><h1>개인정보처리방침</h1><p class="lead">시행일: {TODAY.isoformat()}</p></section>
<section class="card"><h2>1. 손님 정보</h2><p>지금 내시간에는 손님에게 회원가입이나 개인정보 입력을 받지 않아요. 예약 요청 기능이 열리면 요청 전달과 답변 문자 발송에 필요한 휴대폰 번호만 동의를 받아 받고, 30일 뒤 지워요.</p></section>
<section class="card"><h2>2. 업체 정보</h2><p>업체 이름, 주소, 업종, 전화번호, 영업시간은 공공데이터에서 가져온 공개 정보예요. 출처: 국토교통부 전국자동차정비업체표준데이터, 소상공인시장진흥공단 상가(상권)정보, 국토교통부 공동주택관리정보시스템(K-apt). 목록 순서는 추천 순위가 아니고, 업체에게 돈을 받고 위로 올려 주지 않아요. 수집 출처·이용 목적 안내와 처리 정지 요청은 <a href="{E(url_path('정보-수정-삭제-요청'))}">정보 수정·삭제 요청</a>으로 할 수 있어요.</p></section>
<section class="card"><h2>3. 외부 서비스</h2><p>위치 지도는 오픈스트리트맵, 전화번호 찾기는 카카오 지도 서비스를 쓸 수 있어요. 이때 손님 브라우저가 해당 서비스에 직접 접속해요. 방문 통계를 위해 구글 애널리틱스(Google Analytics)를 써요. 쿠키로 방문 페이지·기기·대략적인 지역 같은 통계를 모으며, 이름이나 전화번호 같은 개인정보는 보내지 않아요. 브라우저 설정에서 쿠키를 막을 수 있어요.</p></section>
<section class="card"><h2>4. 문의</h2><p>개인정보 관련 문의: {em}</p></section>''')
    p = url_path('요청')
    pages[p] = page('원하는 시간에 예약 요청 (미리 보기) | 내시간에', '원하는 날짜·시간·예산을 정해 동네 업체에 한 번에 요청하는 화면 미리 보기예요.', p,
        '<div id="req" aria-live="polite"><noscript>이 화면은 자바스크립트가 필요해요.</noscript></div>', noindex=True, scripts=f'<script src="/req.js?v={V("req.js")}" defer></script>')
    p = url_path('내-요청')
    pages[p] = page('내 요청 | 내시간에', '내 예약 요청과 업체 답변', p, '<div id="my" aria-live="polite"></div>', noindex=True, scripts=f'<script src="/flow.js?v={V("flow.js")}" defer></script>')
    p = url_path('답변')
    pages[p] = page('손님 요청에 답하기 | 내시간에', '사장님 답변 화면', p, '<div id="reply" aria-live="polite"></div>', noindex=True, scripts=f'<script src="/flow.js?v={V("flow.js")}" defer></script>')
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
    X = GX.get(kind, {})
    steps = ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in G['steps'])
    wait = ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in X.get('wait', []))
    when = ''.join(f'<li>{E(w)}</li>' for w in G['call_when'])
    age = ''.join(f'<li><b>{t}</b><span>{E(X["aging"][k])}</span></li>' for k, t in (('old', '지은 지 30년 넘은 집'), ('mid', '15~30년 된 집'), ('new', '15년 안 된 집'))) if X.get('aging') else ''
    warn = f'<div class="warn">{G["warn"]}</div>' if G.get('warn') else ''
    body = f'''<section class="hero"><h1>{E(G['name'])}, {E(G['h1_tail'])}</h1><p class="lead">아래에서 사는 지역을 고르면 그 지역 업체 목록과 아파트·동네 정보까지 맞춰서 볼 수 있어요. 먼저 어디서나 통하는 방법부터 정리했어요. 급할수록 순서대로 보고, 위험하다 싶으면 바로 전문가를 부르세요.</p></section>
{warn}
<section class="card"><h2>{E(G['steps_title'])}</h2><ol class="steps">{steps}</ol></section>
{f'<section class="card"><h2>업체가 올 때까지 이렇게 하세요</h2><ol class="steps">{wait}</ol></section>' if wait else ''}
<section class="card"><h2>이럴 땐 업체를 부르세요</h2><ul class="plain">{when}</ul></section>
{f'<section class="card"><h2>건물 나이로 보는 {E(G["name"])}</h2><ul class="steps age">{age}</ul></section>' if age else ''}
{''.join(f'<section class="card"><h2>{E(h.replace("{gu}", "우리 동네").replace("{region}", "우리 지역"))}</h2><p>{b.replace("{gu}", "우리 동네").replace("{region}", "우리 지역")}</p></section>' for h, b in G.get('sections', [])) if kind in SLIM else ''}
{slot_fig(kind, ['check', 'error', 'hotwater', 'heat'], 'hub')}
{choose_section(G['name'], '')}
{related_articles(kind)}
{slot_fig(kind, ['pro', 'prevent'], 'hub2')}
{f'<section class="card"><h2>업체에 전화할 때 꼭 물어볼 것</h2><ul class="plain">' + ''.join(f'<li>{E(a)}</li>' for a in G.get('ask', [])) + '</ul></section>' if G.get('ask') else ''}
{faq_html([(q.replace('{gu}', '우리 동네').replace('{region}', '우리 지역'), a.replace('{gu}', '우리 동네').replace('{region}', '우리 지역')) for q, a in G['faqs']])}
<section class="card"><h2>지역별 {E(G['name'])} 안내</h2><p class="muted">시·도를 찾아 우리 시·군·구를 누르세요.</p></section>
{secs}'''
    return path, page(f'{G["name"]} 지역별 안내 | 내시간에', f'{G["name"]} 때 바로 할 일과 업체 부르는 법을 시·군·구별로 안내해요.', path, body, [('홈', '/'), (G['name'], path)])

ARTICLES = json.load(open(os.path.join(ROOT, 'data', 'articles.json'), encoding='utf-8'))

def related_articles(kind):
    L = [(slug, a) for slug, a in ARTICLES.items() if a.get('kind') == kind]
    extra = ''
    if kind in DIAG:
        extra += f'<li><a href="{E(url_path("진단", kind))}">{E(DIAG[kind]["title"])}: 증상 고르고 하나씩 확인하기</a></li>'
    if kind in ('수도-동파', '보일러-고장'):
        extra += f'<li><a href="{E(url_path("정보", "겨울-집-점검"))}">겨울 집 점검 체크리스트</a></li>'
    if not L and not extra:
        return ''
    return '<section class="card"><h2>더 자세히 알아보기</h2><ul class="plain">' + ''.join(
        f'<li><a href="{E(url_path("정보", slug))}">{E(a["title"])}</a></li>' for slug, a in L) + extra + '</ul></section>'

def article_page(slug, a):
    path = url_path('정보', slug)
    secs = ''
    for s in a['sections']:
        inner = ''
        if 'ol' in s:
            inner = '<ol class="steps">' + ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in s['ol']) + '</ol>'
        elif 'ul' in s:
            inner = '<ul class="plain">' + ''.join(f'<li>{E(x)}</li>' for x in s['ul']) + '</ul>'
        elif 'table' in s:
            head, *rows = s['table']
            inner = ('<div class="tbl"><table><thead><tr>' + ''.join(f'<th scope="col">{E(h)}</th>' for h in head) + '</tr></thead><tbody>'
                     + ''.join('<tr>' + ''.join(f'<td>{E(c)}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')
        if s.get('note'):
            inner += f'<p class="muted">{E(s["note"])}</p>'
        secs += f'<section class="card"><h2>{E(s["h"])}</h2>{inner}</section>'
    kind = a.get('kind')
    G = GUIDES.get(kind, {})
    when = ''.join(f'<li>{E(w)}</li>' for w in a.get('call_when', []))
    ask = ''.join(f'<li>{E(w)}</li>' for w in a.get('ask', []))
    gl = url_path('안내', kind) if kind in GUIDES else ''
    src = ''.join(f'<li><a href="{E(u)}" rel="nofollow noopener" target="_blank">{E(t)}</a></li>' for t, u in a.get('sources', []))
    body = f"""<section class="hero"><h1>{E(a['h1'])}</h1><p class="lead">{E(a['lead'])}</p></section>
<div class="warn">{a['warn']}</div>
{secs}
{extra_html('정보/' + slug)}
{photo_section(kind, (G.get('name') or '') + ' 현장은 이렇게 해요') if kind else ''}
<section class="card"><h2>이럴 땐 업체를 부르세요</h2><ul class="plain">{when}</ul>{f'<p><a class="btn" href="{E(gl)}">우리 동네 {E(G.get("name",""))} 업체 찾기</a></p>' if gl else ''}</section>
{f'<section class="card"><h2>업체에 전화할 때 물어볼 것</h2><ul class="plain">{ask}</ul></section>' if ask else ''}
{faq_html(a['faqs'])}
<section class="card"><h2>참고한 자료</h2><ul class="plain src">{src}</ul><p class="muted">공공기관·제조사 안내를 바탕으로 정리했어요. 마지막 확인: {TODAY.isoformat()}</p></section>"""
    art = {'@context': 'https://schema.org', '@type': 'Article', 'headline': a['title'], 'description': a['desc'],
           'dateModified': TODAY.isoformat(), 'inLanguage': 'ko', 'mainEntityOfPage': abs_url(path),
           'author': {'@type': 'Organization', 'name': '내시간에'}, 'publisher': {'@type': 'Organization', 'name': '내시간에'}}
    return path, page(f"{a['title']} | 내시간에", a['desc'], path, body, [('홈', '/'), ('생활 정보', url_path('정보')), (a['title'], path)], [art, faq_ld(a['faqs'])])

def article_index():
    path = url_path('정보')
    items = ''.join(f'<li><a href="{E(url_path("정보", slug))}"><b>{E(a["title"])}</b></a><span>{E(a["desc"])}</span></li>' for slug, a in ARTICLES.items())
    items += f'<li><a href="{E(url_path("정보", "겨울-집-점검"))}"><b>겨울 집 점검 체크리스트</b></a><span>수도·보일러·전기를 하나씩 체크하고, 체크한 항목은 기억돼요.</span></li>'
    items += f'<li><a href="{E(url_path("진단"))}"><b>자가진단</b></a><span>보일러·동파·하수구·누수·전기 증상을 고르면 집에서 먼저 확인할 것을 알려 드려요.</span></li>'
    items += f'<li><a href="{E(url_path("연락처카드"))}"><b>우리 집 비상 연락처 카드</b></a><span>동네를 고르면 가스·수도·전기 연락처를 한 장으로 만들어 드려요.</span></li>'
    body = f'<section class="hero"><h1>생활 정보</h1><p class="lead">집에 문제가 생겼을 때 업체 부르기 전에 볼 것들을 공공기관 안내를 바탕으로 정리했어요.</p></section><section class="card"><ul class="steps">{items}</ul></section>' + extra_html('정보') + mixed_photos('업체를 부르기 전에 먼저 확인해요', [('수도-동파', 1), ('보일러-고장', 2)])
    return path, page('생활 정보 | 내시간에', '수도 동파, 보일러 에러처럼 집에 문제가 생겼을 때 먼저 볼 것들을 정리했어요.', path, body, [('홈', '/'), ('생활 정보', path)])

EXTRA = json.load(open(os.path.join(ROOT, 'data', 'extra_content.json'), encoding='utf-8'))

def extra_html(key):
    out = ''
    for sec in EXTRA.get(key, []):
        inner = ''.join(f'<p>{E(x)}</p>' for x in sec.get('p', []))
        if sec.get('ul'):
            inner += '<ul class="plain">' + ''.join(f'<li>{E(x)}</li>' for x in sec['ul']) + '</ul>'
        if sec.get('ol'):
            inner += '<ol class="steps">' + ''.join(f'<li><b>{E(t)}</b><span>{E(d)}</span></li>' for t, d in sec['ol']) + '</ol>'
        if sec.get('after'):
            inner += f'<p>{E(sec["after"])}</p>'
        out += f'<section class="card"><h2>{E(sec["h"])}</h2>{inner}</section>'
    return out

def mixed_photos(title, picks):
    figs = ''
    for key, i in picks:
        w = WORK_PHOTOS.get(key)
        if not w or not os.path.exists(os.path.join(ROOT, 'static', 'img', f'{w[0]}-{i}.webp')):
            continue
        figs += (f'<figure><img src="/img/{w[0]}-{i}.webp" width="1200" height="675" alt="{E(w[i])}" loading="lazy" decoding="async">'
                 f'<figcaption>{E(w[i])}</figcaption></figure>')
    if not figs:
        return ''
    return f'<section class="card work"><h2>{E(title)}</h2><div class="work-figs">{figs}</div><p class="muted">사진은 이해를 돕는 예시예요. 실제 업체와 다를 수 있어요.</p></section>'

DIAG = json.load(open(os.path.join(ROOT, 'data', 'diagnose.json'), encoding='utf-8'))

DIAG_SLOT = {'dead': 'check', 'error': 'error', 'hotwater': 'hotwater', 'heat': 'heat', 'noise': 'pro'}

def diag_page(kind, D):
    path = url_path('진단', kind)
    G = GUIDES.get(kind, {})
    picks = ''.join(f'<button type="button" class="dg-pick" data-s="{E(s["id"])}">{E(s["label"])}</button>' for s in D['symptoms'])
    blocks = ''
    for s in D['symptoms']:
        steps = ''.join(f'<li class="dg-step"><b>{E(t)}</b><span>{E(d)}</span>'
                        f'<div class="dg-btns"><button type="button" class="btn sm dg-ok">해결됐어요</button><button type="button" class="btn ghost sm dg-no">안 됐어요, 다음</button></div></li>'
                        for t, d in s['steps'])
        more = f'<p><a href="{E(s["more"])}">이 증상 더 자세히 보기</a></p>' if s.get('more') else ''
        fig = slot_fig(kind, DIAG_SLOT.get(s['id'], ''), 'diag-' + s['id'], bare=True) if DIAG_SLOT.get(s['id']) else ''
        blocks += (f'<section class="card dg-sym" id="s-{E(s["id"])}" data-s="{E(s["id"])}"><h2>{E(s["label"])}</h2>{fig}'
                   f'<ol class="steps dg-steps">{steps}</ol>{more}</section>')
    gl = url_path('안내', kind)
    body = f"""<section class="hero"><h1>{E(D['title'])}</h1><p class="lead">{E(D['lead'])}</p></section>
<div class="warn">{E(D['danger'])}</div>
{slot_fig(kind, 'warn', 'diag')}
<section class="card"><h2>어떤 증상인가요?</h2><div class="dg-picks">{picks}</div></section>
<div class="dg-area">{blocks}</div>
<section class="card dg-done" hidden><h2>해결됐어요</h2><p>다행이에요. 같은 일이 또 생기면 이 페이지에서 다시 확인해 보세요.</p><p><a href="{E(url_path('연락처카드'))}">우리 집 비상 연락처 카드 만들어 두기</a></p></section>
<section class="card dg-call" data-kind="{E(kind)}"><h2>그래도 안 되면 업체를 부르세요</h2><p>여기까지 해 봤다고 말하면 기사님이 원인을 더 빨리 찾아요.</p><p class="dg-recent"></p><p><a class="btn" href="{E(gl)}">우리 동네 {E(G.get('name', ''))} 업체 찾기</a></p></section>
{extra_html('진단/' + kind)}
{slot_fig(kind, 'prevent', 'diag', '다음 겨울엔 이렇게 미리 챙겨요') if kind in PHOTO_SLOTS else photo_section(kind, G.get('name', '') + ' 현장은 이렇게 해요')}"""
    faqs = [[f'{s["label"]} 어떻게 하나요?', ' '.join(f'{i + 1}. {t}: {d}' for i, (t, d) in enumerate(s['steps']))] for s in D['symptoms']]
    return path, page(f"{D['title']} - 증상별로 집에서 먼저 확인할 것 | 내시간에", D['lead'], path, body,
                      [('홈', '/'), ('자가진단', url_path('진단')), (D['title'], path)], [faq_ld(faqs)])

def diag_index():
    path = url_path('진단')
    items = ''.join(f'<li><a href="{E(url_path("진단", k))}"><b>{E(D["title"])}</b></a><span>{E(", ".join(s["label"] for s in D["symptoms"][:3]))}</span></li>' for k, D in DIAG.items())
    body = f'<section class="hero"><h1>자가진단</h1><p class="lead">증상을 고르면 업체 부르기 전에 집에서 확인할 것을 하나씩 알려 드려요.</p></section><section class="card"><ul class="steps">{items}</ul></section>' + extra_html('진단') + mixed_photos('업체를 부르면 이렇게 해요', [('보일러-고장', 1), ('하수구-막힘', 1)])
    return path, page('자가진단 - 보일러·동파·하수구·누수·전기 | 내시간에', '증상을 고르면 집에서 먼저 확인할 것을 순서대로 알려 드려요.', path, body, [('홈', '/'), ('자가진단', path)])

def card_page(region_centers):
    path = url_path('연락처카드')
    regs = sorted(r for r in region_centers)
    gas = {r: v for r, v in CITYGAS['regions'].items()}
    data = json.dumps({'regs': regs, 'gas': gas, 'ctr': {r: [round(c[0], 3), round(c[1], 3)] for r, c in region_centers.items()}}, ensure_ascii=False)
    sidos = sorted({r.split(' ')[0] for r in regs})
    opts = ''.join(f'<option>{E(s)}</option>' for s in sidos)
    body = f"""<section class="hero"><h1>우리 집 비상 연락처 카드</h1><p class="lead">동네를 고르면 가스·수도·전기 문제 때 연락할 곳을 한 장으로 만들어 드려요. 휴대폰에 저장하거나 가족에게 보내 두세요.</p></section>
<section class="card"><h2>동네 고르기</h2><div class="cc-sel"><label>시·도<select id="cc-sido"><option value="">고르세요</option>{opts}</select></label><label>시·군·구<select id="cc-gu" disabled><option value="">먼저 시·도를 고르세요</option></select></label></div></section>
<section class="card cc-card" id="cc-card" hidden aria-live="polite"></section>
<section class="card"><h2>번호 안내</h2><ul class="plain"><li>도시가스 회사 번호는 한국도시가스협회 고객센터 찾기 자료예요. 동네 끝자락은 다를 수 있으니 가스 요금 고지서 번호가 가장 정확해요.</li><li>120은 서울·인천 등 지역 민원 콜센터 번호예요. 콜센터가 없는 시·군은 시·군청 상수도 담당 부서로 연락하세요.</li><li>정전은 한국전력 123, 불이 나거나 다친 사람이 있으면 119예요.</li></ul></section>
{extra_html('연락처카드')}
{mixed_photos('급할 때 이렇게 확인해요', [('전기-고장', 2), ('수도-동파', 2), ('보일러-고장', 2)])}
<script type="application/json" id="cc-data">{data}</script>"""
    return path, page('우리 집 비상 연락처 카드 - 가스·수도·전기 | 내시간에', '동네를 고르면 도시가스 회사, 수도 동파 신고, 정전 문의 번호를 한 장으로 만들어 저장·공유할 수 있어요.', path, body, [('홈', '/'), ('비상 연락처 카드', path)])

CENTERS = {}

def frost_box(region, region_centers=None):
    c = (region_centers or CENTERS).get(region)
    if not c:
        return ''
    return (f'<section class="card frost" data-lat="{c[0]:.3f}" data-lng="{c[1]:.3f}" data-gu="{E(gu_name(region))}">'
            f'<h2>{E(gu_name(region))} 오늘 밤 동파 위험</h2><p class="muted frost-wait">…</p>'
            f'<p class="source">예보: Open-Meteo(기상 모델 예보) · 단계별 행동요령: 서울시 상수도사업본부</p></section>')

CHECK = [
    ['수도', [['계량기함 안을 헌 옷으로 채우기', '헌 옷은 비닐로 한 번 싸서 넣어요. 젖으면 오히려 얼어요.'],
              ['계량기함 뚜껑을 비닐로 덮기', '틈으로 찬 바람이 들어오지 않게 해요.'],
              ['밖으로 드러난 수도관 보온재로 감싸기', '보일러 아래 배관도 함께 감싸요.'],
              ['물 잠그는 메인 밸브 위치 알아 두기', '배관이 터졌을 때 바로 잠글 수 있어요.']]],
    ['보일러', [['보일러 압력 확인 (1~1.5)', '1 아래면 설명서대로 물을 보충하거나 점검을 받아요.'],
                ['배기통(연통) 빠짐·찌그러짐 확인', '배기가 새면 일산화탄소 중독 위험이 있어요.'],
                ['보일러실 환기구 막지 않기', '춥다고 막으면 위험해요.'],
                ['외출 기능 쓰는 법 알아 두기', '며칠 비울 때도 전원 플러그와 가스 밸브는 그대로 둬요.']]],
    ['전기·가스', [['차단기함 위치 알아 두기', '정전 때 바로 확인할 수 있어요.'],
                  ['전기장판·난로 주변 정리', '이불·옷이 열선에 닿지 않게 해요.'],
                  ['가스 중간밸브 위치 알아 두기', '가스 냄새가 나면 바로 잠가요.']]],
    ['연락처', [['우리 집 비상 연락처 카드 만들기', '도시가스·수도·정전 번호를 한 장으로 저장해요.']]],
]

def checklist_page():
    path = url_path('정보', '겨울-집-점검')
    n = 0; secs = ''
    for h, items in CHECK:
        li = ''
        for t, d in items:
            n += 1
            li += f'<li><label class="ck"><input type="checkbox" data-k="c{n}"><span><b>{E(t)}</b><small>{E(d)}</small></span></label></li>'
        secs += f'<section class="card"><h2>{E(h)}</h2><ul class="cklist">{li}</ul></section>'
    body = f"""<section class="hero"><h1>겨울 집 점검 체크리스트</h1><p class="lead">한파 오기 전에 하나씩 체크해 보세요. 체크한 항목은 이 휴대폰에 기억돼서 다음에 들어와도 이어서 할 수 있어요.</p></section>
<div class="ck-bar card"><b class="ck-count">0 / {n}</b> 끝냈어요 <button type="button" class="btn ghost sm ck-reset">처음부터</button></div>
{secs}
{extra_html('정보/겨울-집-점검')}
{mixed_photos('겨울 점검, 이런 모습이에요', [('수도-동파', 2), ('보일러-고장', 1)])}
<section class="card"><h2>더 알아보기</h2><ul class="plain"><li><a href="{E(url_path('정보', '수도-계량기-동파'))}">수도 계량기 얼었을 때 녹이는 법</a></li><li><a href="{E(url_path('정보', '보일러-에러-숫자'))}">보일러 에러 숫자가 떴을 때</a></li><li><a href="{E(url_path('연락처카드'))}">우리 집 비상 연락처 카드</a></li></ul>
<p class="muted">서울시·인천시 상수도사업본부, 행정안전부 겨울철 안전 안내를 바탕으로 정리했어요.</p></section>"""
    return path, page('겨울 집 점검 체크리스트 - 수도·보일러·전기 | 내시간에', '한파 전에 수도 계량기, 보일러, 전기·가스를 하나씩 점검하는 체크리스트예요. 체크한 항목은 기억돼요.', path, body, [('홈', '/'), ('생활 정보', url_path('정보')), ('겨울 집 점검 체크리스트', path)])

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
    for g, reg, fpth in FOOD_PAGES:
        ctr = region_centers.get(reg, (0, 0))
        idx.append({'t': '음식점', 'n': f'{short_region(reg)} {FOOD[g]["name"]}', 's': '단체 예약·포장 전화', 'u': fpth,
                    'k': f'{FOOD[g]["name"]} 맛집 {reg}', 'lat': ctr[0], 'lng': ctr[1]})
    for sec, g, reg, dpth in DIR_PAGES:
        ctr = region_centers.get(reg, (0, 0)); gm = DIRM[sec]['groups'][g]
        idx.append({'t': DIRM[sec]['label'], 'n': f'{short_region(reg)} {gm["name"]}', 's': '전화·위치', 'u': dpth, 'k': f'{gm["name"]} {reg}', 'lat': ctr[0], 'lng': ctr[1]})
    live = {'자동차 정비': url_path('자동차정비')}
    for kind, g in guides:
        live.setdefault(GUIDES[kind]['tile'], url_path('안내', kind) if CFG.get('guides_all') else g)
    order = [GUIDES[k]['tile'] for k in GROUPS[0][1] if k in GUIDES] + ['자동차 정비']
    hot = [t for t in order if t in live]
    icons = {'보일러 고장': '♨', '수도 동파': '❄', '하수구 막힘': '⤓', '누수 탐지': '💧', '열쇠·도어락': '🔑', '정전·전기 고장': '⚡', '유리·창문 파손': '🪟', '정화조 청소': '🚽', '방역·해충': '🐜', '자동차 정비': '🚗'}
    hot_html = ''.join(f'<a class="hot" href="{E(live[t])}"><span class="ic" aria-hidden="true">{icons.get(t, "•")}</span><b>{E(t)}</b></a>' for t in hot)
    chips = ''.join(f'<button type="button" class="qchip" data-q="{E(t.split("·")[0].split()[0])}">{E(t)}</button>' for t in hot)
    groups = [
        ('집 수리·고장', ['정전·전기 고장', '유리·창문 파손', '에어컨 고장·청소', '수전·싱크대 교체', '옥상·외벽 방수', '정화조 청소']),
        ('청소·정리·방역', ['입주·이사청소', '줄눈·탄성코트', '유품정리·특수청소', '방역·해충', '비둘기·벌집']),
        ('상가·업소', ['사다리차', '셔터·자동문 수리', '업소용 냉장고', '간판 수리', '팝업 인테리어']),
    ]
    soon = ''.join(f'<p class="soon-row"><b>{E(n)}</b> {" · ".join(E(i) for i in items if i not in live)}</p>' for n, items in groups if any(i not in live for i in items))
    GI = {'에어컨-고장': '❄︎', '수전-교체': '🚰', '방수': '☂︎', '정화조-청소': '🚽', '입주청소': '🧽', '줄눈-탄성코트': '🧱', '유품정리': '📦',
          '방역-해충': '🐜', '비둘기-벌집': '🐦', '사다리차': '🪜', '셔터-자동문': '🚪', '업소용-냉장고': '🧊', '간판-수리': '💡', '팝업-인테리어': '🛋'}
    more = ''.join(f'<h3 class="sub">{E(n)}</h3><div class="hots">' + ''.join(f'<a class="hot" href="{E(live[GUIDES[k]["tile"]])}"><span class="ic" aria-hidden="true">{GI.get(k, "•")}</span><b>{E(GUIDES[k]["tile"])}</b></a>' for k in ks if k in GUIDES and GUIDES[k]['tile'] in live) + '</div>'
                   for n, ks in GROUPS[1:])
    if len(regions_count) <= 12:
        open_regions = ''.join(f'<a href="{E(url_path("자동차정비", slug_region(r)))}">{E(short_region(r))}</a>' for r in regions_count)
    else:
        sc = Counter(r.split()[0] for r in regions_count)
        open_regions = ''.join(f'<a href="{E(url_path("자동차정비"))}#{E(sd)}">{E(SIDO_SHORT.get(sd, sd))} <span class="muted">{n}개 지역</span></a>' for sd, n in sorted(sc.items(), key=lambda x: -x[1]))
    body = f'''<section class="hero home"><h1>내 시간에<br><span class="hl">예약방문, 전화</span>하세요</h1><p class="lead">출장 수리·자동차 정비부터 음식점 단체 예약, 병원·세무·법률 사무소까지 동네 업체를 모았어요. 원하는 시간에 맞춰 예약하고 방문하거나, 지금 바로 전화하세요.</p></section>
<section class="card find"><h2>무엇이 필요하세요?</h2>
<label class="search"><span class="sr">업종이나 동네 검색</span><input id="q" type="search" placeholder="예: 보일러, 하수구, 연수구 정비" autocomplete="off"></label>
<button type="button" id="near" class="btn ghost wide">내 위치에서 가까운 곳</button>
<div id="results" class="results" aria-live="polite"></div></section>
<section class="card recent" hidden><h2>최근 본 페이지</h2><ul class="plain recent-list"></ul></section>
<section class="card"><h2>지금 바로 찾을 수 있어요</h2><div class="hots">{hot_html}</div></section>
<section class="card"><h2>업체 부르기 전에</h2><div class="toolz">
<a href="{E(url_path('진단'))}"><b>자가진단</b><span>증상 고르면 할 일 안내</span></a>
<a href="{E(url_path('연락처카드'))}"><b>비상 연락처 카드</b><span>가스·수도·전기 번호 한 장</span></a>
<a href="{E(url_path('정보', '겨울-집-점검'))}"><b>겨울 집 점검</b><span>체크하면 기억돼요</span></a>
<a href="{E(url_path('정보'))}"><b>생활 정보</b><span>동파·보일러 에러</span></a>
</div></section>
{f'<section class="card req-cta"><h2>원하는 시간을 먼저 정하세요</h2><p>날짜·시간·예산을 정해 요청하면, 동네 업체 사장님이 가능한 시간과 가격으로 답해요.</p><a class="btn blue wide" href="{E(url_path(chr(50836)+chr(52397)))}">시간 정해 예약 요청하기</a></section>' if LIVE else f'<section class="card"><a class="v-home" href="{E(url_path(chr(47568)+chr(47196)+chr(45)+chr(52286)+chr(44592)))}"><span class="v-mi" aria-hidden="true">🎤</span><span><b>말로 찾기</b><span>"보일러 고장, 송도동 가까운 데" 말하면 바로 전화 연결</span></span></a></section><section class="card"><h2>우리 아파트 수리 안내</h2><p>개별난방인지 지역난방인지, 지은 지 몇 년인지에 따라 고장 났을 때 먼저 연락할 곳이 달라요.</p><a class="btn blue wide" href="{E(url_path(chr(50500)+chr(54028)+chr(53944)))}">동네 아파트 찾기</a></section>'}
<section class="card"><h2>열린 동네</h2><div class="links">{open_regions}</div><p class="muted">동네와 업종은 차례로 늘어나요.</p></section>
{('<section class="card"><h2>음식점 단체 예약·포장</h2><div class="hots">' + ''.join(f'<a class="hot" href="{E(url_path("음식점", g))}"><span class="ic" aria-hidden="true">{M["icon"]}</span><b>{E(M["name"])}</b></a>' for g, M in FOOD.items()) + '</div></section>') if FOOD_PAGES else ''}
<section class="card"><h2>집 수리·청소·상가 업종</h2>{more}</section>
{''.join(f'<section class="card"><h2>{E(S["label"])}</h2><div class="hots">' + ''.join(f'<a class="hot" href="{E(url_path(sec, g))}"><span class="ic" aria-hidden="true">{gm["icon"]}</span><b>{E(gm["name"])}</b></a>' for g, gm in S['groups'].items()) + '</div></section>' for sec, S in DIRM.items()) if DIR_PAGES else ''}
{f'<section class="card"><h2>곧 열려요</h2>{soon}</section>' if soon else ''}
{owner_cta('동네 업체')}
<script type="application/json" id="regions" data-src="/search.json">[]</script>'''
    open(os.path.join(OUT, 'search.json'), 'w', encoding='utf-8').write(json.dumps(idx, ensure_ascii=False, separators=(',', ':')))
    ld = [{'@context': 'https://schema.org', '@type': 'WebSite', 'name': '내시간에', 'url': BASE + '/'}]
    return '/', page('내시간에 - 내 시간에 예약방문, 전화하세요 | 동네 정비소·출장 업체', '내 시간에 예약방문, 전화하세요. 보일러·하수구·누수·열쇠 같은 출장 수리와 자동차 정비소를 동네별로 찾고, 원하는 시간에 맞춰 예약하세요.', '/', body, None, ld)

# ---------------------------------------------------------------- write

def load_apts():
    fp = os.path.join(ROOT, 'data', 'apartments.json')
    if not os.path.exists(fp):
        return {}, ''
    d = json.load(open(fp, encoding='utf-8'))
    return d.get('regions', {}), d.get('_date', '')

def apt_section(kind, gu, apts, apt_date):
    """K-apt 단지 정보로 지역마다 다른 안내 문단을 만들어요."""
    if not apts:
        return ''
    n = len(apts)
    yr = TODAY.year
    name = lambda a: f'{a[0]}({a[1]})' if a[1] else a[0]
    ex = lambda lst, k=3: ', '.join(E(name(a)) for a in lst[:k])
    old = [a for a in apts if a[2] and yr - a[2] >= 30]
    corridor = [a for a in apts if a[5] == '복도식']
    indiv = [a for a in apts if a[4].startswith('개별')]
    central = [a for a in apts if a[4] in ('지역난방', '중앙난방')]
    dis = [a[6] for a in apts if a[6]]
    p = []
    if kind == '보일러-고장' and SLIM_NOW[0]:
        pass
    elif kind == '보일러-고장':
        p.append(f'{E(gu)} 아파트 {n}곳 중 <b>개별난방 {len(indiv)}곳</b>, <b>지역·중앙난방 {len(central)}곳</b>이에요.')
        if central:
            p.append(f'지역·중앙난방 단지({ex(central)} 등)는 집에 보일러가 없어서, 난방이 안 되면 업체보다 <b>관리사무소에 먼저</b> 연락해요.')
        if indiv:
            p.append(f'개별난방 단지({ex(indiv)} 등)는 보일러가 집마다 있어서 고장 나면 직접 업체를 불러요.')
    elif kind == '수도-동파':
        if corridor:
            p.append(f'{E(gu)} 아파트 {n}곳 중 <b>복도식 단지가 {len(corridor)}곳</b>이에요({ex(corridor)} 등). 복도식은 계량기가 바깥 복도에 있어서 한파 때 특히 잘 얼어요. 한파 예보가 나오면 계량기 함부터 보온하세요.')
        else:
            p.append(f'{E(gu)} 아파트 {n}곳은 대부분 계단식이라 계량기가 집 안쪽이나 계단실에 있는 편이에요. 그래도 오래 집을 비울 땐 물을 가늘게 틀어 두세요.')
    elif kind in ('입주청소', '줄눈-탄성코트'):
        new = [a for a in apts if a[2] and yr - a[2] <= 2]
        if new:
            p.append(f'{E(gu)}에는 최근 2년 안에 입주를 시작한 단지가 <b>{len(new)}곳</b> 있어요({ex(new, 5)} 등). 새 단지는 입주 기간에 청소·시공 업체 출입을 관리사무소에 미리 신청해야 하는 경우가 많아요.')
        else:
            p.append(f'{E(gu)} 아파트 {n}곳 중 최근 2년 안에 입주를 시작한 단지는 없어요. 이사청소라면 오래 산 집의 기름때·물때 제거를 중심으로 범위를 정하세요.')
    elif kind == '사다리차':
        p.append(f'{E(gu)}에는 관리사무소가 있는 아파트 단지가 {n}곳 있어요. {ex(apts)} 같은 큰 단지는 이사 날짜와 사다리차 작업을 관리사무소에 미리 알려야 하는 경우가 많아요.')
    elif kind == '비둘기-벌집':
        p.append(f'{E(gu)} 아파트 {n}곳에 사신다면, 단지 전체에 비둘기가 많을 땐 관리사무소에 단지 차원의 퇴치를 요청하고, 우리 집 실외기·베란다만 업체에 맡기면 돼요.')
    elif kind in ('누수-탐지', '하수구-막힘', '전기-고장', '유리-파손', '수전-교체', '방수'):
        what = {'누수-탐지': '배관이 낡아 물이 새기 쉬워요. 아래층으로 물이 샌다면 관리사무소에 먼저 알리세요',
                '하수구-막힘': '공용 배수관이 막히는 일이 잦아요. 여러 집이 같이 막혔다면 관리사무소에 먼저 알리세요',
                '전기-고장': '배선과 차단기 용량이 요즘 가전에 비해 작을 수 있어요. 차단기가 자주 내려가면 점검을 받아 보세요',
                '유리-파손': '창틀이 낡아 유리만 바꾸기 어려운 경우도 있어요. 창틀 상태도 함께 봐 달라고 하세요',
                '수전-교체': '배관과 밸브가 낡아 잠가도 물이 새는 경우가 있어요. 밸브가 안 잠기면 관리사무소에 세대 밸브 위치를 물어보세요',
                '방수': '옥상·외벽 방수가 낡았을 수 있어요. 아파트 옥상·외벽은 공용 부분이라 관리사무소에 먼저 알리세요'}[kind]
        if old:
            p.append(f'{E(gu)} 아파트 {n}곳 중 <b>{len(old)}곳이 지은 지 30년 넘은 단지</b>예요({ex(sorted(old, key=lambda a: a[2]))} 등). 오래된 단지는 {what}.')
        else:
            newest = sum(1 for a in apts if a[2] and yr - a[2] < 10)
            p.append(f'{E(gu)} 아파트 {n}곳은 지은 지 30년 넘은 곳이 없고, 10년 안 된 단지가 {newest}곳이에요. 새 단지는 하자보수 기간이 남아 있을 수 있으니 업체 부르기 전에 관리사무소에 먼저 물어보세요.')
    elif kind == '정화조-청소':
        p.append(f'{E(gu)}에서 관리사무소가 있는 아파트 단지는 {n}곳이에요({ex(apts)} 등). 이런 단지는 관리사무소가 정화조를 맡아요. 단독주택·빌라·상가 건물은 건물주가 직접 청소를 맡겨야 해요.')
    elif kind == '방역-해충':
        if dis:
            avg = round(sum(dis) / len(dis))
            p.append(f'{E(gu)} 아파트 단지는 1년에 평균 <b>{avg}번</b> 단지 소독을 해요. 소독 날짜는 관리사무소 공지를 확인하고, 그 사이에 계속 나오면 집 안만 따로 방역을 맡기면 돼요.')
    elif kind == '열쇠-도어락':
        p.append(f'{E(gu)} 아파트 {n}곳에 사신다면, 공동현관 비밀번호나 출입카드 문제는 관리사무소가 해결해 줘요. 집 현관 도어락이 안 열릴 때만 열쇠 업체를 부르면 돼요.')
    if not p:
        return ''
    big = ' · '.join(E(name(a)) for a in apts[:12])
    return (f'<section class="card"><h2>{E(gu)} 아파트로 보면</h2><p>{" ".join(p)}</p>'
            f'<p class="muted">{E(gu)}의 큰 단지: {big}</p>'
            f'<p class="source">아파트 정보: 국토교통부 공동주택관리정보시스템(K-apt) 관리비 공개 단지 기준{(", " + apt_date[:4] + "." + apt_date[4:6] + "." + apt_date[6:]) if apt_date else ""}</p></section>')

# ---------------------------------------------------------------- 아파트: 동(洞)별 단지 안내 페이지

APT_MIN_N = 5  # 관리비 공개 단지가 3곳 이상인 동만 페이지를 만들어요
APT_KINDS = ['보일러-고장', '하수구-막힘', '누수-탐지', '전기-고장', '열쇠-도어락', '수도-동파']

def apt_slug(name):
    t = re.sub(r'[^\w가-힣]+', '-', name).strip('-')
    return t or 'apt'

def apt_paths(apts):
    """(지역, 동) → 페이지 주소."""
    out = {}
    for reg, L in apts.items():
        c = Counter(a[1] for a in L if a[1] and a[2])
        for d, n in c.items():
            if n >= APT_MIN_N:
                out[(reg, d)] = url_path('아파트', slug_region(reg), apt_slug(d))
    return out

def apt_names(L, k=4):
    t = ', '.join(E(a[0]) for a in L[:k])
    return t + (f' 등 {len(L)}곳' if len(L) > k else '')

def apt_dong_page(region, dong, L, ctx):
    gu = gu_name(region); yr = TODAY.year
    A = sorted([a for a in L if a[1] == dong and a[2]], key=lambda a: (a[2], a[0]))
    G_all = [a for a in L if a[2]]
    n = len(A); hh = sum(a[3] or 0 for a in A)
    old, new = A[0], A[-1]
    big = max(A, key=lambda a: a[3] or 0)
    avg = round(sum(a[2] for a in A) / n); gavg = round(sum(a[2] for a in G_all) / len(G_all))
    indiv = [a for a in A if (a[4] or '').startswith('개별')]
    dist = [a for a in A if (a[4] or '').startswith('지역')]
    cent = [a for a in A if (a[4] or '').startswith('중앙')]
    corr = [a for a in A if a[5] == '복도식']
    o30 = [a for a in A if yr - a[2] >= 30]
    rows = ''.join(f'<tr id="a{i}"><td>{E(a[0])}</td><td class="nw">{a[2]}<br><small>{yr - a[2]}년차{f" · {a[6]}개 동" if a[6] else ""}</small></td><td class="nw">{(f"{a[3]:,}" if a[3] else "")}<br><small>{E((a[4] or "").replace("난방", ""))}</small></td></tr>' for i, a in enumerate(A))
    cmp = f'{gu} 평균({gavg}년)보다 {abs(gavg - avg)}년 {"먼저" if avg < gavg else "늦게"}' if avg != gavg else f'{gu} 평균({gavg}년)과 같은 해'
    lead = (f'{E(gu)} {E(dong)}에서 관리비를 공개하는 아파트는 {n}곳, 모두 {hh:,}세대예요. 가장 오래된 곳은 {E(old[0])}({old[2]}년), '
            f'가장 새 곳은 {E(new[0])}({new[2]}년)이고, 가장 큰 단지는 {E(big[0])}({(big[3] or 0):,}세대)예요.')
    # 난방별 연락처
    heat = []
    if indiv:
        gl = CITYGAS['regions'].get(region) or []
        gas = ''.join(f'<tr><td>{E(c)}</td><td><a href="tel:{E(p.replace("-", ""))}">{E(p)}</a></td></tr>' for c, p in gl)
        heat.append(f'<h3 class="sub">개별난방 {len(indiv)}곳</h3><p>{apt_names(indiv)}: 보일러 업체에 직접, 가스 문제면 도시가스 회사로.</p>'
                    + (f'<div class="tbl"><table><thead><tr><th scope="col">{E(gu)} 도시가스</th><th scope="col">고객센터</th></tr></thead><tbody>{gas}</tbody></table></div>' if gas else ''))
    if dist:
        heat.append(f'<h3 class="sub">지역난방 {len(dist)}곳</h3><p>{apt_names(dist)}: 집에 보일러가 없어 관리사무소가 먼저예요.</p>')
    if cent:
        heat.append(f'<h3 class="sub">중앙난방 {len(cent)}곳</h3><p>{apt_names(cent)}: 난방 시간·온도를 관리사무소가 정해요.</p>')
    # 나이
    bands = [(0, 10, '10년 미만'), (10, 20, '10~19년'), (20, 30, '20~29년'), (30, 200, '30년 이상')]
    bl = [(lab, [a for a in A if lo <= yr - a[2] < hi]) for lo, hi, lab in bands]
    brow = ''.join(f'<tr><td>{lab}</td><td>{len(x)}곳</td><td>{apt_names(x, 3) if x else "-"}</td></tr>' for lab, x in bl)
    age_txt = []
    if o30:
        age_txt.append(f'30년 넘은 {apt_names(o30, 3)}: 동파·녹물·아래층 누수를 함께 조심하세요.')
    mid = [a for a in A if 10 <= yr - a[2] < 30]
    if mid:
        age_txt.append(f'{min(yr - a[2] for a in mid)}~{max(yr - a[2] for a in mid)}년 된 {len(mid)}곳은 보일러 교체와 배관 막힘이 잦은 나이예요.')
    yng = [a for a in A if yr - a[2] < 10]
    if yng:
        age_txt.append(f'{min(a[2] for a in yng)}년 이후 지은 {len(yng)}곳은 하자보수 대상인지 먼저 확인하세요.')
    # 동파
    frost = (f'복도식 {len(corr)}곳({apt_names(corr, 3)})은 계량기가 바깥 복도에 있어 한파 전에 보온하세요.'
             if corr else f'{E(dong)} {n}곳 모두 계단식·혼합식이라 계량기가 덜 얼어요.')
    # 단지별 한 줄
    def one(a):
        h = a[4] or ''
        who = '보일러 업체' if h.startswith('개별') else ('관리사무소' if h else '관리사무소나 업체')
        m = {'복도식': '계량기 바깥 복도', '계단식': '계량기 계단실·집 안', '혼합식': '동마다 계량기 위치 다름'}.get(a[5] or '', '')
        ag = yr - a[2]
        tip = '하자보수 확인' if ag < 10 else ('보일러·배관 점검' if ag < 20 else ('세대 배관·전기 점검' if ag < 30 else '공용 배관 공사 계획 확인'))
        return f'<li><b>{E(a[0])}</b> — {a[2]}년 · {(a[3] or 0):,}세대{f" · {a[6]}개 동" if a[6] else ""}. 난방이 안 되면 {who}. {m + ". " if m else ""}{ag}년차라 {tip}.</li>'
    ones = '<ul class="plain">' + ''.join(one(a) for a in sorted(A, key=lambda a: -(a[3] or 0))) + '</ul>'
    pc = lambda X, T: round(len(X) / len(T) * 100) if T else 0
    g_ind = [a for a in G_all if (a[4] or '').startswith('개별')]; g_cor = [a for a in G_all if a[5] == '복도식']; g_o30 = [a for a in G_all if yr - a[2] >= 30]
    g_hh = round(sum(a[3] or 0 for a in G_all) / len(G_all)); d_hh = round(hh / n)
    stat = (f'<div class="tbl apt"><table><thead><tr><th scope="col">항목</th><th scope="col">{E(dong)}</th><th scope="col">{E(gu.split()[-1])}</th></tr></thead><tbody>'
            f'<tr><td>단지 수</td><td class="nw">{n}곳</td><td class="nw">{len(G_all)}곳</td></tr>'
            f'<tr><td>평균 사용승인</td><td class="nw">{avg}년</td><td class="nw">{gavg}년</td></tr>'
            f'<tr><td>단지당 평균 세대 수</td><td class="nw">{d_hh:,}</td><td class="nw">{g_hh:,}</td></tr>'
            f'<tr><td>개별난방 비율</td><td>{pc(indiv, A)}%</td><td>{pc(g_ind, G_all)}%</td></tr>'
            f'<tr><td>복도식 비율</td><td>{pc(corr, A)}%</td><td>{pc(g_cor, G_all)}%</td></tr>'
            f'<tr><td>30년 넘은 단지</td><td>{pc(o30, A)}%</td><td>{pc(g_o30, G_all)}%</td></tr>'
            '</tbody></table></div>')
    # 업체
    blocks = []
    kinds = [k for k in APT_KINDS if not (k == '보일러-고장' and not indiv)]
    for k in kinds:
        st = ctx['stores'].get(k, {}).get(region, [])
        here = [r for r in st if r[2] == dong][:3]
        if not here:
            continue
        Gk = GUIDES[k]
        cards = ''.join(store_card(r, i, Gk['name'], region) for i, r in enumerate(here))
        blocks.append(f'<h3 class="sub">{E(Gk["name"])}</h3><div class="shops">{cards}</div>'
                      f'<p class="muted"><a href="{E(url_path("안내", k, region.replace(" ", "-")))}">{E(gu)} {E(Gk["name"])} {len(st)}곳 모두 보기</a></p>')
    shops = (f'<section class="card"><h2>{E(dong)}에 있는 수리 업체</h2>{"".join(blocks)}<p class="source">소상공인시장진흥공단 상가정보</p></section>') if blocks else ''
    # 이웃 동
    near = ctx['near_dongs']
    ix = next((i for i, (d, _) in enumerate(near) if d == dong), 0)
    ring = [near[(ix + j) % len(near)] for j in range(1, min(7, len(near)))]
    nl = ''.join(f'<a href="{E(ctx["paths"][(region, d)])}">{E(d)} <small>{c}곳</small></a>' for d, c in ring if d != dong)
    faqs = [(f'{dong}에서 가장 오래된 아파트는 어디예요?', f'{old[0]}{josa(old[0], "이에요", "예요")}. {old[2]}년 사용승인, 올해 {yr - old[2]}년차예요.'),
            (f'{dong} 아파트는 대부분 어떤 난방이에요?', f'{n}곳 중 개별난방 {len(indiv)}곳, 지역난방 {len(dist)}곳, 중앙난방 {len(cent)}곳이에요.'),
            (f'{dong}에서 가장 큰 아파트는 어디예요?', f'{big[0]}, {(big[3] or 0):,}세대예요.')]
    ad = ctx['apt_date']
    body = (f'<section class="hero"><h1>{E(dong)} 아파트 {n}곳<br><small>단지별 고장·수리 안내</small></h1><p class="lead">{lead}</p></section>'
            f'<section class="card"><h2>{E(dong)} 아파트 목록</h2><div class="tbl apt"><table><thead><tr><th scope="col">단지</th><th scope="col">사용승인</th><th scope="col">세대</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p>{E(dong)} 단지의 평균 사용승인 연도는 {avg}년으로 {cmp}에 지었어요.</p><p class="source">출처: 공동주택관리정보시스템(K-apt) 관리비 공개 단지 ({E(ad[:4])}.{E(ad[4:6])})</p></section>'
            f'<section class="card"><h2>단지별 한 줄 안내</h2>{ones}</section>'
            f'<section class="card"><h2>{E(dong)}{josa(dong, "과", "와")} {E(gu)} 비교</h2>{stat}</section>'
            f'<section class="card"><h2>난방·온수가 안 될 때 먼저 연락할 곳</h2>{"".join(heat)}</section>'
            f'{shops}'
            f'<section class="card"><h2>단지 나이별로 챙길 것</h2><div class="tbl"><table><thead><tr><th scope="col">지은 지</th><th scope="col">단지 수</th><th scope="col">단지</th></tr></thead><tbody>{brow}</tbody></table></div><p>{" ".join(age_txt)}</p></section>'
            f'<section class="card"><h2>{E(dong)} 겨울철 수도 계량기</h2><p>{frost}</p></section>'
            f'{faq_html(faqs)}'
            + (f'<section class="card"><h2>{E(gu)} 다른 동 아파트</h2><div class="links">{nl}</div></section>' if nl else '')
            )
    path = ctx['paths'][(region, dong)]
    title = f'{short_region(region)} {dong} 아파트 {n}곳 고장·수리 연락처 ({", ".join(a[0] for a in sorted(A, key=lambda a: -(a[3] or 0))[:2])}) | 내시간에'
    desc = f'{short_region(region)} {dong} 아파트 {n}곳({", ".join(a[0] for a in sorted(A, key=lambda a: -(a[3] or 0))[:3])} 등)의 사용승인 연도·세대 수·난방 방식과, 난방이 안 될 때 먼저 연락할 곳, {dong} 수리 업체.'
    crumbs = [('홈', '/'), ('아파트', url_path('아파트')), (f'{gu} 아파트', url_path('아파트', slug_region(region))), (dong, path)]
    return path, page(title, desc, path, body, crumbs, [faq_ld(faqs)])

def apt_overlap(items, lim=0.2):
    """아파트 동 페이지끼리 5어절 묶음이 lim 넘게 겹치면 그 페이지를 돌려줘요 (둘 중 짧은 쪽)."""
    def txt(h):
        m = re.search(r'<main.*?</main>', h, re.S); h = m.group(0) if m else h
        h = re.sub(r'<script.*?</script>', '', h, flags=re.S)
        return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h))).split()
    S = []; short = set()
    for p, h in items:
        w = txt(h); S.append((p, {' '.join(w[i:i + 5]) for i in range(len(w) - 4)}))
        if len(' '.join(w)) < 2000: short.add(p)  # 2,000자보다 짧은 페이지도 검색에서 빼요
    df = Counter(x for _, st in S for x in st)
    freq = {x: k for k, x in enumerate(x for x, n in df.items() if n > 150)}
    masks = [sum(1 << freq[x] for x in st if x in freq) for _, st in S]
    inv = defaultdict(list)
    for i, (_, st) in enumerate(S):
        for x in st:
            if x not in freq: inv[x].append(i)
    bad = set(short)
    for i, (p, st) in enumerate(S):
        c = Counter()
        for x in st:
            if x in freq: continue
            for j in inv[x]:
                if j != i: c[j] += 1
        mi = masks[i]
        for j in range(len(S)):
            if j == i: continue
            n2 = len(S[j][1])
            if len(st) > n2: continue  # 둘 중 짧은 쪽만 빼요
            k = c.get(j, 0) + bin(mi & masks[j]).count('1')
            if k / max(1, len(st)) > lim:
                bad.add(p); break
    return bad


def apt_region_page(region, L, paths):
    gu = gu_name(region)
    L = sorted([a for a in L if a[2]], key=lambda a: -(a[3] or 0))
    def cell(a):
        k = (region, a[1])
        return f'<a href="{E(paths[k])}">{E(a[0])}</a>' if k in paths else E(a[0])
    rows = ''.join(f'<tr><td>{cell(a)}<br><small>{E(a[1] or "")}</small></td><td class="nw">{a[2]}</td><td class="nw">{(f"{a[3]:,}" if a[3] else "")}<br><small>{E((a[4] or "").replace("난방", ""))}</small></td></tr>' for a in L[:300])
    ds = sorted(((d, c) for (r, d), _ in paths.items() if r == region for c in [sum(1 for a in L if a[1] == d)]), key=lambda x: -x[1])
    dl = ''.join(f'<a href="{E(paths[(region, d)])}">{E(d)} <small>{c}곳</small></a>' for d, c in ds)
    body = (f'<section class="hero"><h1>{E(gu)} 아파트 단지별 수리 안내</h1><p class="lead">{E(gu)}에서 관리비를 공개하는 아파트 {len(L)}곳이에요. 동을 고르면 그 동 단지들의 난방 방식에 맞는 연락처와 단지 나이에 맞는 점검, 동네 수리 업체를 볼 수 있어요.</p></section>'
            + (f'<section class="card"><h2>동 고르기</h2><div class="links">{dl}</div></section>' if dl else '')
            + f'<section class="card"><h2>{E(gu)} 아파트 (세대 수 많은 순)</h2><div class="tbl apt"><table><thead><tr><th scope="col">단지</th><th scope="col">사용승인</th><th scope="col">세대</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<p class="source">출처: 공동주택관리정보시스템(K-apt)</p></section>')
    path = url_path('아파트', slug_region(region))
    crumbs = [('홈', '/'), ('아파트', url_path('아파트')), (f'{gu} 아파트', path)]
    return path, page(f'{short_region(region)} 아파트 단지별 고장·수리 안내 | 내시간에', f'{short_region(region)} 아파트 {len(L)}곳의 사용승인 연도·세대 수·난방 방식과 동별 수리 연락처 안내.', path, body, crumbs, noindex=not ds), len(ds)

def apt_home(regs):
    by = defaultdict(list)
    for r, n in regs:
        by[r.split()[0]].append((r, n))
    blocks = ''.join(f'<h3 class="sub">{E(SIDO_SHORT.get(s, s))}</h3><div class="links">' + ''.join(f'<a href="{E(url_path("아파트", slug_region(r)))}">{E(gu_name(r))} <small>{n}</small></a>' for r, n in sorted(L)) + '</div>' for s, L in by.items())
    body = ('<section class="hero"><h1>아파트 단지별 수리 안내</h1><p class="lead">우리 단지가 개별난방인지 지역난방인지, 지은 지 몇 년인지에 따라 고장 났을 때 먼저 연락할 곳이 달라요. 시·군·구를 고르면 동별 안내를 볼 수 있어요.</p></section>'
            f'<section class="card"><h2>지역 고르기</h2>{blocks}<p class="muted">숫자는 안내 페이지가 있는 동 수예요.</p></section>')
    return url_path('아파트'), page('아파트 단지별 고장·수리 안내 | 내시간에', '전국 아파트 단지의 난방 방식·지은 해에 맞춘 고장 연락처와 점검을 동별로 안내해요.', url_path('아파트'), body, [('홈', '/'), ('아파트', url_path('아파트'))])


def voice_page(regions):
    R = [[r, gu_name(r), SIDO_SHORT.get(r.split()[0], r.split()[0])] for r in sorted(regions)]
    ex = ['보일러에 E03 떠요 연수구 송도동 오늘 오후 4시', '싱크대 막혔어 수원시 영통구 지금 전화해 줘', '현관 도어락이 안 열려요 강남구 역삼동',
          '아이가 열이 나요 근처 소아과 마포구', '내일 오전 10시 콜택시 해운대구', '지하철에서 지갑 잃어버렸어', '이번 주말 미술관 종로구', '회식 10명 단체 예약 성동구 성수동']
    chips = ''.join(f'<button type="button" class="v-ex" data-ex="{E(x)}">{E(x)}</button>' for x in ex)
    faqs = [('정말 전화가 자동으로 걸리나요?', '목록에서 \'전화\'를 누르면 휴대폰 전화 앱이 열려요. 통화를 마치고 이 화면으로 돌아오면 \'연결됐어요\' 또는 \'안 받아요\'를 고를 수 있어요. \'안 받으면 다음 곳으로 바로 넘어가기\'를 켜 두면, 6초 뒤 다음 곳 전화로 넘어가요. 휴대폰에 따라 전화를 거는 마지막 버튼은 직접 눌러야 할 수 있어요.'),
            ('내 위치를 가져가나요?', '아니요. GPS 위치는 쓰지 않아요. 말하거나 고른 동네 이름으로만 찾고, 마지막에 쓴 동네만 이 기기에 기억해 둬요.'),
            ('말한 내용은 어디로 가나요?', '말을 글자로 바꾸는 일은 휴대폰·브라우저의 음성 인식(구글·애플 등)이 해요. 내시간에 서버에는 말한 내용을 저장하지 않아요. 걱정되면 글로 적어서 찾아도 돼요.'),
            ('어떤 곳을 찾을 수 있나요?', '보일러·하수구·누수·전기·열쇠 같은 수리 업체부터 약국·병원·동물병원, 콜택시, 미술관·박물관·공연장, 식당 단체 예약까지 찾아요. 전화번호는 카카오 지도에 등록된 번호예요.')]
    body = (f'<section class="hero"><h1>말로 찾기<br><small>말하면 가까운 곳에 바로 전화</small></h1><p class="lead">"보일러 고장 났어, 송도동에서 가까운 데 불러 줘"처럼 말하면 업종·동네·시간을 알아듣고, 가까운 곳을 찾아 통화할 말까지 적어 드려요. 안 받으면 다음 곳으로 바로 넘어가요.</p></section>'
            f'<section class="card v-box" id="v-box"><button type="button" class="v-mic" id="v-mic" aria-label="눌러서 말하기"><span aria-hidden="true">🎤</span></button><p class="v-micl" id="v-micl">눌러서 말하기</p><p class="v-live" id="v-live" aria-live="polite"></p>'
            f'<form id="v-form" class="v-form"><input id="v-q" placeholder="글로 적어도 돼요" aria-label="찾을 내용" autocomplete="off"><button type="submit">찾기</button></form>'
            f'<div class="v-exs">{chips}</div></section>'
            f'<div class="v-after card" id="v-after" hidden role="dialog" aria-live="assertive"></div>'
            f'<section class="card" id="v-res"><div id="v-out" aria-live="polite"><p class="v-msg">위에서 말하거나 예시를 눌러 보세요.</p></div></section>'
            f'<div class="v-toast" id="v-toast" role="status"></div>'
            '<section class="card"><h2>이렇게 쓰세요</h2><ol class="steps"><li><b>무엇이, 어디서, 언제</b>를 한 번에 말해요. "연수구 송도동, 보일러 에러 E03, 오늘 오후 4시"처럼요.</li>'
            '<li>가까운 순서로 전화번호가 있는 곳을 최대 6곳 보여 줘요. 위에는 그대로 읽으면 되는 <b>통화 대본</b>이 나와요.</li>'
            '<li>끝에 <b>"전화해 줘"</b>나 <b>"연락해 줘"</b>까지 말하면 가장 가까운 곳의 전화 앱이 바로 열려요. 통화 버튼만 누르면 돼요.</li>'
            '<li><b>전화</b>를 눌러 통화하고 돌아오면, 연결됐는지 물어봐요. 안 받았으면 <b>다음 곳으로 바로</b> 넘어가요.</li></ol></section>'
            '<section class="card"><h2>이런 말을 알아들어요</h2><div class="tbl"><table><thead><tr><th scope="col">말하면</th><th scope="col">찾는 곳</th></tr></thead><tbody>'
            '<tr><td>보일러·온수·난방</td><td>보일러 수리</td></tr><tr><td>싱크대·변기·하수구 막혔어</td><td>하수구 막힘</td></tr><tr><td>물이 새요·아랫집</td><td>누수 탐지</td></tr>'
            '<tr><td>차단기·누전·정전</td><td>전기 공사</td></tr><tr><td>도어락·문이 안 열려</td><td>열쇠·도어락</td></tr><tr><td>타이어·배터리 방전·견인</td><td>긴급출동</td></tr>'
            '<tr><td>약국·병원·소아과·동물병원</td><td>문 연 곳 문의</td></tr><tr><td>콜택시·택시</td><td>콜택시</td></tr><tr><td>지갑·휴대폰 잃어버렸어</td><td>분실물센터 (+lost112 안내)</td></tr>'
            '<tr><td>미술관·박물관·공연</td><td>관람·예약 문의</td></tr><tr><td>회식·단체 예약·미용실</td><td>예약 전화</td></tr></tbody></table></div>'
            '<p class="muted">시간은 "지금", "오늘 오후 4시", "내일 오전 10시 반"처럼 말하면 대본에 들어가요. 에러 숫자(E03 등)도 알아들어요.</p></section>'
            + faq_html(faqs))
    path = url_path('말로-찾기')
    head = '<script>window.VOICE_REGIONS=' + json.dumps(R, ensure_ascii=False) + ';</script>'
    return path, page('말로 찾기 · 말하면 가까운 곳에 바로 전화 (보일러·약국·택시·미술관) | 내시간에',
                      '"보일러 고장 났어, 가까운 데 불러 줘"라고 말하면 가까운 업체를 찾아 전화 대본과 함께 바로 연결해요. 안 받으면 다음 곳으로 넘어가요. 위치(GPS) 없이 동네 이름으로 찾아요.',
                      path, body, [('홈', '/'), ('말로 찾기', path)], [faq_ld(faqs)], extra_head=head,
                      scripts=f'<script src="/voice.js?v={V("voice.js")}" defer></script>')


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
    CENTERS.update(centers)
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
    apts, apt_date = load_apts()
    sp = os.path.join(ROOT, 'data', 'stores.json')
    sdata = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'kinds': {}}
    extra = sorted(r for r in apts if r not in released and r.split()[0] in SIDO_SHORT and re.search(r'[시군구]$', r) and len(r.split()) >= 2)
    _all = [a[2] for L in apts.values() for a in L if a[2]]
    if _all:
        _c = Counter(min(max(y // 10 * 10, 1970), 2020) for y in _all)
        NATIONAL_DECADES.update({d: _c.get(d, 0) / len(_all) * 100 for d in range(1970, 2030, 10)})
        globals()['NATIONAL_OLD'] = round(sum(1 for y in _all if TODAY.year - y >= 30) / len(_all) * 100)
    gregs = (released + extra) if CFG.get('guides_all') else [g.split('/')[1].replace('-', ' ', 1) for g in CFG.get('released_guides', [])]
    gkinds = list(GUIDES) if CFG.get('guides_all') else list(dict.fromkeys(g.split('/')[0] for g in CFG.get('released_guides', [])))
    for reg in gregs:
        ss = by_region.get(reg, [])
        dc = Counter(s['dong'] for s in ss if s['dong'])
        me = centers.get(reg)
        near = [r for _, r in sorted((km(me, centers[r]), r) for r in gregs if r != reg and r in centers)[:6]] if me else []
        ap = apts.get(reg, [])
        dongs = [d for d, _ in dc.most_common()] or [d for d, _ in Counter(a[1] for a in ap if a[1]).most_common()]
        ctx = {'dongs': dongs, 'near': near, 'shops': len(ss) if reg in released else 0, 'apts': ap, 'apt_date': apt_date, 'center': centers.get(reg), 'store_date': sdata.get('_date', '')}
        for kind in gkinds:
            if kind in GUIDES:
                p, h = guide_page(kind, reg, {**ctx, 'stores': sdata['kinds'].get(kind, {}).get(reg, [])})
                write(p, h)
                if 'noindex' not in h: urls.append(p); guides.append((kind, p))
    apaths = apt_paths({r: L for r, L in apts.items() if r in gregs})
    areg = []; apt_out = []
    for reg in gregs:
        L = apts.get(reg, [])
        if not L: continue
        dc = Counter(a[1] for a in L if a[1] and a[2])
        nd = sorted(((d, c) for d, c in dc.items() if (reg, d) in apaths), key=lambda x: -x[1])
        actx = {'paths': apaths, 'apt_date': apt_date, 'stores': sdata['kinds'], 'near_dongs': nd[:40]}
        for d, _ in nd:
            p, h = apt_dong_page(reg, d, L, actx); apt_out.append((p, h))
        p, h, n = apt_region_page(reg, L, apaths); write(p, h)
        if n: urls.append(p); areg.append((reg, n))
    bad = apt_overlap(apt_out)
    for p, h in apt_out:
        if p in bad:
            h = h.replace('<meta name="viewport"', '<meta name="robots" content="noindex,follow"><meta name="viewport"', 1)
        else:
            urls.append(p)
        write(p, h)
    print(f'아파트 동 페이지 {len(apt_out)}쪽 중 짧거나 비슷한 글 20% 넘어 검색 제외 {len(bad)}쪽')
    p, h = apt_home(areg); write(p, h); urls.append(p)
    p, h = voice_page(gregs); write(p, h); urls.append(p)
    for kind in gkinds:
        if CFG.get('guides_all') and kind in GUIDES:
            p, h = guide_index(kind, gregs); write(p, h); urls.append(p)
    for slug, a in ARTICLES.items():
        p, h = article_page(slug, a); write(p, h); urls.append(p)
    p, h = article_index(); write(p, h); urls.append(p)
    for k, D in DIAG.items():
        p, h = diag_page(k, D); write(p, h); urls.append(p)
    p, h = diag_index(); write(p, h); urls.append(p)
    p, h = checklist_page(); write(p, h); urls.append(p)
    fp = os.path.join(ROOT, 'data', 'food.json')
    food = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) and FOOD else {'groups': {}}
    food_pages = []
    for g, regs in food['groups'].items():
        if g not in FOOD: continue
        for reg, entry in regs.items():
            if len(entry['list']) < 3: continue
            me = centers.get(reg)
            nearr = [r for _, r in sorted((km(me, centers[r]), r) for r in regs if r != reg and r in centers and len(regs[r]['list']) >= 3)[:6]] if me else []
            here = [k for k in food['groups'] if reg in food['groups'][k] and len(food['groups'][k][reg]['list']) >= 3]
            p, h = food_page(g, reg, entry, {'near': nearr, 'groups_here': here, 'date': food.get('_date', '')})
            write(p, h); urls.append(p); food_pages.append((g, reg, p))
        p, h = food_index(g, [r for r in regs if len(regs[r]['list']) >= 3]); write(p, h); urls.append(p)
    if FOOD and food['groups']:
        p, h = food_home(); write(p, h); urls.append(p)
    FOOD_PAGES[:] = food_pages
    dp = os.path.join(ROOT, 'data', 'dir.json')
    dird = json.load(open(dp, encoding='utf-8')) if os.path.exists(dp) and DIRM else {'sections': {}}
    dir_pages = []
    for sec, groups in dird['sections'].items():
        if sec not in DIRM: continue
        for g, regs in groups.items():
            if g not in DIRM[sec]['groups']: continue
            ok = [r for r in regs if len(regs[r]['list']) >= 2]
            for reg in ok:
                me = centers.get(reg)
                nearr = [r for _, r in sorted((km(me, centers[r]), r) for r in ok if r != reg and r in centers)[:6]] if me else []
                here = [k for k in groups if reg in groups[k] and len(groups[k][reg]['list']) >= 2]
                p, h = dir_page(sec, g, reg, regs[reg], {'near': nearr, 'here': here, 'date': dird.get('_date', '')})
                write(p, h); urls.append(p); dir_pages.append((sec, g, reg, p))
            p, h = dir_index(sec, g, ok); write(p, h); urls.append(p)
        p, h = dir_home(sec); write(p, h); urls.append(p)
    DIR_PAGES[:] = dir_pages
    rc = {r: len(by_region[r]) for r in released}
    p, h = trade_index(rc); write(p, h); urls.append(p)
    p, h = card_page(centers); write(p, h); urls.append(p)
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
