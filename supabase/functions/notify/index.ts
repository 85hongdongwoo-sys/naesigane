// 내시간에 문자 알림 (Supabase Edge Function) — 문자 서비스(솔라피) 가입 후 켜요.
// 1) supabase secrets set SOLAPI_KEY=... SOLAPI_SECRET=... SMS_FROM=발신번호 SITE=https://naesigane.co.kr
// 2) supabase functions deploy notify
// 3) Database → Webhooks: replies 테이블 INSERT 와 requests 테이블 UPDATE 에 이 함수를 연결
// 4) config.json 의 sms_enabled 를 true 로 바꾸고 다시 배포
import { createClient } from "npm:@supabase/supabase-js@2";
import { createHmac, randomUUID } from "node:crypto";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const SITE = Deno.env.get("SITE") ?? "https://naesigane.co.kr";

async function sms(to: string, text: string) {
  const date = new Date().toISOString(), salt = randomUUID();
  const sig = createHmac("sha256", Deno.env.get("SOLAPI_SECRET")!).update(date + salt).digest("hex");
  const r = await fetch("https://api.solapi.com/messages/v4/send", {
    method: "POST",
    headers: { "Content-Type": "application/json",
      Authorization: `HMAC-SHA256 apiKey=${Deno.env.get("SOLAPI_KEY")}, date=${date}, salt=${salt}, signature=${sig}` },
    body: JSON.stringify({ message: { to, from: Deno.env.get("SMS_FROM"), text } }),
  });
  if (!r.ok) console.error("sms fail", await r.text());
}

Deno.serve(async (req) => {
  const { type, table, record, old_record } = await req.json();
  // 새 요청이 업체에 배정되면 → 사장님께 (요청 정보성 알림, 수신 동의한 가입 업체만)
  if (table === "replies" && type === "INSERT") {
    const { data: o } = await db.from("owners").select("mobile,sms_consent").eq("id", record.owner_id).single();
    const { data: q } = await db.from("requests").select("region,job,trade,summary").eq("id", record.request_id).single();
    if (o?.sms_consent && q) await sms(o.mobile, `[내시간에] 손님 요청: ${q.job ?? q.trade} · ${q.summary.slice(0, 40)}…\n답하기: ${SITE}/답변/#${record.token}`);
  }
  // 손님이 업체를 확정하면 → 사장님께
  if (table === "requests" && type === "UPDATE" && record.status === "chosen" && old_record?.status !== "chosen") {
    const { data: rp } = await db.from("replies").select("token, owners(mobile)").eq("request_id", record.id).eq("owner_id", record.chosen_owner).single();
    // @ts-ignore
    if (rp) await sms(rp.owners.mobile, `[내시간에] 손님이 사장님을 골랐어요. 손님 번호 확인: ${SITE}/답변/#${rp.token}`);
  }
  // 업체가 답하면 → 손님께
  if (table === "replies" && type === "UPDATE" && record.answer && !old_record?.answer) {
    const { data: q } = await db.from("requests").select("mobile,token").eq("id", record.request_id).single();
    if (q) await sms(q.mobile, `[내시간에] 업체 답이 왔어요. 확인: ${SITE}/내-요청/#${q.token}`);
  }
  return new Response("ok");
});
