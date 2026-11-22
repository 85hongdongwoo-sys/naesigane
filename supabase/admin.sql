-- 운영자용 (Supabase SQL Editor에서 필요한 부분만 골라 Run)

-- 1) 가입 신청한 사장님 보기 (approved=false 인 곳이 확인 대기)
select created_at, biz_name, biz_no, owner_name, mobile, trade, region, approved from owners order by created_at desc;

-- 2) 사업자 확인이 끝나면 승인 (사업자번호를 넣어서 실행)
-- update owners set approved = true where biz_no = '1234567890';

-- 3) 문자 발송을 켜기 전: 새 요청을 사장님께 직접 알려 줄 링크 목록
--    (사장님 휴대폰으로 아래 링크를 문자로 보내 주세요)
select q.created_at, q.region, q.trade, o.biz_name, o.mobile,
       'https://naesigane.co.kr/답변/#' || r.token as 사장님_답변_링크
from replies r join requests q on q.id = r.request_id join owners o on o.id = r.owner_id
where r.answer is null and q.status = 'open' and q.expires_at > now()
order by q.created_at desc;

-- 4) 30일 지난 요청 지우기 (개인정보 보관 기간)
-- delete from requests where expires_at < now();
