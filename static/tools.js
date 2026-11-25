/* 내시간에 도구: 자가진단 · 비상 연락처 카드 · 동파 위험 · 점검 체크리스트 · 최근 본 페이지 */
(function(){
  'use strict';
  function $(s,r){return (r||document).querySelector(s)}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function load(k,d){try{var v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}}
  function save(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
  var path=decodeURIComponent(location.pathname);

  // ---- 최근 본 페이지 기록 (안내·정비소·음식점 등 동네 페이지)
  var seg=path.split('/').filter(Boolean);
  if(seg.length>=3&&/^(안내|자동차정비|음식점|병원|전문가)$/.test(seg[0])){
    var h1=$('h1'),t=h1?h1.textContent.replace(/\s+/g,' ').trim():document.title;
    var R=load('nsg_recent',[]).filter(function(x){return x.u!==location.pathname});
    R.unshift({u:location.pathname,t:t.slice(0,60)});save('nsg_recent',R.slice(0,5));
    if(seg[0]==='안내'&&seg[2]){var L=load('nsg_kind_region',{});L[seg[1]]={u:location.pathname,r:seg[2].replace(/-/g,' ')};save('nsg_kind_region',L)}
  }
  var rec=$('.recent');
  if(rec){var R2=load('nsg_recent',[]);if(R2.length){$('.recent-list',rec).innerHTML=R2.map(function(x){return '<li><a href="'+esc(x.u)+'">'+esc(x.t)+'</a></li>'}).join('');rec.hidden=false}}

  // ---- 자가진단: 증상 고르기 → 한 단계씩
  var picks=$$('.dg-pick');
  if(picks.length){
    document.documentElement.classList.add('dg-js');
    var syms=$$('.dg-sym'),done=$('.dg-done'),call=$('.dg-call');
    function show(id){
      syms.forEach(function(s){var on=s.dataset.s===id;s.hidden=!on;if(on){$$('.dg-step',s).forEach(function(li,i){li.hidden=i>0;li.classList.remove('dg-cur')});var f=$('.dg-step',s);if(f)f.classList.add('dg-cur')}});
      picks.forEach(function(b){b.classList.toggle('on',b.dataset.s===id);b.setAttribute('aria-pressed',b.dataset.s===id)});
      done.hidden=true;call.classList.remove('dg-hl');
      var s=$('#s-'+id);if(s)s.scrollIntoView({behavior:'smooth',block:'start'});
      if(typeof gtag==='function')try{gtag('event','diag_pick',{kind:call.dataset.kind,symptom:id})}catch(e){}
    }
    syms.forEach(function(s){s.hidden=true});
    picks.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.s)})});
    $$('.dg-ok').forEach(function(b){b.addEventListener('click',function(){done.hidden=false;done.scrollIntoView({behavior:'smooth',block:'center'})})});
    $$('.dg-no').forEach(function(b){b.addEventListener('click',function(){
      var li=b.closest('.dg-step');li.classList.remove('dg-cur');var nx=li.nextElementSibling;
      if(nx){nx.hidden=false;nx.classList.add('dg-cur');nx.scrollIntoView({behavior:'smooth',block:'center'})}
      else{call.classList.add('dg-hl');call.scrollIntoView({behavior:'smooth',block:'center'})}
    })});
    var KR=load('nsg_kind_region',{})[call.dataset.kind];
    if(KR)$('.dg-recent',call).innerHTML='<a class="btn dark" href="'+esc(KR.u)+'">최근 본 '+esc(KR.r)+' 업체 보기</a>';
  }

  // ---- 우리 집 비상 연락처 카드
  var ccData=$('#cc-data');
  if(ccData){
    var D=JSON.parse(ccData.textContent),sd=$('#cc-sido'),gu=$('#cc-gu'),box=$('#cc-card');
    function fillGu(s,keep){
      var L=D.regs.filter(function(r){return r.split(' ')[0]===s});
      gu.innerHTML='<option value="">고르세요</option>'+L.map(function(r){return '<option value="'+esc(r)+'">'+esc(r.split(' ').slice(1).join(' '))+'</option>'}).join('');
      gu.disabled=!L.length;if(keep)gu.value=keep;
    }
    function text(r){
      var g=D.gas[r],lines=['['+r+' 비상 연락처]'];
      if(g)g.forEach(function(x){lines.push('가스 냄새·가스 안 들어옴: '+x[0]+' '+x[1])});else lines.push('가스: LPG 판매점(가스통에 적힌 번호) 또는 고지서 번호');
      lines.push('수도 계량기 동파·깨짐: 120 또는 시·군청 상수도 담당','정전: 한국전력 123','불·응급: 119','- 내시간에 naesigane.co.kr');
      return lines.join('\n');
    }
    function render(r){
      if(!r){box.hidden=true;return}
      save('nsg_region',r);
      var g=D.gas[r],gu2=r.split(' ').slice(1).join(' ');
      var gas=g?g.map(function(x){return '<li><span>가스 냄새·가스 안 들어옴</span><b>'+esc(x[0])+'</b><a href="tel:'+esc(x[1].replace(/-/g,''))+'">'+esc(x[1])+'</a></li>'}).join('')
              :'<li><span>가스</span><b>LPG 판매점</b><em>가스통·계량기에 붙은 번호</em></li>';
      box.innerHTML='<h2>'+esc(gu2)+' 비상 연락처</h2><ul class="cc-list">'+gas+
        '<li><span>수도 계량기 동파·깨짐</span><b>지역 민원 콜센터</b><a href="tel:120">120</a></li>'+
        '<li><span>정전</span><b>한국전력</b><a href="tel:123">123</a></li>'+
        '<li><span>불·응급</span><b>소방</b><a href="tel:119">119</a></li></ul>'+
        '<div class="cc-act"><button type="button" class="btn" id="cc-share">가족에게 보내기</button><button type="button" class="btn ghost" id="cc-copy">글자로 복사</button><button type="button" class="btn ghost" id="cc-print">인쇄</button></div>'+
        '<p class="muted cc-msg" aria-live="polite"></p>';
      box.hidden=false;
      var msg=$('.cc-msg',box),T=text(r);
      $('#cc-share').onclick=function(){if(navigator.share){navigator.share({title:gu2+' 비상 연락처',text:T}).catch(function(){})}else{copy()}};
      function copy(){(navigator.clipboard?navigator.clipboard.writeText(T):Promise.reject()).then(function(){msg.textContent='복사했어요. 카톡이나 문자에 붙여 넣으세요.'},function(){msg.textContent='복사가 안 되는 브라우저예요. 화면을 캡처해 두세요.'})}
      $('#cc-copy').onclick=copy;$('#cc-print').onclick=function(){window.print()};
      if(typeof gtag==='function')try{gtag('event','contact_card',{region:r})}catch(e){}
    }
    sd.addEventListener('change',function(){fillGu(sd.value);render('')});
    gu.addEventListener('change',function(){render(gu.value)});
    var last=load('nsg_region','');
    if(last&&D.regs.indexOf(last)>-1){sd.value=last.split(' ')[0];fillGu(sd.value,last);render(last)}
  }

  // ---- 오늘 밤 동파 위험 (Open-Meteo 예보, 서울시 단계별 행동요령)
  $$('.frost').forEach(function(box){
    var u='https://api.open-meteo.com/v1/forecast?latitude='+box.dataset.lat+'&longitude='+box.dataset.lng+'&hourly=temperature_2m&timezone=Asia%2FSeoul&forecast_days=2';
    fetch(u).then(function(r){return r.json()}).then(function(j){
      var now=Date.now(),T=j.hourly.time,V=j.hourly.temperature_2m,min=99;
      for(var i=0;i<T.length;i++){var t=new Date(T[i]+':00+09:00').getTime();if(t>=now&&t<=now+24*3600e3&&V[i]<min)min=V[i]}
      if(min===99)throw 0;
      var m=Math.round(min),lv,act;
      if(m>-5){lv='낮음';act='동파 걱정은 크지 않아요. 계량기함과 밖으로 나온 수도관을 미리 보온해 두세요.'}
      else if(m>-10){lv='주의';act='계량기함과 밖으로 나온 수도관 보온 상태를 다시 살펴보세요.'}
      else if(m>-15){lv='경계';act='오래 집을 비운다면 집 안 수도꼭지를 조금 열어 물이 흐르게 하세요. 종이컵 하나가 33초쯤에 차는 정도면 돼요.'}
      else{lv='심각';act='잠깐 물을 안 쓸 때도 욕실 수도꼭지를 조금 열어 물이 흐르게 하세요.'}
      $('.frost-wait',box).outerHTML='<p class="frost-now"><span class="frost-t">'+(m<0?'영하 '+(-m):m)+'도</span><span class="frost-lv lv-'+lv+'">동파 '+lv+'</span></p><p>앞으로 24시간 '+esc(box.dataset.gu)+' 최저기온 예보예요. '+act+'</p><p><a href="/정보/수도-계량기-동파/">얼었을 때 녹이는 법</a> · <a href="/정보/겨울-집-점검/">겨울 집 점검 체크리스트</a></p>';
    }).catch(function(){var w=$('.frost-wait',box);if(w)w.textContent='지금은 예보를 불러오지 못했어요. 잠시 뒤 다시 열어 보세요.'});
  });

  // ---- 겨울 집 점검 체크리스트 (이 휴대폰에 기억)
  var cks=$$('.cklist input[type=checkbox]');
  if(cks.length){
    var S=load('nsg_ck',{}),cnt=$('.ck-count');
    function upd(){var n=cks.filter(function(c){return c.checked}).length;cnt.textContent=n+' / '+cks.length}
    cks.forEach(function(c){c.checked=!!S[c.dataset.k];c.addEventListener('change',function(){S[c.dataset.k]=c.checked;save('nsg_ck',S);upd()})});
    $('.ck-reset').addEventListener('click',function(){S={};save('nsg_ck',S);cks.forEach(function(c){c.checked=false});upd()});
    upd();
  }
})();
