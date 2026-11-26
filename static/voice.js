/* 말로 찾기: 음성(또는 글)으로 업종·동네·시간을 알아듣고, 가까운 곳을 찾아 전화로 연결해요.
   위치(GPS)는 쓰지 않고, 말한 동네 이름으로 찾아요. 말한 내용은 서버에 저장하지 않아요. */
(function(){
  var $=function(s,r){return (r||document).querySelector(s)},esc=function(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
  var REG=(window.VOICE_REGIONS||[]);
  var KINDS=[
    [/보일러|난방|온수|뜨거운 ?물|따뜻한 ?물/,'보일러 수리','보일러','fix'],
    [/하수구|변기|싱크대|배수구|막혔|막힘|역류/,'하수구 막힘','하수구·변기 막힘','fix'],
    [/누수|물이 ?새|물 ?새|천장.*물|아랫집/,'누수 탐지','누수','fix'],
    [/차단기|누전|정전|콘센트|전등|전기/,'전기 공사','전기','fix'],
    [/열쇠|도어락|현관.*안 ?열|문이 ?안 ?열|잠겼|잠김/,'열쇠 도어락','열쇠·도어락','fix'],
    [/동파|얼었|계량기/,'수도 동파','수도 동파','fix'],
    [/에어컨|세탁기|냉장고|가전|티비|TV/i,'가전 수리','가전 수리','fix'],
    [/샷시|새시|창호|창문|방충망/,'샷시','창호·샷시','fix'],
    [/도배|장판|벽지/,'도배 장판','도배·장판','fix'],
    [/폐기물|철거|버릴|버리|소파 ?버|가구 ?버/,'폐기물 수거','대형 폐기물','fix'],
    [/타이어|펑크|배터리|방전|견인|긴급출동/,'타이어 긴급출동','타이어·긴급출동','car'],
    [/동물병원|강아지|고양이|반려/,'동물병원','동물병원','open'],
    [/약국/,'약국','약국','open'],
    [/치과/,'치과','치과','open'],
    [/응급실/,'응급실','응급실','open'],
    [/병원|의원|소아과|내과|정형외과|이비인후과/,'병원','병원','open'],
    [/콜택시|택시/,'콜택시','콜택시','taxi'],
    [/분실물|잃어버/,'분실물센터','분실물','lost'],
    [/지하철|전철/,'지하철역','지하철역','info'],
    [/미술관|갤러리/,'미술관','미술관','visit'],
    [/박물관/,'박물관','박물관','visit'],
    [/공연|연극|뮤지컬|콘서트/,'공연장','공연장','visit'],
    [/도서관/,'도서관','도서관','visit'],
    [/미용실|헤어|머리 ?자르/,'미용실','미용실','book'],
    [/네일/,'네일','네일샵','book'],
    [/세탁소|드라이/,'세탁소','세탁소','open'],
    [/식당|밥집|맛집|회식|단체/,'음식점','음식점','book'],
    [/카페/,'카페','카페','open'],
    [/세차/,'세차','세차장','book'],
    [/카센터|정비|엔진오일/,'자동차 정비','자동차 정비','car'],
    [/이사|용달/,'용달 이사','이사·용달','fix'],
    [/청소/,'청소 업체','청소','fix'],
    [/방역|바퀴벌레|해충|쥐/,'방역','방역·해충','fix']
  ];
  var DIAL=/전화 ?(해|하|걸|좀|부탁|넣어|연결)|연락 ?(해|하|좀|줘|주|부탁|넣어)|연결 ?(해|좀|부탁)|걸어 ?(줘|주)|불러 ?(줘|주)|통화 ?(해|하|연결)|콜 ?(해|불러)/;
  var FILLER=/(연락 ?해 ?줘|연락 ?해 ?주세요|연락해|연락 ?좀|연락 ?부탁|전화 ?걸어 ?줘|걸어 ?줘|통화 ?연결|통화 ?하고 ?싶|가까운|근처|가장|제일|좀|빨리|어디|데|곳|불러 ?줘|불러 ?주세요|찾아 ?줘|찾아 ?주세요|예약해 ?줘|예약 ?해 ?주세요|예약|전화해 ?줘|전화 ?해 ?주세요|연결해 ?줘|알려 ?줘|해 ?줘|주세요|요\.?$)/g;
  function parse(t){
    var o={raw:t.trim(),kind:null};
    for(var i=0;i<KINDS.length;i++){if(KINDS[i][0].test(t)){o.kind=KINDS[i];break}}
    // 시·군·구
    var best=null;REG.forEach(function(r){var gu=r[1];var parts=gu.split(' ');var last=parts[parts.length-1];
      if(t.indexOf(gu)>=0||t.indexOf(last)>=0){var sc=(t.indexOf(r[2])>=0?2:0)+(t.indexOf(gu)>=0?1:0)+last.length/10;if(!best||sc>best.sc)best={r:r,sc:sc}}});
    if(best)o.region=best.r;
    var dm=t.match(/([가-힣]{1,5}\d?(?:동|읍|면|가))(?=[\s,.에은는이가의서]|$)/g);
    if(dm){dm=dm.filter(function(d){return !/^(이동|운동|자동|행동|활동|전동|공동|수동|아파트동|반동|작동|가동|출동|소동|감동|파동)$/.test(d)});if(dm.length)o.dong=dm[dm.length-1]}
    // 시간
    var w=t.match(/(지금|당장|바로)/);if(w)o.when='지금 바로';
    var d=t.match(/(오늘|내일|모레|이번 ?주말|토요일|일요일|월요일|화요일|수요일|목요일|금요일)/),ap=t.match(/(오전|오후|아침|점심|저녁|밤)/),h=t.match(/(\d{1,2}|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두)\s*시(\s*반|\s*(\d{1,2})\s*분)?/);
    var KN={'한':1,'두':2,'세':3,'네':4,'다섯':5,'여섯':6,'일곱':7,'여덟':8,'아홉':9,'열':10,'열한':11,'열두':12};
    if(d||ap||h){var s=(d?d[1]+' ':'')+(ap?ap[1]+' ':'')+(h?((KN[h[1]]||h[1])+'시'+(h[2]?(/반/.test(h[2])?' 반':' '+h[3]+'분'):'')):'');o.when=s.trim()}
    var code=t.match(/\b([A-Za-z]{1,2}\s?-?\s?\d{1,3})\b|에러\s*(\d{1,3})/);if(code)o.code=(code[1]||code[2]).replace(/\s/g,'').toUpperCase();
    // 증상: 업종·지역·시간·부탁 말을 빼고 남은 말
    var sym=t;if(o.region)sym=sym.replace(o.region[1],'').replace(o.region[1].split(' ').pop(),'');if(o.dong)sym=sym.replace(o.dong,'');
    sym=sym.replace(/(지금|당장|바로|오늘|내일|모레|오전|오후|아침|점심|저녁|\d{1,2}\s*시(\s*반)?)/g,' ').replace(FILLER,' ').replace(/\s+/g,' ').trim();
    o.sym=sym.length>2?sym:'';
    return o}
  function script(o,place){
    var area=(o.region?o.region[1].split(' ').pop():'')+(o.dong?' '+o.dong:'');var when=o.when||'오늘 중에';var k=o.kind?o.kind[3]:'gen';var nm=o.kind?o.kind[2]:'';
    var sym=o.sym?o.sym.replace(/[.。]$/,''):'';
    if(k==='fix')return '안녕하세요. '+(area?area+'에 사는데요, ':'')+(sym?sym+'.':nm+' 때문에 연락드렸어요.')+(o.code&&sym.toUpperCase().replace(/[\s-]/g,'').indexOf(o.code.replace(/-/g,''))<0?' 화면에 에러 '+o.code+' 표시가 떠요.':'')+' '+when+' 와 주실 수 있을까요? 출장비랑 대략 비용도 알려 주세요.';
    if(k==='car')return '안녕하세요. '+(area?area+' 근처인데요, ':'')+(sym?sym+'.':nm+' 도움이 필요해요.')+' '+when+' 와 주실 수 있을까요? 도착까지 얼마나 걸리고 비용은 얼마인지 알려 주세요.';
    if(k==='open')return '안녕하세요. '+when+' 문 여나요? '+(sym?sym+'. ':'')+'지금 가면 바로 볼 수 있는지 알고 싶어요.';
    if(k==='taxi')return '안녕하세요. '+(area?area+'에서 ':'')+'택시 부르려고요. '+when+' 배차 가능할까요? 출발지는 (정확한 주소)예요.';
    if(k==='lost')return '안녕하세요. 물건을 잃어버려서 연락드렸어요. '+(sym?sym+'. ':'')+'(잃어버린 날짜·장소·물건 모양)인데 들어온 게 있는지 확인 부탁드려요.';
    if(k==='visit')return '안녕하세요. '+when+' 관람하려고 하는데요, 예약이 필요한지, 어떻게 하면 되는지 여쭤보려고요.';
    if(k==='book')return '안녕하세요. '+when+' '+(sym?sym+' ':'')+'예약 가능할까요? (인원·이름)으로 부탁드려요.';
    return '안녕하세요. '+(sym?sym+'. ':'')+when+' 가능한지 여쭤보려고요.'}
  /* ---------- 카카오 ---------- */
  var kready;function kakaoLoad(){if(!(window.NSG&&NSG.kakao))return Promise.reject(new Error('nokey'));if(kready)return kready;kready=new Promise(function(ok,no){var s=document.createElement('script');s.src='https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&libraries=services&appkey='+encodeURIComponent(NSG.kakao);s.onload=function(){kakao.maps.load(function(){ok()})};s.onerror=no;document.head.appendChild(s)});return kready}
  function geo(q){return new Promise(function(res){var g=new kakao.maps.services.Geocoder();g.addressSearch(q,function(d,st){res(st===kakao.maps.services.Status.OK&&d[0]?{x:+d[0].x,y:+d[0].y,name:d[0].address_name}:null)})})}
  function places(kw,c,rad){return new Promise(function(res){var ps=new kakao.maps.services.Places(),S=kakao.maps.services;var all=[];function go(p){ps.keywordSearch(kw,function(d,st,pg){if(st===S.Status.OK)all=all.concat(d);if(st===S.Status.OK&&pg&&pg.hasNextPage&&p<2&&all.filter(function(x){return x.phone}).length<8)go(p+1);else res(all)},{location:new kakao.maps.LatLng(c.y,c.x),radius:rad,sort:S.SortBy.DISTANCE,page:p})}go(1)})}
  /* ---------- 화면 ---------- */
  var st={o:null,list:[],idx:-1,pending:null,auto:true,timer:null};
  try{st.auto=localStorage.getItem('nsg_voice_auto')!=='0'}catch(e){}
  function area(){try{return JSON.parse(localStorage.getItem('nsg_voice_area')||'null')}catch(e){return null}}
  function saveArea(a){try{localStorage.setItem('nsg_voice_area',JSON.stringify(a))}catch(e){}}
  function show(h){$('#v-out').innerHTML=h}
  function msg(t){show('<p class="v-msg">'+t+'</p>')}
  function run(text){
    text=(text||'').trim();if(!text){msg('찾을 내용을 말하거나 적어 주세요.');return}
    $('#v-q').value=text;var o=parse(text);st.o=o;o.dial=DIAL.test(text);
    if(!o.region&&!o.dong){var a=area();if(a){o.region=a.region;o.dong=a.dong}}
    else if(!o.region&&o.dong){var a2=area();if(a2)o.region=a2.region}
    var kw=o.kind?o.kind[1]:text.replace(FILLER,' ').replace(/\s+/g,' ').trim();
    if(!o.region){askArea(o,kw);return}
    saveArea({region:o.region,dong:o.dong||''});
    var where=o.region[1]+(o.dong?' '+o.dong:'');
    var summary='<div class="v-sum"><span>🔎 '+esc(o.kind?o.kind[2]:kw)+'</span><span>📍 '+esc(where)+'</span>'+(o.when?'<span>🕒 '+esc(o.when)+'</span>':'')+'<button type="button" class="v-chg" id="v-chg">동네 바꾸기</button></div>';
    show(summary+'<p class="v-msg">가까운 곳을 찾고 있어요…</p>');
    if(window.gtag)gtag('event','voice_search',{kind:o.kind?o.kind[2]:'기타',region:o.region[1]});
    kakaoLoad().then(function(){
      return geo(o.region[0]+(o.dong?' '+o.dong:'')).then(function(c){return c||geo(o.region[0])})
    }).then(function(c){
      if(!c){show(summary+'<p class="v-msg">동네 위치를 못 찾았어요. 동네 이름을 다시 말해 주세요.</p>');return}
      var rad=o.kind&&/visit|taxi|lost|info/.test(o.kind[3])?20000:(o.dong?3000:8000);
      return places(kw,c,rad).then(function(L){
        L=L.filter(function(x){return x.phone});
        var seen={};L=L.filter(function(x){if(seen[x.phone])return false;seen[x.phone]=1;return true}).slice(0,6);
        st.list=L;st.idx=-1;render(summary);
        if(o.dial&&L.length){var b=document.createElement('button');b.type='button';b.className='v-big';b.innerHTML='☎ '+esc(L[0].place_name)+'에 전화';b.onclick=function(){dial(0)};var sc=$('.v-script');sc.parentNode.insertBefore(b,sc);
          toast('가장 가까운 '+L[0].place_name+'에 전화를 걸어요');setTimeout(function(){dial(0)},900)}})
    }).catch(function(){show(summary+'<p class="v-msg">지금은 지도 검색을 쓸 수 없어요. <a href="https://m.search.naver.com/search.naver?query='+encodeURIComponent(where+' '+kw)+'" target="_blank" rel="noopener">네이버에서 \''+esc(where+' '+kw)+'\' 찾기</a></p>')})}
  function askArea(o,kw){
    var opts=REG.map(function(r){return '<option value="'+esc(r[0])+'">'+esc(r[0])+'</option>'}).join('');
    show('<div class="v-ask"><p><b>어느 동네에서 찾을까요?</b><br>"연수구 송도동"처럼 말하거나 아래에서 골라 주세요. 위치(GPS)는 쓰지 않아요.</p><div class="v-row"><select id="v-reg" aria-label="시·군·구"><option value="">시·군·구 고르기</option>'+opts+'</select><input id="v-dong" placeholder="동 (예: 송도동)" aria-label="동"></div><button type="button" class="v-go" id="v-areago">이 동네에서 찾기</button></div>');
    $('#v-areago').onclick=function(){var v=$('#v-reg').value;if(!v){$('#v-reg').focus();return}var r=REG.filter(function(x){return x[0]===v})[0];var d=$('#v-dong').value.trim();saveArea({region:r,dong:d});run(o.raw+' '+r[1]+(d?' '+d:''))}}
  function km(m){m=+m;return m>=1000?(m/1000).toFixed(1)+'km':m+'m'}
  function render(summary){
    var o=st.o,L=st.list;
    if(!L.length){show(summary+'<p class="v-msg">전화번호가 있는 곳을 찾지 못했어요. 동네를 넓혀 시·군·구만 말해 보세요.</p>');return}
    var sc=script(o);
    var h=summary+'<div class="v-script"><div class="v-sh"><b>📝 통화할 때 이렇게 말해요</b><button type="button" id="v-copy">복사</button></div><textarea id="v-scr" rows="4" aria-label="통화 대본">'+esc(sc)+'</textarea></div>'+
      '<label class="v-auto"><input type="checkbox" id="v-autochk"'+(st.auto?' checked':'')+'> 안 받으면 다음 곳으로 바로 넘어가기</label>'+
      (o.kind&&o.kind[3]==='lost'?'<p class="v-note">지하철·버스·택시에서 잃어버린 물건은 경찰청 유실물 종합안내 <a href="https://www.lost112.go.kr" target="_blank" rel="noopener">lost112.go.kr</a>에서도 찾아볼 수 있어요.</p>':'')+
      (o.kind&&o.kind[3]==='visit'?'<p class="v-note">미술관·공연은 대부분 각 기관 홈페이지에서 예약해요. \'자세히\'를 눌러 기관 정보를 확인하세요.</p>':'')+
      '<ol class="v-list">'+L.map(function(x,i){return '<li class="v-it'+(i===st.idx?' on':'')+(x._miss?' miss':'')+'" data-i="'+i+'"><div class="v-n"><b>'+esc(x.place_name)+'</b><span>'+esc((x.category_name||'').split(' > ').pop())+' · '+km(x.distance)+'</span><small>'+esc(x.road_address_name||x.address_name)+'</small>'+(x._miss?'<em>안 받음</em>':'')+'</div>'+
        '<div class="v-a"><a class="v-call" href="tel:'+esc(x.phone.replace(/[^0-9]/g,''))+'" data-i="'+i+'">☎ 전화</a><a class="v-more" href="'+esc(x.place_url)+'" target="_blank" rel="noopener">자세히</a></div></li>'}).join('')+'</ol>'+
      '<p class="v-src">장소·전화번호: 카카오 지도 검색 결과(저장하지 않아요). 영업 여부는 전화로 확인하세요.</p>';
    show(h);
    $('#v-copy').onclick=function(){var t=$('#v-scr').value;(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){toast('대본을 복사했어요')},function(){$('#v-scr').select()})};
    $('#v-autochk').onchange=function(){st.auto=this.checked;try{localStorage.setItem('nsg_voice_auto',st.auto?'1':'0')}catch(e){}}}
  function toast(t){var e=$('#v-toast');e.textContent=t;e.classList.add('on');clearTimeout(toast.t);toast.t=setTimeout(function(){e.classList.remove('on')},2200)}
  /* ---------- 전화 뒤 돌아왔을 때 ---------- */
  function afterCall(){
    var p=st.pending;if(!p)return;st.pending=null;
    var cur=st.list[p.i];if(!cur)return;
    var next=st.list.findIndex(function(x,j){return j>p.i&&!x._miss});
    var sh=$('#v-after');
    sh.innerHTML='<p><b>'+esc(cur.place_name)+'</b> 통화 어땠어요?</p><div class="v-row2"><button type="button" class="v-ok" id="v-okb">✅ 연결됐어요</button>'+(next>=0?'<button type="button" class="v-nx" id="v-nxb">📵 안 받아요 → 다음 곳</button>':'<button type="button" class="v-nx" id="v-nxb">📵 안 받아요</button>')+'</div>'+(next>=0&&st.auto?'<p class="v-cd" id="v-cd"></p>':'');
    sh.hidden=false;
    function close(){clearInterval(st.timer);sh.hidden=true}
    $('#v-okb').onclick=function(){close();toast('잘 연결됐네요!');if(window.gtag)gtag('event','voice_call_ok')};
    $('#v-nxb').onclick=function(){close();cur._miss=true;if(next>=0)dial(next);else{render($('.v-sum')?$('.v-sum').outerHTML:'');toast('목록의 곳에 모두 걸었어요. 동네를 넓혀 다시 찾아보세요.')}};
    if(next>=0&&st.auto){var n=6,cd=$('#v-cd'),nm=esc(st.list[next].place_name);
      var tick=function(){n--;if(!cd.isConnected){clearInterval(st.timer);return}
        if(n<=0){clearInterval(st.timer);close();cur._miss=true;dial(next);return}
        cd.innerHTML=n+'초 뒤 <b>'+nm+'</b>에 전화해요 <button type="button" id="v-stop">멈추기</button>';
        $('#v-stop').onclick=function(){clearInterval(st.timer);cd.textContent='자동으로 넘어가기를 멈췄어요.'}};
      n++;tick();st.timer=setInterval(tick,1000)}}
  function dial(i){var x=st.list[i];if(!x)return;st.idx=i;var big=$('.v-big');render($('.v-sum')?$('.v-sum').outerHTML:'');if(big&&i===0){var sc=$('.v-script');sc.parentNode.insertBefore(big,sc)}var li=document.querySelector('.v-it[data-i="'+i+'"]');if(li)li.scrollIntoView({behavior:'smooth',block:'center'});st.pending={i:i,t:Date.now()};if(window.gtag)gtag('event','phone_call_click',{section:'voice',sub1:x.place_name,link_text:'auto_next'});location.href='tel:'+x.phone.replace(/[^0-9]/g,'')}
  document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('.v-call');if(!a)return;var i=+a.dataset.i;st.idx=i;st.pending={i:i,t:Date.now()};document.querySelectorAll('.v-it').forEach(function(li){li.classList.toggle('on',+li.dataset.i===i)})});
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='visible'&&st.pending&&Date.now()-st.pending.t>1500)setTimeout(afterCall,300)});
  window.addEventListener('focus',function(){if(st.pending&&Date.now()-st.pending.t>4000)setTimeout(afterCall,300)});
  /* ---------- 음성 ---------- */
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition,rec=null,on=false;
  var mic=$('#v-mic'),live=$('#v-live');
  if(!SR){mic.classList.add('off');$('#v-micl').textContent='이 브라우저는 음성 인식을 지원하지 않아요. 키보드의 마이크 버튼으로 말해도 돼요.'}
  mic.onclick=function(){
    if(!SR){$('#v-q').focus();return}
    if(on){rec.stop();return}
    rec=new SR();rec.lang='ko-KR';rec.interimResults=true;rec.maxAlternatives=1;var fin='';
    rec.onstart=function(){on=true;mic.classList.add('rec');live.textContent='듣고 있어요… 말씀하세요';$('#v-micl').textContent='다 말하면 잠시 기다리거나 다시 누르세요'};
    rec.onresult=function(ev){var t='';for(var i=ev.resultIndex;i<ev.results.length;i++){if(ev.results[i].isFinal)fin+=ev.results[i][0].transcript;else t+=ev.results[i][0].transcript}live.textContent=fin+t;$('#v-q').value=fin+t};
    rec.onerror=function(ev){live.textContent=ev.error==='not-allowed'?'마이크 사용을 허용해 주세요. 아니면 아래에 글로 적어도 돼요.':'잘 못 들었어요. 다시 눌러 말해 주세요.'};
    rec.onend=function(){on=false;mic.classList.remove('rec');$('#v-micl').textContent='눌러서 말하기';if(fin.trim())run(fin)};
    try{rec.start()}catch(e){}};
  $('#v-form').onsubmit=function(e){e.preventDefault();run($('#v-q').value)};
  document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-ex]');if(b){run(b.dataset.ex);window.scrollTo({top:$('#v-box').offsetTop-70,behavior:'smooth'})}
    if(e.target.id==='v-chg'){try{localStorage.removeItem('nsg_voice_area')}catch(_){}var o=st.o;if(o){o.region=null;o.dong=null;askArea(o,'')}}});
  var q=new URLSearchParams(location.search).get('q');if(q)run(q);
})();
