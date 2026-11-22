(function(){
  var root=document.getElementById('req');if(!root)return;
  var JOBS={'자동차 정비':{min:40,opts:['엔진오일 교체','타이어','배터리','브레이크','점검·기타']},'하수구 막힘':{min:60,opts:['변기','싱크대','욕실·베란다 바닥','기타']},'보일러 고장':{min:60,opts:['난방 안 됨','온수 안 나옴','에러 표시','물 샘·소음']},'수도 동파':{min:60,opts:['물이 안 나옴','계량기 깨짐','배관 터짐']},'누수':{min:90,opts:['천장','벽','바닥','수도 요금 급증']},'열쇠·도어락':{min:30,opts:['문 열기','도어락 교체','열쇠 복사']}};
  var W='일월화수목금토',S={step:1,trade:'자동차 정비',job:'엔진오일 교체',mode:'날짜 고르기',day:1,part:'오전',slots:{},flex:'앞뒤 30분 괜찮아요',alt:false,altPick:{},extras:{},memo:'',budget:'잘 모르겠어요'};
  var hint=new URLSearchParams(location.search).get('t');if(hint&&JOBS[hint]){S.trade=hint;S.job=JOBS[hint].opts[0]}
  function esc(t){return String(t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function chip(on,label,act,extra){return '<button type="button" class="opt'+(on?' on':'')+'" aria-pressed="'+on+'" data-act="'+esc(act)+'"'+(extra||'')+'>'+label+'</button>'}
  function day(i){var d=new Date();d.setHours(0,0,0,0);d.setDate(d.getDate()+i);return d}
  function dtxt(d){return (d.getMonth()+1)+'/'+d.getDate()+'('+W[d.getDay()]+')'}
  var PART={'오전':[8,12,'8~12시'],'오후':[12,17,'12~17시'],'저녁':[17,21,'17~21시'],'밤':[21,24,'21시 이후']};
  function endOf(t){var m=+t.slice(0,2)*60+(+t.slice(3))+JOBS[S.trade].min;return Math.floor(m/60)%24+':'+('0'+m%60).slice(-2)}
  function summary(){var p=[S.trade+' · '+S.job];
    if(S.mode==='지금 바로')p.push('지금 바로');
    else{var sl=Object.keys(S.slots).filter(function(k){return S.slots[k]}).sort();
      p.push(dtxt(day(S.day))+' '+(sl.length?sl.join(' 또는 ')+' (끝나는 시간 약 '+endOf(sl[0])+')':S.part+' 아무 때나'));p.push(S.flex);
      var al=Object.keys(S.altPick).filter(function(k){return S.altPick[k]});if(S.alt&&al.length)p.push('2순위 '+al.join(', '));}
    var ex=Object.keys(S.extras).filter(function(k){return S.extras[k]});if(ex.length)p.push(ex.join(', '));
    p.push('예산 '+S.budget);if(S.memo)p.push('메모: '+S.memo);return p.join(' · ')}
  function render(){
    var h='',n=5;
    h+='<div class="rq-top"><button type="button" class="rq-back" data-act="back" aria-label="이전 단계"'+(S.step===1?' disabled':'')+'>‹</button><div class="rq-prog"><span>'+S.step+' / '+n+'</span><div><i style="width:'+(S.step/n*100)+'%"></i></div></div></div>';
    if(S.step===1){h+='<h1>어떤 일이 필요하세요?</h1><div class="rq-grid">'+Object.keys(JOBS).map(function(t){return chip(S.trade===t,t,'trade:'+t)}).join('')+'</div>';
      h+='<h2>조금 더 자세히</h2><div class="rq-grid">'+JOBS[S.trade].opts.map(function(o){return chip(S.job===o,o,'job:'+o)}).join('')+'</div>';}
    if(S.step===2){h+='<p class="rq-kicker">'+esc(S.job)+', 알겠어요 · 보통 약 '+JOBS[S.trade].min+'분 걸려요</p><h1>언제가 편하세요?</h1><p class="rq-sub">되는 시간을 여러 개 고르시면 맞는 업체를 더 빨리 찾아요.</p>';
      h+='<div class="seg" role="tablist">'+['지금 바로','오늘 중','날짜 고르기'].map(function(m){return '<button type="button" role="tab" aria-selected="'+(S.mode===m)+'" class="'+(S.mode===m?'on':'')+'" data-act="mode:'+m+'">'+m+'</button>'}).join('')+'</div>';
      if(S.mode==='지금 바로')h+='<p class="rq-note">지금 바로 올 수 있는 업체에만 여쭤봐요. 답이 늦으면 바로 전화할 곳도 알려 드려요.</p>';
      else{
        h+='<h2>날짜</h2><div class="days">';for(var i=0;i<14;i++){var d=day(i),wd=d.getDay(),top=i===0?'오늘':i===1?'내일':W[wd];
          h+='<button type="button" class="dayb'+(S.day===i?' on':'')+(wd===0?' sun':wd===6?' sat':'')+'" aria-pressed="'+(S.day===i)+'" data-act="day:'+i+'"><span>'+top+'</span><b>'+d.getDate()+'</b></button>'}h+='</div>';
        h+='<h2>시간대</h2><div class="rq-grid four">'+Object.keys(PART).map(function(p){return chip(S.part===p,'<b>'+p+'</b><small>'+PART[p][2]+'</small>','part:'+p)}).join('')+'</div>';
        h+='<h2>시작 시간 <small>30분 단위 · 여러 개 가능</small></h2><div class="rq-grid four">';
        var pr=PART[S.part],now=new Date(),nm=now.getHours()*60+now.getMinutes();
        for(var hh=pr[0];hh<pr[1];hh++)for(var mm=0;mm<60;mm+=30){var t=('0'+hh).slice(-2)+':'+(mm?'30':'00'),past=S.day===0&&hh*60+mm<nm;
          h+=past?'<button type="button" class="opt past" disabled>'+t+'<small>지남</small></button>':chip(!!S.slots[t],t,'slot:'+t)}
        h+='</div><h2>시간 여유는?</h2><div class="rq-grid two">'+['딱 그 시간','앞뒤 30분 괜찮아요','앞뒤 1시간 괜찮아요','그 시간대 아무 때나'].map(function(f){return chip(S.flex===f,f,'flex:'+f)}).join('')+'</div>';
        h+='<div class="rq-box"><label class="sw"><span><b>다른 날도 괜찮아요</b><small>2순위 날짜를 넣으면 답이 더 많이 와요</small></span><input type="checkbox" data-act="alt"'+(S.alt?' checked':'')+'></label>';
        if(S.alt){h+='<div class="rq-grid">';for(var k=1;k<=3;k++){var dd=day(S.day+k),lab=dtxt(dd)+' '+S.part;h+=chip(!!S.altPick[lab],lab,'altp:'+lab)}h+=chip(!!S.altPick['이번 주 아무 때나'],'이번 주 아무 때나','altp:이번 주 아무 때나')+'</div>'}
        h+='</div>';
      }
      h+='<h2>이것도 알려 주세요 <small>(선택)</small></h2><div class="rq-grid">'+(S.trade==='자동차 정비'?['차 맡겨 두기 가능','기다리면서 볼게요','출장 오면 좋겠어요']:['집에 사람 있어요','주차 자리 있어요','엘리베이터 없어요']).map(function(e){return chip(!!S.extras[e],e,'ex:'+e)}).join('')+'</div>';}
    if(S.step===3){h+='<p class="rq-kicker">선택이에요, 건너뛰셔도 돼요</p><h1>조금만 더 알려 주시면<br>가격이 정확해져요</h1><label class="fld"><span>메모</span><textarea id="memo" rows="3" placeholder="'+(S.trade==='자동차 정비'?'예: 아반떼 2019, 8만 km':'예: 2층 욕실, 어제부터 물이 천천히 내려가요')+'">'+esc(S.memo)+'</textarea></label>';}
    if(S.step===4){h+='<p class="rq-kicker">사장님이 가격대를 맞춰 드려요</p><h1>생각해 두신 예산이 있으세요?</h1><div class="rq-grid two">'+['5만 원 이하','5만~10만 원','10만~20만 원','20만 원 이상','잘 모르겠어요'].map(function(b){return chip(S.budget===b,b,'bud:'+b)}).join('')+'</div>';}
    if(S.step===5){h+='<p class="rq-kicker">거의 다 됐어요</p><h1>이렇게 여쭤볼게요</h1><div class="rq-sum">'+esc(summary())+'</div>'+
      '<div class="rq-note"><b>예약 요청 보내기는 곧 열려요.</b> 사장님 가입이 시작되면 이 내용이 동네 업체 여러 곳에 한 번에 가고, 가능한 시간과 가격대로 답이 와요. 지금은 이 내용을 복사해서 업체에 문자로 보내거나 전화로 읽어 주세요.</div>'+
      '<button type="button" class="btn dark wide" data-act="copy">요청 내용 복사하기</button><a class="btn ghost wide" href="/자동차정비/">동네 업체 찾아 전화하기</a>';}
    h+='<div class="rq-foot">'+(S.step===3||S.step===4?'<button type="button" class="btn ghost" data-act="next">건너뛰기</button>':'')+(S.step<5?'<button type="button" class="btn blue" data-act="next">다음</button>':'')+'</div>';
    if(S.step===2&&S.mode!=='지금 바로')h+='<p class="rq-live"><b>지금까지</b> '+esc(summary())+'</p>';
    root.innerHTML=h;
    var m=document.getElementById('memo');if(m)m.addEventListener('input',function(){S.memo=m.value});
  }
  root.addEventListener('click',function(e){var b=e.target.closest('[data-act]');if(!b||b.tagName==='INPUT')return;var a=b.dataset.act,v=a.slice(a.indexOf(':')+1);
    if(a==='next')S.step=Math.min(5,S.step+1);else if(a==='back')S.step=Math.max(1,S.step-1);
    else if(a.indexOf('trade:')===0){S.trade=v;S.job=JOBS[v].opts[0]}else if(a.indexOf('job:')===0)S.job=v;
    else if(a.indexOf('mode:')===0){S.mode=v;if(v==='오늘 중')S.day=0}else if(a.indexOf('day:')===0){S.day=+v;S.mode=S.day===0?'오늘 중':'날짜 고르기'}
    else if(a.indexOf('part:')===0)S.part=v;else if(a.indexOf('slot:')===0)S.slots[v]=!S.slots[v];else if(a.indexOf('flex:')===0)S.flex=v;
    else if(a.indexOf('altp:')===0)S.altPick[v]=!S.altPick[v];else if(a.indexOf('ex:')===0)S.extras[v]=!S.extras[v];else if(a.indexOf('bud:')===0)S.budget=v;
    else if(a==='copy'){var t=summary();(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent='복사했어요'},function(){b.textContent='길게 눌러 복사해 주세요'});return}
    render();if(a==='next'||a==='back')window.scrollTo(0,0)});
  root.addEventListener('change',function(e){if(e.target.dataset.act==='alt'){S.alt=e.target.checked;render()}});
  render();
})();
