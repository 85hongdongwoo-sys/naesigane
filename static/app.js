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
      var S=kakao.maps.services,ps=new S.Places();
      function q(kw,rad){return new Promise(function(res){var o={radius:rad,sort:S.SortBy.DISTANCE};if(b.dataset.lat)o.location=new kakao.maps.LatLng(+b.dataset.lat,+b.dataset.lng);ps.keywordSearch(kw,function(d,st){res(st===S.Status.OK?d.filter(function(x){return x.phone}):[])},o)})}
      function clean(n){return n.replace(/\(주\)|㈜|주식회사|\(합\)|\(1급\)/g,'').replace(/\([^)]*\)/g,' ').replace(/\s+/g,' ').trim()}
      function done(hit,sure){
        if(!hit){b.disabled=false;b.innerHTML='<span aria-hidden="true">☎</span> '+(b.classList.contains('sm')?'번호 찾기':'네이버에서 번호 찾기');b.onclick=function(e){e.stopImmediatePropagation();fallback()};note.hidden=false;note.textContent='등록된 번호를 못 찾았어요.';return}
        var tel='tel:'+hit.phone.replace(/[^0-9]/g,''),a=document.createElement('a');a.className=b.className.replace('lookup','').trim();a.href=tel;a.innerHTML='<span aria-hidden="true">☎</span> 전화';b.replaceWith(a);note.hidden=false;
        if(sure){note.textContent='☎ '+hit.phone+' (카카오 지도 등록 번호)로 연결해요.';location.href=tel}
        else note.textContent='같은 자리의 \''+hit.place_name+'\' 번호('+hit.phone+')예요. 맞으면 \'전화\'를 누르세요.';
      }
      (async function(){
        var r=await q(name,300);if(r.length)return done(r[0],true);
        r=await q(clean(name),500);if(r.length)return done(r[0],true);
        var kws=b.dataset.car?['자동차정비','카센터','공업사','타이어']:[];
        for(var i=0;i<kws.length;i++){r=(await q(kws[i],40)).filter(function(x){return +x.distance<=40&&/자동차/.test(x.category_name)});if(r.length)return done(r[0],false)}
        done(null);
      })();
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
  // ---- 안내 페이지: 동네 업체 실시간 목록 (카카오, 저장하지 않음)
  var live=$('.live-shops');
  if(live){
    var list=$('.live-list',live),moreB=$('.live-more',live);
    function esc2(t){return String(t||'').replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
    function none(msg){list.innerHTML='<p class="muted">'+msg+'</p>'}
    var started=false;
    function start(){if(started)return;started=true;
      loadKakao().then(function(){
        var mustRe=live.dataset.must?new RegExp(live.dataset.must):null,S=kakao.maps.services,ps=new S.Places(),kws=live.dataset.kw.split('|'),gu=live.dataset.gu,area=live.dataset.area,seen={},all=[],near=[];
        var o={size:15};if(live.dataset.lat){o.location=new kakao.maps.LatLng(+live.dataset.lat,+live.dataset.lng);o.radius=20000}
        function one(kw,page,plain){return new Promise(function(res){ps.keywordSearch(plain?kw:area+' '+kw,function(d,st){res(st===S.Status.OK?d:[])},Object.assign({page:page},o))})}
        (async function(){
          function take(d){d.forEach(function(x){var ad=(x.road_address_name||x.address_name||'');if(!x.phone||seen[x.id]||x.category_group_code||/공원|학교|아파트|주차장|음식|카페/.test(x.category_name||'')||(mustRe&&!mustRe.test(x.place_name+' '+(x.category_name||''))))return;seen[x.id]=1;if(ad.indexOf(gu)>=0)all.push(x);else near.push(x)})}
          for(var i=0;i<kws.length;i++){for(var pg=1;pg<=2;pg++){var d=await one(kws[i],pg);
            d.forEach(function(x){var ad=(x.road_address_name||x.address_name||'');if(!x.phone||seen[x.id]||x.category_group_code||/공원|학교|아파트|주차장|음식|카페/.test(x.category_name||'')||(mustRe&&!mustRe.test(x.place_name+' '+(x.category_name||''))))return;seen[x.id]=1;if(ad.indexOf(gu)>=0)all.push(x);else near.push(x)});
            if(d.length<15)break}}
          if(all.length+near.length<5&&o.location){for(var j=0;j<kws.length;j++)take(await one(kws[j],1,true))}
          if(all.length<5){near.sort(function(p,q){return (+p.distance||9e9)-(+q.distance||9e9)});near.slice(0,10-all.length).forEach(function(x){x._near=1;all.push(x)})}
          if(!all.length)return none('카카오 지도에서 '+esc2(area)+' 업체를 찾지 못했어요. 아래 네이버 검색으로 찾아보세요.');
          var shown=0;
          function card(x,i){var cat=(x.category_name||'').split('>').pop().trim(),ad=x.road_address_name||x.address_name,
              nav='https://map.naver.com/p/search/'+encodeURIComponent(x.place_name+' '+ad);
            return '<article class="shop"><div class="shop-head"><span class="pin" aria-hidden="true">'+(i+1)+'</span><h3>'+esc2(x.place_name)+'</h3></div>'+
              '<p class="addr">'+esc2(ad.split(' ').slice(2).join(' ')||ad)+'</p>'+'<div class="chips">'+(cat?'<span class="chip">'+esc2(cat)+'</span>':'')+(x._near?'<span class="chip">가까운 지역 · '+esc2(ad.split(' ').slice(0,2).join(' '))+'</span>':'')+'</div>'+
              '<p class="tel">☎ '+esc2(x.phone)+'</p>'+
              '<div class="actions act3"><a class="btn book" href="/요청/?t='+encodeURIComponent(live.dataset.trade||'')+'&r='+encodeURIComponent(live.dataset.region||'')+'&s='+encodeURIComponent(x.place_name)+'">예약 요청<span class="dev">개발 중</span></a>'+
              '<a class="btn ghost sm call" href="tel:'+esc2(x.phone.replace(/[^0-9]/g,''))+'"><span aria-hidden="true">☎</span> 전화</a>'+
              '<a class="btn ghost sm" href="'+esc2(nav)+'" target="_blank" rel="noopener">길찾기</a></div></article>'}
          function more(){var next=all.slice(shown,shown+10);list.insertAdjacentHTML('beforeend',next.map(function(x,j){return card(x,shown+j)}).join(''));shown+=next.length;moreB.hidden=shown>=all.length}
          list.innerHTML='';more();moreB.addEventListener('click',more);
        })();
      },function(){none('지금은 업체 목록을 불러올 수 없어요. 아래 네이버 검색으로 찾아보세요.')});
    }
    if(!(window.NSG&&NSG.kakao))none('아래 네이버 검색으로 업체를 찾아보세요.');
    else if('IntersectionObserver' in window){var io=new IntersectionObserver(function(e){if(e[0].isIntersecting){io.disconnect();start()}},{rootMargin:'300px'});io.observe(live)}
    else start();
  }
  // ---- 첫 화면 검색 (업종 + 동네)
  var data=$('#regions'),q=$('#q'),out=$('#results');
  if(data&&q){var R=JSON.parse(data.textContent);if(data.dataset.src){fetch(data.dataset.src).then(function(r){return r.json()}).then(function(j){R=j;if(q.value)find(q.value)})}
    function esc(t){return String(t).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
    function show(list,empty){out.innerHTML=list.slice(0,8).map(function(r){return '<a class="res" href="'+r.u+'"><b>'+esc(r.n)+'</b><span>'+esc(r.s)+'</span></a>'}).join('')||'<p class="muted">'+(empty||'아직 열리지 않은 업종·동네예요. 곧 늘어나요.')+'</p>'}
    function find(raw){var v=raw.replace(/\s/g,'');if(!v){out.innerHTML='';return}
      var parts=raw.trim().split(/\s+/),chunks=v.match(/.{1,2}/g)||[];
      show(R.filter(function(r){var k=(r.k+r.n).replace(/\s/g,'');return k.indexOf(v)>=0||parts.every(function(w){return k.indexOf(w)>=0})||(parts.length==1&&chunks.every(function(w){return k.indexOf(w)>=0}))}))}
    q.addEventListener('input',function(){find(q.value)});
    $$('.qchip').forEach(function(c){c.addEventListener('click',function(){q.value=c.dataset.q;find(q.value)})});
    $('#near').addEventListener('click',function(){
      if(!navigator.geolocation){show([],'이 기기에서는 위치를 쓸 수 없어요.');return}
      navigator.geolocation.getCurrentPosition(function(p){var la=p.coords.latitude,lo=p.coords.longitude;
        show(R.filter(function(r){return r.lat}).sort(function(a,b){return Math.hypot(a.lat-la,a.lng-lo)-Math.hypot(b.lat-la,b.lng-lo)}))},function(){show([],'위치를 쓸 수 없어요. 업종이나 동네 이름으로 찾아 주세요.')});
    });
  }
})();
