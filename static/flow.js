(function(){
  function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function won(a,b){function f(n){return n>=10000?(n/10000).toFixed(n%10000?1:0).replace('.0','')+'만':n.toLocaleString()}return a&&b?f(a)+'~'+f(b)+' 원':a?f(a)+' 원부터':''}
  var LIVE=!!(window.NSG&&NSG.api),SMS=!!(window.NSG&&NSG.sms),tok=location.hash.slice(1);
  function off(el){el.innerHTML='<div class="card"><h2>아직 준비 중이에요</h2><p>이 기능은 사장님 가입이 시작되면 열려요.</p></div>'}
  // ---------------- 손님: 내 요청 (비교·확정·후기)
  var my=document.getElementById('my');
  if(my){ if(!LIVE)return off(my); if(!tok){my.innerHTML='<div class="card"><p>요청 링크가 올바르지 않아요.</p></div>';return}
    var picked=null,stars=5,tags={};
    function load(){NSG.call('get_request',{t:tok}).then(draw,function(e){my.innerHTML='<div class="card"><p>'+esc(e.message)+'</p></div>'})}
    function draw(q){if(!q){my.innerHTML='<div class="card"><p>요청을 찾을 수 없어요. 30일이 지나면 지워져요.</p></div>';return}
      var R=q.replies||[],h='<section class="hero"><p class="rq-kicker">'+esc(q.job||q.trade)+' · '+esc(q.region)+'</p><h1>'+(R.length?'업체 '+R.length+'곳이 답했어요':'업체 답을 기다리고 있어요')+'</h1><p class="lead">'+esc(q.summary)+'</p></section>';
      if(!R.length)h+='<div class="card"><p>요청이 '+q.sent+'곳에 갔어요. '+(SMS?'답이 오면 문자로 알려 드려요. ':'답은 이 페이지에 모여요. ')+'<b>이 페이지 주소를 꼭 저장해 두세요.</b></p><button type="button" class="btn ghost wide" data-copy="1">이 페이지 주소 복사하기</button><p class="muted">30분이 지나도 답이 없으면 동네 업체에 바로 전화해 보세요.</p><a class="btn ghost wide" href="/자동차정비/">동네 업체 전화번호 보기</a></div>';
      R.forEach(function(r){var tag=r.answer==='ok'?['원하신 시간 가능','ok']:r.answer==='other'?['다른 시간 제안','other']:['이번엔 어려워요','no'];
        h+='<article class="shop'+(r.chosen?' chosen':'')+'"><div class="shop-head"><h3>'+esc(r.name)+'</h3><span class="tag '+tag[1]+'">'+tag[0]+'</span></div>'+
          (r.stars?'<p class="addr">★ '+r.stars+' · 업체 후기 '+r.reviews+'건</p>':'<p class="addr">아직 후기 없음</p>')+
          (r.answer!=='no'?'<div class="two"><div><small>가능한 시간</small><b>'+esc(r.slot||'-')+'</b></div><div><small>예상 가격</small><b>'+esc(won(r.price_min,r.price_max)||'현장 확인 후')+'</b>'+(r.labor?'<small class="ok">부품+공임 포함</small>':'')+'</div></div>'+(r.note?'<p>“'+esc(r.note)+'”</p>':''):'')+
          (q.status==='open'&&r.answer!=='no'?'<div class="actions"><button type="button" class="btn blue" data-pick="'+r.id+'">이 업체로 확정</button>'+(r.phone?'<a class="btn ghost" href="tel:'+esc(r.phone.replace(/[^0-9]/g,''))+'">전화</a>':'')+'</div>':'')+
          (r.chosen?'<p class="ok"><b>확정했어요.</b> '+(SMS?'사장님께도 알려 드렸어요. ':'')+(r.phone?'자세한 시간은 '+esc(r.phone)+'로 통화해서 맞춰 주세요.':'')+'</p>':'')+'</article>'});
      if(q.status==='chosen'&&!q.reviewed){var T=['시간 약속 지킴','설명한 가격 그대로','친절해요','꼼꼼해요','뒷정리 깔끔','빨리 와 줬어요'];
        h+='<section class="card" id="rv"><h2>일이 끝났다면, 업체는 어떠셨어요?</h2><div class="stars" role="radiogroup" aria-label="별점">'+[1,2,3,4,5].map(function(n){return '<button type="button" role="radio" aria-checked="'+(n===stars)+'" aria-label="'+n+'점" data-star="'+n+'" class="'+(n<=stars?'on':'')+'">★</button>'}).join('')+'</div>'+
          '<div class="rq-grid">'+T.map(function(t){return '<button type="button" class="opt'+(tags[t]?' on':'')+'" data-tag="'+t+'">'+t+'</button>'}).join('')+'</div>'+
          '<label class="fld"><span>실제로 낸 금액 (선택, 이름 없이 평균 계산에만 써요)</span><input id="paid" type="number" inputmode="numeric" placeholder="예: 62000"></label>'+
          '<label class="fld"><span>한 줄 후기 (선택)</span><textarea id="body" rows="2" maxlength="200"></textarea></label><button type="button" class="btn blue wide" data-review="1">후기 올리기</button><p class="muted">예약이 확정된 손님만 후기를 남길 수 있어요. 이름은 가려져요.</p></section>'}
      if(q.reviewed)h+='<div class="card"><p>후기 고마워요! 다음 손님이 업체를 고를 때 큰 도움이 돼요.</p></div>';
      my.innerHTML=h}
    my.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
      if(b.dataset.pick){b.disabled=true;NSG.call('choose_owner',{t:tok,oid:b.dataset.pick}).then(load,function(er){alertBox(er.message)})}
      else if(b.dataset.copy){(navigator.clipboard?navigator.clipboard.writeText(location.href):Promise.reject()).then(function(){b.textContent='복사했어요'},function(){b.textContent=location.href})}
      else if(b.dataset.star){stars=+b.dataset.star;[].forEach.call(my.querySelectorAll('[data-star]'),function(x){x.classList.toggle('on',+x.dataset.star<=stars);x.setAttribute('aria-checked',+x.dataset.star===stars)})}
      else if(b.dataset.tag){tags[b.dataset.tag]=!tags[b.dataset.tag];b.classList.toggle('on')}
      else if(b.dataset.review){b.disabled=true;NSG.call('write_review',{t:tok,p:{stars:stars,tags:Object.keys(tags).filter(function(k){return tags[k]}),paid:document.getElementById('paid').value,body:document.getElementById('body').value}}).then(load,function(er){b.disabled=false;alertBox(er.message)})}});
    function alertBox(m){var p=document.createElement('p');p.className='err';p.setAttribute('role','alert');p.textContent=m;my.prepend(p)}
    load();setInterval(function(){if(!document.querySelector('#rv'))load()},60000);
  }
  // ---------------- 사장님: 답변
  var rp=document.getElementById('reply');
  if(rp){ if(!LIVE)return off(rp); if(!tok){rp.innerHTML='<div class="card"><p>답변 링크가 올바르지 않아요.</p></div>';return}
    var ans='ok';
    NSG.call('get_reply',{t:tok}).then(function(q){if(!q){rp.innerHTML='<div class="card"><p>요청을 찾을 수 없어요. 기한이 지났을 수 있어요.</p></div>';return}
      var h='<section class="hero"><p class="rq-kicker">'+esc(q.region)+' · '+esc(q.job||q.trade)+'</p><h1>손님 요청이 왔어요</h1><p class="lead">'+esc(q.summary)+'</p></section>';
      if(q.photos&&q.photos.length)h+='<div class="photos">'+q.photos.map(function(u){return '<span class="ph"><img src="'+u+'" alt="손님 사진"></span>'}).join('')+'</div>';
      if(q.memo)h+='<div class="card"><p>“'+esc(q.memo)+'”</p></div>';
      if(q.chosen)h+='<div class="card soon"><h2>손님이 사장님을 골랐어요</h2><p>손님 번호: <a href="tel:'+esc(q.mobile)+'">'+esc(q.mobile)+'</a> 로 연락해 자세한 시간을 맞춰 주세요.</p></div>';
      else if(q.status!=='open')h+='<div class="card"><p>이 요청은 마감됐어요.</p></div>';
      else{h+='<section class="card"><h2>답하기</h2><div class="seg three">'+[['ok','그 시간 가능'],['other','다른 시간 제안'],['no','이번엔 어려움']].map(function(a){return '<button type="button" data-ans="'+a[0]+'" class="'+(a[0]===(q.answer||ans)?'on':'')+'">'+a[1]+'</button>'}).join('')+'</div>'+
        '<div id="more"><label class="fld"><span>가능한 시간</span><input id="slot" placeholder="예: 토 10:00" value="'+esc(q.slot||'')+'"></label>'+
        '<div class="two"><label class="fld"><span>최소 가격(원)</span><input id="pmin" type="number" inputmode="numeric" value="'+esc(q.price_min||'')+'"></label><label class="fld"><span>최대 가격(원)</span><input id="pmax" type="number" inputmode="numeric" value="'+esc(q.price_max||'')+'"></label></div>'+
        '<label class="agree"><input type="checkbox" id="labor"'+(q.labor?' checked':'')+'><span>부품+공임 포함 가격이에요</span></label>'+
        '<label class="fld"><span>손님께 한마디 (선택)</span><input id="note" maxlength="200" value="'+esc(q.note||'')+'" placeholder="예: 오일 종류 보고 최종 금액 안내드려요"></label></div>'+
        '<button type="button" class="btn blue wide" id="send">'+(q.answer?'답 고쳐서 보내기':'답 보내기')+'</button><p id="msg" class="muted" aria-live="polite"></p></section>';}
      rp.innerHTML=h;ans=q.answer||'ok';
      rp.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
        if(b.dataset.ans){ans=b.dataset.ans;[].forEach.call(rp.querySelectorAll('[data-ans]'),function(x){x.classList.toggle('on',x===b)});document.getElementById('more').hidden=ans==='no'}
        if(b.id==='send'){b.disabled=true;NSG.call('answer_reply',{t:tok,p:{answer:ans,slot:val('slot'),price_min:val('pmin'),price_max:val('pmax'),labor:document.getElementById('labor').checked,note:val('note')}})
          .then(function(){document.getElementById('msg').textContent='손님께 답을 보냈어요. '+(SMS?'손님이 고르면 문자로 알려 드려요.':'손님이 고르면 이 페이지에 손님 번호가 보여요.');b.disabled=false;b.textContent='답 고쳐서 보내기'},function(er){document.getElementById('msg').textContent=er.message;b.disabled=false})}});
    },function(e){rp.innerHTML='<div class="card"><p>'+esc(e.message)+'</p></div>'});
    function val(id){var el=document.getElementById(id);return el?el.value:''}
  }
  // ---------------- 사장님: 가입 신청
  var jf=document.getElementById('join');
  if(jf&&LIVE){jf.hidden=false;var mail=document.getElementById('join-mail');if(mail)mail.hidden=true;
    jf.addEventListener('submit',function(e){e.preventDefault();var f=new FormData(jf),p={};f.forEach(function(v,k){p[k]=v});p.biz_no=(p.biz_no||'').replace(/[^0-9]/g,'');p.mobile=(p.mobile||'').replace(/[^0-9]/g,'');p.sms_consent=!!p.sms_consent;
      var out=document.getElementById('join-msg'),btn=jf.querySelector('button');btn.disabled=true;
      NSG.call('apply_owner',{p:p}).then(function(){jf.innerHTML='<h2>신청을 받았어요</h2><p>사업자등록을 확인한 뒤 적어 주신 휴대폰으로 연락드려요.</p>'},function(er){out.textContent=er.message;btn.disabled=false})})}
})();
