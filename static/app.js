(function(){
  function $(s,r){return (r||document).querySelector(s)}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
  // ---- 지금 영업 중 표시
  var now=new Date(), wd=now.getDay(), mins=now.getHours()*60+now.getMinutes();
  function toMin(t){var m=/^(\d{1,2}):(\d{2})/.exec(t||'');return m?(+m[1])*60+(+m[2]):null}
  $$('.chip[data-hours]').forEach(function(c){
    var p=c.getAttribute('data-hours').split('-'),a=toMin(p[0]),b=toMin(p[1]);
    if(a==null||b==null)return;
    var weekday=wd>=1&&wd<=5,open=weekday&&mins>=a&&mins<b;
    c.classList.add(open?'open':'closed');
    c.textContent=(open?'영업 중 · ':weekday?'영업시간 아님 · ':'주말은 전화로 확인 · ')+'평일 '+p[0]+'~'+p[1];
    c.closest('.shop').dataset.open=open?'1':'0';
  });
  // ---- 더 보기 + 필터
  var shops=$$('.shop'), shown=$('#shown'), more=$('.more'), box=$('.shops'), limit=box?+box.dataset.page:0, filtered=false;
  function paginate(){if(!more)return;var vis=shops.filter(function(s){return !s.dataset.off});
    vis.forEach(function(s,i){s.hidden=!filtered&&i>=limit});more.hidden=filtered||vis.length<=limit;}
  if(more){paginate();more.addEventListener('click',function(){limit+=30;paginate()})}
  $$('.f').forEach(function(b){b.addEventListener('click',function(){
    $$('.f').forEach(function(x){x.classList.remove('on');x.setAttribute('aria-pressed','false')});
    b.classList.add('on');b.setAttribute('aria-pressed','true');
    var f=b.dataset.f,n=0;filtered=f!=='all';
    shops.forEach(function(s){var ok=true,t=s.dataset.type;
      if(f==='big')ok=(t==='1'||t==='2');else if(f==='small')ok=(t==='3'||t==='4');
      else if(f==='open')ok=s.dataset.open==='1';else if(f.indexOf('dong:')===0)ok=s.dataset.dong===f.slice(5);
      s.hidden=!ok;if(ok){n++;delete s.dataset.off}else s.dataset.off='1';});
    if(!filtered)paginate();
    if(shown)shown.textContent=n;
  })});
  // ---- 전화번호 보기 (저장하지 않고 그때그때 찾기)
  var kakaoReady=null;
  function loadKakao(){
    if(!window.NSG||!NSG.kakao)return Promise.reject();
    if(kakaoReady)return kakaoReady;
    kakaoReady=new Promise(function(ok,no){var s=document.createElement('script');
      s.src='https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&libraries=services&appkey='+encodeURIComponent(NSG.kakao);
      s.onload=function(){kakao.maps.load(function(){ok()})};s.onerror=no;document.head.appendChild(s)});
    return kakaoReady;
  }
  $$('.lookup').forEach(function(b){b.addEventListener('click',function(){
    var card=b.closest('.shop'),note=$('.lookup-note',card),q=b.dataset.q,name=b.dataset.name;
    function fallback(){window.open('https://m.search.naver.com/search.naver?query='+encodeURIComponent(q),'_blank','noopener')}
    if(!(window.NSG&&NSG.kakao)){fallback();note.hidden=false;note.textContent='네이버 검색에서 '+name+' 전화번호를 확인하세요.';return}
    b.disabled=true;b.textContent='번호 찾는 중…';
    loadKakao().then(function(){
      var ps=new kakao.maps.services.Places(),opt={};
      if(b.dataset.lat){opt.location=new kakao.maps.LatLng(+b.dataset.lat,+b.dataset.lng);opt.radius=300;opt.sort=kakao.maps.services.SortBy.DISTANCE}
      ps.keywordSearch(name,function(res,st){
        var hit=(st===kakao.maps.services.Status.OK)&&res.filter(function(r){return r.phone})[0];
        if(hit){var tel='tel:'+hit.phone.replace(/[^0-9]/g,''),a=document.createElement('a');a.className='btn dark call';a.href=tel;a.innerHTML='<span aria-hidden="true">☎</span> 바로 전화 <small>'+hit.phone+'</small>';b.replaceWith(a);
          note.hidden=false;note.textContent='카카오 지도에 등록된 번호로 연결해요.';location.href=tel;}
        else{b.disabled=false;b.textContent='네이버에서 번호 찾기';b.onclick=function(e){e.stopImmediatePropagation();fallback()};note.hidden=false;note.textContent='등록된 번호를 못 찾았어요.';}
      },opt);
    },function(){fallback()});
  })});
  // ---- 지도 (누를 때 불러오기)
  var mapEl=$('#map');
  if(mapEl){$('.map-load',mapEl).addEventListener('click',function(){
    var css=document.createElement('script');css.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';css.crossOrigin='';
    css.onload=function(){
      mapEl.innerHTML='';mapEl.classList.add('loaded');
      var pts=JSON.parse(mapEl.dataset.pts||'[]'),m=L.map(mapEl,{scrollWheelZoom:false});
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(m);
      var b=[];pts.forEach(function(p){b.push([p[0],p[1]]);
        L.marker([p[0],p[1]],{icon:L.divIcon({className:'',html:'<div class="mk">'+p[2]+'</div>',iconSize:[24,24]})}).addTo(m)
          .on('click',function(){var el=document.getElementById('s'+(p[2]-1));if(el)el.scrollIntoView({behavior:'smooth',block:'center'})});});
      if(b.length)m.fitBounds(b,{padding:[20,20]});
    };document.head.appendChild(css);
  })}
  // ---- 예약 답변 업체 (가입 업체)
  var mem=$('#members');
  if(mem&&window.NSG&&NSG.api){NSG.call('region_owners',{reg:mem.dataset.region,tr:mem.dataset.trade}).then(function(L){
    if(!L||!L.length)return;function e(t){return String(t==null?'':t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
    mem.hidden=false;mem.innerHTML='<h2 class="list-title">예약 답변 업체 <span class="muted">'+L.length+'곳</span></h2>'+L.map(function(o){
      return '<article class="shop member"><div class="shop-head"><h3>'+e(o.name)+'</h3><span class="tag ok">예약 답변 업체</span></div>'+
      '<p class="addr">'+(o.stars?'<b class="star">★ '+o.stars+'</b> · 업체 후기 '+o.reviews+'건':'아직 후기 없음')+(o.answered?' · 최근 30일 답변 '+o.answered+'건':'')+'</p>'+
      (o.price?'<p class="addr">'+e(o.price)+'</p>':'')+(o.last?'<p class="quote">“'+e(o.last)+'”</p>':'')+
      '<div class="actions two-btn">'+(o.phone?'<a class="btn dark" href="tel:'+e(o.phone.replace(/[^0-9]/g,''))+'">☎ 바로 전화</a>':'')+'<a class="btn blue" href="/요청/?t='+encodeURIComponent(mem.dataset.trade)+'&r='+encodeURIComponent(mem.dataset.region)+'">예약 요청</a></div></article>'}).join('')})}
  // ---- 첫 화면 검색 (업종 + 동네)
  var data=$('#regions'),q=$('#q'),out=$('#results');
  if(data&&q){var R=JSON.parse(data.textContent);
    function esc(t){return String(t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
    function show(list,empty){out.innerHTML=list.slice(0,8).map(function(r){return '<a class="res" href="'+r.u+'"><b>'+esc(r.n)+'</b><span>'+esc(r.s)+'</span></a>'}).join('')||'<p class="muted">'+(empty||'아직 열리지 않은 업종·동네예요. 곧 늘어나요.')+'</p>'}
    function find(v){v=v.replace(/\s/g,'');if(!v){out.innerHTML='';return}var words=v.match(/.{1,2}/g)||[];
      show(R.filter(function(r){var k=(r.k+r.n).replace(/\s/g,'');return k.indexOf(v)>=0||words.every(function(w){return k.indexOf(w)>=0})}))}
    q.addEventListener('input',function(){find(q.value)});
    $$('.qchip').forEach(function(c){c.addEventListener('click',function(){q.value=c.dataset.q;find(q.value)})});
    $('#near').addEventListener('click',function(){
      if(!navigator.geolocation){show([],'이 기기에서는 위치를 쓸 수 없어요.');return}
      navigator.geolocation.getCurrentPosition(function(p){var la=p.coords.latitude,lo=p.coords.longitude;
        show(R.filter(function(r){return r.lat}).sort(function(a,b){return Math.hypot(a.lat-la,a.lng-lo)-Math.hypot(b.lat-la,b.lng-lo)}))},function(){show([],'위치를 쓸 수 없어요. 업종이나 동네 이름으로 찾아 주세요.')});
    });
  }
})();
