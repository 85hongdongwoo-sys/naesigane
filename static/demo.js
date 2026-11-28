(function(){
  var el=document.getElementById('demo');if(!el)return;
  function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  var Q={trade:'자동차 정비',job:'엔진오일 교환 + 브레이크 소리 점검',region:'인천 연수구 송도동',want:'토요일 오전 10~12시',alt:'일요일 오후도 괜찮아요',budget:'10만 원 이하',memo:'아반떼 2019년식이에요. 브레이크 밟을 때 끽 소리가 나요.'};
  var D={answer:'ok',slot:'토요일 오전 10시 30분',min:60000,max:90000,labor:true,note:'엔진오일 교환은 30분이면 끝나요. 브레이크 패드는 보고 교체가 필요하면 먼저 말씀드릴게요.'};
  var step=0,sent=false,picked=false;
  function won(a,b){function f(n){return (n/10000).toFixed(n%10000?1:0).replace('.0','')+'만'}return f(a)+'~'+f(b)+' 원'}
  var steps=['손님이 요청','사장님 알림','추천 답변','손님이 비교'];
  function bar(){return '<ol class="dm-steps">'+steps.map(function(s,i){return '<li class="'+(i===step?'on':i<step?'done':'')+'"><button type="button" data-go="'+i+'"><b>'+(i+1)+'</b><span>'+s+'</span></button></li>'}).join('')+'</ol>'}
  function nav(next){return '<div class="actions">'+(step>0?'<button type="button" class="btn ghost" data-go="'+(step-1)+'">이전</button>':'')+(next?'<button type="button" class="btn blue" data-go="'+(step+1)+'">'+next+'</button>':'')+'</div>'}
  function sum(){return '<dl class="dm-sum"><dt>할 일</dt><dd>'+esc(Q.job)+'</dd><dt>원하는 시간</dt><dd>'+esc(Q.want)+' <small>('+esc(Q.alt)+')</small></dd><dt>예산</dt><dd>'+esc(Q.budget)+'</dd><dt>동네</dt><dd>'+esc(Q.region)+'</dd><dt>메모</dt><dd>'+esc(Q.memo)+'</dd></dl>'}
  function draw(){var h=bar();
    if(step===0){h+='<section class="card"><h2>1. 손님이 원하는 시간을 먼저 정해요</h2><p>손님은 전화 대신, 할 일·원하는 시간·예산을 골라 동네 업체 여러 곳에 한 번에 요청해요.</p>'+sum()+'<p class="muted">시연용 예시 요청이에요. 실제 손님 정보가 아니에요.</p>'+nav('사장님께 가는 알림 보기')+'</section>'}
    else if(step===1){h+='<section class="card"><h2>2. 사장님 휴대폰으로 알림이 와요</h2><p>앱을 깔 필요가 없어요. 문자(또는 카카오 알림톡) 한 통이 오고, 링크를 누르면 답변 화면이 열려요.</p><div class="dm-phone"><div class="dm-bubble"><b>[내시간에] 새 예약 요청</b><br>'+esc(Q.job)+'<br>'+esc(Q.want)+' · 예산 '+esc(Q.budget)+'<br>'+esc(Q.region)+'<br><u>답하기 ▸</u></div><small>오전 8:42</small></div>'+nav('답변 화면 열기')+'</section>'}
    else if(step===2){h+='<section class="card"><h2>3. 추천 답변이 미리 채워져 있어요</h2><p>요청 내용과 사장님이 등록해 둔 가격대·영업시간으로 답변 초안을 자동으로 만들어 둬요. 사장님은 확인하고 <b>보내기</b>만 누르면 돼요.</p>'+sum()+
      '<div class="dm-draft"><p class="dm-badge">추천 답변 초안</p>'+
      '<div class="seg" role="radiogroup">'+[['ok','가능'],['other','다른 시간'],['no','어려움']].map(function(a){return '<button type="button" class="opt'+(D.answer===a[0]?' on':'')+'" data-ans="'+a[0]+'">'+a[1]+'</button>'}).join('')+'</div>'+
      (D.answer!=='no'?'<label class="fld"><span>가능한 시간</span><input id="dm-slot" value="'+esc(D.slot)+'"></label><label class="fld"><span>예상 가격 (원)</span><span class="dm-two"><input id="dm-min" type="number" value="'+D.min+'"><input id="dm-max" type="number" value="'+D.max+'"></span></label><label class="agree"><input id="dm-labor" type="checkbox"'+(D.labor?' checked':'')+'><span>부품+공임 포함 가격이에요</span></label><label class="fld"><span>한마디</span><textarea id="dm-note" rows="3" maxlength="200">'+esc(D.note)+'</textarea></label>':'<p class="muted">"이번엔 어려워요"로 답하면 손님이 다른 업체를 고를 수 있게 바로 알려 드려요.</p>')+
      (sent?'<p class="ok"><b>보냈어요.</b> 손님 화면에 바로 나타나요.</p>':'<button type="button" class="btn blue wide" data-send="1">이대로 보내기</button>')+
      '</div>'+nav(sent?'손님 화면 보기':'')+'</section>'}
    else{var ours={name:'송도 바른정비 (시연)',ans:D.answer,slot:D.slot,p:D.answer==='no'?'':won(D.min,D.max),labor:D.labor,note:D.note};
      var L=[ours,{name:'연수 A정비 (예시)',ans:'other',slot:'토요일 오후 2시',p:'7~10만 원',labor:false,note:'오전은 예약이 차 있어요.'},{name:'B카센터 (예시)',ans:'ok',slot:'토요일 오전 11시',p:'8~12만 원',labor:true,note:''}];
      h+='<section class="card"><h2>4. 손님은 답을 비교해서 골라요</h2><p>여러 업체 답이 한 화면에 모여요. 손님이 확정하면 그때 사장님께 손님 번호가 전달돼요.</p></section>'+L.map(function(r,i){var tg=r.ans==='ok'?['원하신 시간 가능','ok']:r.ans==='other'?['다른 시간 제안','other']:['이번엔 어려워요','no'];
        return '<article class="shop'+(picked&&i===0?' chosen':'')+'"><div class="shop-head"><h3>'+esc(r.name)+'</h3><span class="tag '+tg[1]+'">'+tg[0]+'</span></div>'+(r.ans!=='no'?'<div class="two"><div><small>가능한 시간</small><b>'+esc(r.slot)+'</b></div><div><small>예상 가격</small><b>'+esc(r.p)+'</b>'+(r.labor?'<small class="ok">부품+공임 포함</small>':'')+'</div></div>'+(r.note?'<p>“'+esc(r.note)+'”</p>':''):'')+(i===0&&!picked&&r.ans!=='no'?'<div class="actions"><button type="button" class="btn blue" data-pick="1">이 업체로 확정</button></div>':'')+(picked&&i===0?'<p class="ok"><b>확정했어요.</b> 사장님께 손님 연락처가 전달돼요.</p>':'')+'</article>'}).join('')+
        '<section class="card"><h2>사장님이 하는 일은 딱 하나</h2><p>알림을 받고, 미리 채워진 답을 확인하고, 보내기. 전화를 못 받는 시간에 온 손님도 놓치지 않아요.</p><a class="btn dark wide" href="/사장님/">사장님 무료 등록 신청하기</a>'+nav('')+'</section>'}
    el.innerHTML=h}
  function keep(){var s=document.getElementById('dm-slot');if(s){D.slot=s.value;D.min=+document.getElementById('dm-min').value||0;D.max=+document.getElementById('dm-max').value||0;D.labor=document.getElementById('dm-labor').checked;D.note=document.getElementById('dm-note').value}}
  el.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;keep();
    if(b.dataset.go!=null){step=+b.dataset.go;draw();el.scrollIntoView({behavior:'smooth',block:'start'})}
    else if(b.dataset.ans){D.answer=b.dataset.ans;sent=false;draw()}
    else if(b.dataset.send){sent=true;draw()}
    else if(b.dataset.pick){picked=true;draw()}});
  draw();
})();
