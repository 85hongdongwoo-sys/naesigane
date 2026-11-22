-- 내시간에 데이터베이스 (Supabase SQL Editor에 통째로 붙여 넣고 Run)
-- 원칙: 손님·사장님 모두 로그인 없이 '비밀 링크(토큰)'로만 자기 요청/답변을 봐요.
-- 표(테이블)는 바깥에서 직접 읽을 수 없고, 아래 함수(rpc)로만 필요한 만큼 주고받아요.

create extension if not exists pgcrypto;

-- 사장님 가입 신청 (운영자가 사업자 확인 후 approved=true 로 바꿔요)
create table if not exists owners (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  biz_name text not null,
  biz_no text not null,               -- 사업자등록번호 (국세청 확인용)
  owner_name text,
  mobile text not null,               -- 알림 받을 휴대폰
  public_phone text,                  -- 손님에게 보일 번호
  trade text not null,                -- 업종
  region text not null,               -- 예: 인천광역시 연수구
  address text,
  price_note text,                    -- 대표 가격대 메모
  sms_consent boolean not null default false,
  approved boolean not null default false,
  token text not null default encode(gen_random_bytes(18), 'hex')  -- 사장님 관리 링크
);

-- 손님 요청
create table if not exists requests (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  trade text not null,
  job text,
  region text not null,
  summary text not null,              -- 시간·여유·2순위·예산 요약 (화면에서 만든 문장)
  when_json jsonb,                    -- 날짜·시간 슬롯 원본
  memo text,
  photos jsonb default '[]'::jsonb,   -- 작은 사진(data URL) 최대 3장
  skip_detail boolean default false,
  mobile text not null,
  consent boolean not null,
  status text not null default 'open',   -- open / chosen / closed
  chosen_owner uuid references owners(id),
  token text not null default encode(gen_random_bytes(18), 'hex'),
  expires_at timestamptz default now() + interval '30 days'
);

-- 요청이 간 업체별 답변 칸
create table if not exists replies (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references requests(id) on delete cascade,
  owner_id uuid not null references owners(id) on delete cascade,
  token text not null default encode(gen_random_bytes(18), 'hex'),  -- 사장님 답변 링크
  answer text,                        -- ok / other / no
  slot text,                          -- 가능한 시간
  price_min int, price_max int, labor_included boolean,
  note text,
  answered_at timestamptz,
  unique (request_id, owner_id)
);

-- 업체 후기 (확정된 요청의 손님만)
create table if not exists reviews (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  request_id uuid unique not null references requests(id) on delete cascade,
  owner_id uuid not null references owners(id) on delete cascade,
  stars int not null check (stars between 1 and 5),
  tags text[] default '{}',
  paid int,                           -- 실제 낸 금액 (평균 계산에만)
  body text,
  nick text,
  owner_reply text
);

alter table owners enable row level security;
alter table requests enable row level security;
alter table replies enable row level security;
alter table reviews enable row level security;
-- 정책을 하나도 만들지 않아 표 직접 접근은 모두 막혀요. 아래 함수만 열어요.

-- 1) 사장님 가입 신청
create or replace function apply_owner(p jsonb) returns text language plpgsql security definer set search_path = public as $$
declare t text;
begin
  if coalesce((p->>'sms_consent')::boolean,false) = false then raise exception '알림 문자 수신 동의가 필요해요'; end if;
  if (p->>'biz_no') !~ '^[0-9]{10}$' then raise exception '사업자등록번호 10자리를 확인해 주세요'; end if;
  insert into owners(biz_name,biz_no,owner_name,mobile,public_phone,trade,region,address,price_note,sms_consent)
  values (p->>'biz_name',p->>'biz_no',p->>'owner_name',p->>'mobile',p->>'public_phone',p->>'trade',p->>'region',p->>'address',p->>'price_note',true)
  returning token into t;
  return t;
end $$;

-- 2) 손님 요청 보내기: 같은 지역·업종의 승인된 업체에 답변 칸을 만들어요
create or replace function create_request(p jsonb) returns jsonb language plpgsql security definer set search_path = public as $$
declare r requests; n int;
begin
  if coalesce((p->>'consent')::boolean,false) = false then raise exception '동의가 필요해요'; end if;
  if jsonb_array_length(coalesce(p->'photos','[]'::jsonb)) > 3 then raise exception '사진은 3장까지예요'; end if;
  insert into requests(trade,job,region,summary,when_json,memo,photos,skip_detail,mobile,consent)
  values (p->>'trade',p->>'job',p->>'region',p->>'summary',p->'when',p->>'memo',coalesce(p->'photos','[]'::jsonb),coalesce((p->>'skip')::boolean,false),p->>'mobile',true)
  returning * into r;
  insert into replies(request_id, owner_id)
    select r.id, o.id from owners o where o.approved and o.trade = r.trade and o.region = r.region;
  get diagnostics n = row_count;
  return jsonb_build_object('token', r.token, 'sent', n);
end $$;

-- 3) 사장님: 답변 링크로 요청 보기
create or replace function get_reply(t text) returns jsonb language sql security definer set search_path = public as $$
  select jsonb_build_object('trade',q.trade,'job',q.job,'region',q.region,'summary',q.summary,'memo',q.memo,'photos',q.photos,
    'skip',q.skip_detail,'status',q.status,'answer',rp.answer,'slot',rp.slot,'price_min',rp.price_min,'price_max',rp.price_max,
    'labor',rp.labor_included,'note',rp.note,'chosen', q.chosen_owner = rp.owner_id,
    'mobile', case when q.chosen_owner = rp.owner_id then q.mobile else null end)
  from replies rp join requests q on q.id = rp.request_id where rp.token = t and q.expires_at > now();
$$;

-- 4) 사장님: 답하기 (가능 / 다른 시간 / 어려움)
create or replace function answer_reply(t text, p jsonb) returns boolean language plpgsql security definer set search_path = public as $$
begin
  if (p->>'answer') not in ('ok','other','no') then raise exception '답을 골라 주세요'; end if;
  update replies set answer=p->>'answer', slot=p->>'slot', price_min=nullif(p->>'price_min','')::int, price_max=nullif(p->>'price_max','')::int,
    labor_included=(p->>'labor')::boolean, note=left(p->>'note',200), answered_at=now()
  where token=t and request_id in (select id from requests where status='open' and expires_at > now());
  return found;
end $$;

-- 5) 손님: 내 요청과 답변 보기
create or replace function get_request(t text) returns jsonb language sql security definer set search_path = public as $$
  select jsonb_build_object('trade',q.trade,'job',q.job,'region',q.region,'summary',q.summary,'status',q.status,
    'sent',(select count(*) from replies where request_id=q.id),
    'reviewed', exists(select 1 from reviews where request_id=q.id),
    'replies', coalesce((select jsonb_agg(jsonb_build_object('id',o.id,'name',o.biz_name,'phone',o.public_phone,'answer',rp.answer,'slot',rp.slot,
        'price_min',rp.price_min,'price_max',rp.price_max,'labor',rp.labor_included,'note',rp.note,'chosen',q.chosen_owner=o.id,
        'stars',(select round(avg(stars)::numeric,1) from reviews where owner_id=o.id),'reviews',(select count(*) from reviews where owner_id=o.id))
        order by (rp.answer='ok') desc nulls last, rp.answered_at)
      from replies rp join owners o on o.id=rp.owner_id where rp.request_id=q.id and rp.answer is not null),'[]'::jsonb))
  from requests q where q.token = t;
$$;

-- 6) 손님: 업체 확정
create or replace function choose_owner(t text, oid uuid) returns boolean language plpgsql security definer set search_path = public as $$
begin
  update requests set chosen_owner=oid, status='chosen'
  where token=t and status='open' and exists(select 1 from replies where request_id=requests.id and owner_id=oid and answer in ('ok','other'));
  return found;
end $$;

-- 7) 손님: 후기 남기기 (확정된 요청만, 한 번만)
create or replace function write_review(t text, p jsonb) returns boolean language plpgsql security definer set search_path = public as $$
declare q requests;
begin
  select * into q from requests where token=t and status='chosen';
  if not found then raise exception '확정된 예약에만 후기를 남길 수 있어요'; end if;
  insert into reviews(request_id,owner_id,stars,tags,paid,body,nick)
  values (q.id,q.chosen_owner,(p->>'stars')::int,coalesce(array(select jsonb_array_elements_text(p->'tags')),'{}'),nullif(p->>'paid','')::int,left(p->>'body',200),
    left(regexp_replace(coalesce(p->>'nick','손님'),'(.).*','\1**'),4));
  return true;
end $$;

-- 8) 업체 후기 목록 (공개)
create or replace function owner_reviews(oid uuid) returns jsonb language sql security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object('stars',stars,'tags',tags,'body',body,'nick',nick,'date',to_char(created_at,'MM/DD'),'owner_reply',owner_reply) order by created_at desc),'[]'::jsonb)
  from reviews where owner_id = oid;
$$;

revoke all on function apply_owner, create_request, get_reply, answer_reply, get_request, choose_owner, write_review, owner_reviews from public;
grant execute on function apply_owner(jsonb), create_request(jsonb), get_reply(text), answer_reply(text, jsonb), get_request(text), choose_owner(text, uuid), write_review(text, jsonb), owner_reviews(uuid) to anon;
