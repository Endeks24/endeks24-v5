/* Endeks24 v5 yükleyici (harici dosya). Künye gibi sitenin özel kod alanını basmayan sayfalarda sayfa içeriğinden <script src> ile yüklenir (26.10.2026). */

/* Okur görünümü (v5 kapalıyken): e24-grafik bloklarında her adın yanına değeri sade metin olarak yazılır ("Sanayi: %3,37"). */
document.addEventListener('DOMContentLoaded',function(){try{
if(document.documentElement.classList.contains('e24v5'))return;
[].forEach.call(document.querySelectorAll('.e24-grafik'),function(g){
  var t=function(s){var e=g.querySelector(s);return e?e.textContent:'';},b=g.getAttribute('data-birim')||(/yüzde|%/i.test(t('.e24-g-baslik')+' '+t('.e24-g-kaynak'))?'%':'');
  var yaz=function(n){n=Number(n);if(isNaN(n))return '';var x=n.toLocaleString('tr-TR',{maximumFractionDigits:2});return b==='%'?'%'+x:x+(b?' '+b:'');};
  var ekle=function(el,n,on){if(!el||el.querySelector('.e24-g-okur'))return;var v=yaz(n);if(!v)return;var sp=document.createElement('span');sp.className='e24-g-okur';sp.textContent=on+v;el.appendChild(sp);};
  [].forEach.call(g.querySelectorAll('.e24-g-satir[data-deger]'),function(r){ekle(r,r.getAttribute('data-deger'),': ');});
  if(g.getAttribute('data-tur')==='pay'&&g.hasAttribute('data-deger')){b=b||'%';ekle(g.querySelector('.e24-g-baslik'),g.getAttribute('data-deger'),': ');}
});}catch(e){}});


(function(){try{
var d=document,H=d.documentElement,w=window,TABAN='https://cdn.jsdelivr.net/gh/Endeks24/endeks24-v5@{surum}/',ANAHTAR='https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/anahtar.json',GOMULU={yuzde:100,surum:'4485c5ba0cb44344d56c090d813690a3066c85cb'},GA='G-W0YYJNQPJ2';
function ls(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);return v;}catch(e){return null;}}
var q=location.search,m=q.match(/[?&]v5=([01])/),tercih=m?m[1]:ls('e24v5');if(m)ls('e24v5',m[1]);
var an=null;try{an=JSON.parse(ls('e24v5-anahtar')||'null');}catch(e){}
/* Z3: eski (16.10) yükleyici aynı kayda {h,t} yazar; o biçim de okunur (h: herkese açık) */
if(an&&an.yuzde==null&&typeof an.h==='boolean')an={yuzde:an.h?100:0,surum:an.surum};
if(!an||an.yuzde==null)an=GOMULU;
var surum=an.surum||GOMULU.surum,kova=ls('e24v5-kova');
if(kova===null||isNaN(+kova)){kova=String(Math.floor(Math.random()*100));if(ls('e24v5-kova',kova)===null)kova='99';}
function karar(y){return tercih==='1'||(tercih!=='0'&&+kova<+y);}
function dosya(f){return TABAN.replace('{surum}',surum)+f;}
/* Z13: anahtar.json başta istenir; paket ondaki sürümle yüklenir. Önbellekte günlerce kalan sayfada gömülü sürüm eskiyse (WhatsApp gibi her açılışı
   ilk ziyaret sayılan tarayıcılarda) yine güncel paket gelir. Anahtar 1,5 sn içinde gelmezse gömülü ya da saklı sürümle devam edilir. */
function anahtarAl(){return anahtarAl.p||(anahtarAl.p=fetch(ANAHTAR,{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}));}
var acik=karar(an.yuzde);
w.__e24v5={acik:acik,kova:+kova,yuzde:+an.yuzde,surum:surum};
/* Saha raporu (YAYIN-LISTESI): bütün GA olayları ve oturumlar v5 kovasıyla etiketlenir (sayfa/oturum ve reklam gösterimi kova bazında) */
function etiket(){if(typeof w.gtag!=='function')return;var g=acik?'acik':'kapali';w.gtag('set','user_properties',{v5_gorunum:g});w.gtag('set',{v5_gorunum:g,v5_surum:acik?surum:''});}
/* Sayfa yüklenince; bir kaynak asılı kalıp load olayı gecikirse en geç DOM hazır olduktan 6 sn sonra (ölçüm kaybolmasın) */
function sonra(f){var ok=0,c=function(){if(!ok){ok=1;f();}};w.addEventListener('load',c);d.addEventListener('DOMContentLoaded',function(){setTimeout(c,6000);});}
/* GA (V5): panelde GA kimliği boşaltıldığında gtag buradan, sayfa yüklendikten sonra yüklenir. gtag('js') ve config hemen kuyruğa girer,
   betik gelince sırayla işlenir. Okur sayfadan yüklenmeden ayrılırsa (sekme gizlenince) betik hemen istenir. Tema gtag'i hâlâ basıyorsa bu blok çalışmaz. */
if(GA&&!d.querySelector('script[src*="googletagmanager.com/gtag/js"]')){w.dataLayer=w.dataLayer||[];w.gtag=w.gtag||function(){w.dataLayer.push(arguments);};
  w.gtag('js',new Date());etiket();w.gtag('config',GA);
  var gy=function(){if(gy.ok)return;gy.ok=1;var g=d.createElement('script');g.async=true;g.src='https://www.googletagmanager.com/gtag/js?id='+GA;d.head.appendChild(g);};
  sonra(function(){setTimeout(gy,0);});d.addEventListener('visibilitychange',function(){if(d.visibilityState==='hidden')gy();});}
else etiket();
/* Sayfa türü (custom.js'teki kararla aynı; derle.py kurumsal adresleri ve Özel adresini kaynaktan yazar) */
function sayfaTuru(){var s=function(x){return d.querySelector(x);},y=location.pathname.replace(/\/+$/,'');
  if(s('.e24-borsa'))return 'kurumsal';
  if(["/kunye", "/haber-merkezi", "/analiz-ve-arastirma-kurulu", "/iletisim", "/kullanim-sartlari", "/cerez-politikasi"].indexOf(y)>=0&&(s('#bik-kunye-main')||s('.card.border-0.rounded-0.my-3.p-5')||s('#contactAjaxForm')))return 'kurumsal';
  if(s('main.index'))return 'ana';if(s('main .category-page'))return 'kategori';
  if(s('main.authors .author-list')||s('main .author-detail'))return 'yazarlar';
  if(s('main .infinite-item .article-header')&&s('main .infinite-item .article-text'))return 'kose';
  if(y==='/muhabir/14/endeks24-arastirma'&&s('main.editorindex .result-category'))return 'ozel';
  if(s('main.last-postsindex .last-posts-page'))return 'tum';
  if(s('main .infinite-item .post-header'))return 'haber';return '';}
/* kur(gec): v5'i kurar. gec=true: sayfa yüklendikten sonra (anahtar bu yüklemede açtıysa, Z3); o zaman d.write ve görsel ertelemesi yapılmaz. */
function kur(gec){
  /* X (18.10.2026): herkese açılışla önizleme rozeti kalkar (?v5=1 tercihi yine çalışır, rozet basılmaz). */
  H.classList.add('e24v5');
  /* Z27 (19.10.2026, Tebilişim gözlemi: eski tasarım bir an görünüp üstüne yenisi basılıyordu): v5 kurulana kadar sayfa görünmez.
     Güvenlik: v5'in yeniden kurmadığı sayfa türünde hemen, vazgeçince (e24v5 sınıfı kalkar) hemen, her durumda DOM hazır olduktan
     2,5 sn sonra ya da betik başladıktan 5 sn sonra tema görünür (sayfa hiçbir zaman boş kalmaz). */
  if(!gec){var gz=d.createElement('style');gz.id='e24v5-gizle';
    gz.textContent='html.e24v5:not(.e24v5-hazir):not(.e24v5-tema):not(.e24v5-goster) body{visibility:hidden!important}';d.head.appendChild(gz);
    var goster=function(){H.classList.add('e24v5-goster');};setTimeout(goster,5000);
    d.addEventListener('DOMContentLoaded',function(){setTimeout(goster,2000);if(!({"ana": "ana", "kategori": "kategori", "ozel": "kategori", "tum": "kategori", "yazarlar": "kose", "kose": "kose", "kurumsal": "kurumsal", "haber": "haber"}[sayfaTuru()]))goster();});}
  /* V3: v5 Font Awesome kullanmaz (simgeler satır içi SVG). Tema Font Awesome ve hava durumu yazı tiplerini başlıkta preload ile istediği için
     bu dosyalar burada engellenemez; preload satırlarının kaldırılması Tebilişim'den istendi. */
  if(!gec)d.write('<link rel="preconnect" href="'+TABAN.replace(/^(https?:\/\/[^\/]+).*$/,'$1')+'" crossorigin><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>');
  /* Görsel önceliği: ayrıştırıcı gövdeye geçince temanın bütün görselleri (kaydırıcı slaytları, kartlar) aynı anda istenir ve manşet görseli
     bant genişliğini onlarla paylaşır. v5 bu görsellerin çoğunu göstermez (kartlar kendi boyutunu ister). Bu yüzden ana içerikteki görsellerin
     adresi, manşet görseli ve fetchpriority=high görsel dışında, data-src'ye alınır: v5'e taşınanlar kurulumda geri açılır (custom.js gorselOnar),
     gizli temada kalanlar hiç inmez. v5 kurulmazsa ya da sayfa yeniden kurulmuyorsa adresler geri yazılır. Reklam alanları ve reklam görselleri
     ertelemenin dışındadır, hiç dokunulmaz (X: reklam süresi v5 açık ve kapalı aynı).
     (Kategori manşetinin ilk görseli temada loading=lazy; bu ancak temada düzeltilebilir, Tebilişim'den istendi.) */
  var tut=function(r){if(r.hasAttribute('data-e24y')||r.getAttribute('fetchpriority')==='high')return;var m0=d.querySelector('.main-headline .swiper-slide img');if(r===m0)return;
    var u=r.getAttribute('src');if(!u||/^data:/.test(u))return;r.setAttribute('data-e24y','');if(!r.getAttribute('data-src'))r.setAttribute('data-src',u);r.removeAttribute('src');
    if(r.getAttribute('srcset')){r.setAttribute('data-e24ss',r.getAttribute('srcset'));r.removeAttribute('srcset');}};
  var birak=function(){[].forEach.call(d.querySelectorAll('img[data-e24y]'),function(r){if(!r.getAttribute('src'))r.setAttribute('src',r.getAttribute('data-src'));
    if(r.getAttribute('data-e24ss'))r.setAttribute('srcset',r.getAttribute('data-e24ss'));r.removeAttribute('data-e24y');});};
  if(!gec)try{var mo=new MutationObserver(function(){
      [].forEach.call(d.querySelectorAll('main img:not([data-e24t])'),function(r){r.setAttribute('data-e24t','');
        if(!r.closest('.widget-advert'))tut(r);});});
    mo.observe(H,{childList:true,subtree:true});d.addEventListener('DOMContentLoaded',function(){mo.takeRecords();mo.disconnect();});}catch(e){}
  /* Vazgeçince v5 kurulumu bir daha başlamaz (__e24v5k) ve v5 CSS'i kaldırılır; geç gelen dosya yarım tasarım kuramaz. Neden saklanır ve GA'ya yazılır. */
  var vazgec=function(n){if(w.__e24v5k===1&&!H.classList.contains('e24v5'))return;H.classList.remove('e24v5');w.__e24v5k=1;birak();
    [].forEach.call(d.querySelectorAll('link[id^="e24v5-css"]'),function(l){l.parentNode.removeChild(l);});
    var z=typeof n==='string'?n:'hata';ls('e24v5-vazgec',z+'@'+Date.now());if(typeof w.gtag==='function')w.gtag('event','v5_vazgec',{neden:z,non_interaction:true});};
  var ekle=function(t,o){var e=d.createElement(t);for(var k in o)e[k]=o[k];d.head.appendChild(e);return e;};
  /* Z29 (26.10.2026, "site zaman zaman eski tasarıma dönüyor"): dosya 3 sn içinde gelmezse (yavaş ya da kesintili mobil ağ, CDN kesintisi) ya da
     hata verirse eskiden hemen vazgeçilir, ziyaretçi o sayfada eski temada kalırdı. Şimdi aynı dosya sırayla yedek CDN adreslerinden (aynı depo,
     aynı değişmez etiket) yeniden istenir; her adrese 4 sn tanınır, hepsi başarısızsa 12 sn sonunda vazgeçilir. */
  var HOST=TABAN.replace(/^(https?:\/\/[^\/]+).*$/,'$1'),YEDEK=[HOST,'https://fastly.jsdelivr.net','https://gcore.jsdelivr.net'];
  var kritik=function(t,o,f){var i=0,ok=0,e=null,tm=0,dene=function(){if(ok||w.__e24v5k===1&&!H.classList.contains('e24v5'))return;
      if(e&&e.parentNode)e.parentNode.removeChild(e);
      var x=d.createElement(t);for(var k in o)x[k]=o[k];x[t==='link'?'href':'src']=dosya(f).replace(HOST,YEDEK[i]);
      x.addEventListener('load',function(){ok=1;clearTimeout(tm);});
      x.addEventListener('error',function(){if(ok)return;clearTimeout(tm);ilerle();});
      e=x;d.head.appendChild(x);tm=setTimeout(function(){if(!ok)ilerle();},4000);},
      ilerle=function(){if(++i<YEDEK.length)dene();else if(!ok)vazgec('dosya:'+f);};
    dene();return {tamam:function(){return ok;}};};
  /* Dosyalar sayfanın ana görseli (LCP) indikten sonra istenir, en geç DOM hazır olduktan 6 sn sonra. CSS'ler media=print ile (render'ı
     bekletmez), etkinleştirmeyi v5 kurulumu yapar. CSS sayfa türü başına tek dosya; JS ortak paket ve sayfa paketi. Sayfa türü bilinmiyorsa
     (v5'in yeniden kurmadığı sayfa) tema.css ve ortak.js. */
  var yukle=function(){if(yukle.ok)return;yukle.ok=1;var bitti=0,git=function(o){if(bitti)return;bitti=1;
      if(o&&o.surum&&o.yuzde!=null&&karar(o.yuzde)){surum=o.surum;w.__e24v5.surum=surum;}baslat();};
    anahtarAl().then(git);setTimeout(git,800);};
  var baslat=function(){
    var tur=sayfaTuru(),pk={"ana": "ana", "kategori": "kategori", "ozel": "kategori", "tum": "kategori", "yazarlar": "kose", "kose": "kose", "kurumsal": "kurumsal", "haber": "haber"}[tur]||'';w.__e24v5.sayfa=tur;w.__e24v5.paket=pk;
    if(!pk)birak();
    ekle('link',{rel:'stylesheet',media:'print',id:'e24v5-font',href:'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400..700&family=Source+Serif+4:opsz,wght@8..60,400..700&display=swap'});
    var css=kritik('link',{rel:'stylesheet',media:'print',id:'e24v5-css',crossOrigin:'anonymous'},(pk||'tema')+'.css');
    var pj=pk?kritik('script',{async:true,crossOrigin:'anonymous'},pk+'.js'):null,oj=kritik('script',{async:true,crossOrigin:'anonymous'},'ortak.js');
    /* Sayfa gizli beklerken (5 sn) görseller geri açılır: v5 geç kurulsa da okur boş görsel görmez. */
    setTimeout(function(){if(!H.classList.contains('e24v5-hazir')&&!H.classList.contains('e24v5-tema'))birak();},5000);
    /* X: CSS, ortak paket ve sayfa paketi 13 sn içinde kurulmazsa vazgeçilir: sayfa eski temada kalır. */
    setTimeout(function(){if(H.classList.contains('e24v5-hazir')||H.classList.contains('e24v5-tema'))return;
      if(!css.tamam()||!w.__e24v5k||(pk&&!w.__e24v5p))vazgec('zaman');},13000);};
  if(gec)return yukle();
  /* Z27: tema görünmez beklediği için dosyalar ana görseli beklemeden, DOM hazır olunca istenir (görsel ertelemesi sürer) */
  d.addEventListener('DOMContentLoaded',yukle);
  /* Z28 (24.10.2026, Tebilişim gözlemi: sayfa gizli beklerken dosyalar DOM hazır olunca isteniyordu): sayfa türü anlaşılır anlaşılmaz
     (ana içeriğin ilk öğeleri ayrıştırılınca) dosyalar hemen istenir; yavaş ağda DOM hazır olması saniyelerce sürebilir. Tür anlaşılmazsa
     (v5'in yeniden kurmadığı sayfa) eskisi gibi DOM hazır beklenir. */
  try{var erken=function(){if(yukle.ok)return true;try{if(sayfaTuru()){mo2.disconnect();yukle();return true;}}catch(e){}return false;};
    var mo2=new MutationObserver(erken);mo2.observe(H,{childList:true,subtree:true});d.addEventListener('DOMContentLoaded',function(){mo2.disconnect();});erken();}catch(e){}
}
if(acik){anahtarAl();kur(false);}
/* Uzak anahtar (anahtar.json, dal adresi; kısa önbellek ve purge): sonraki sayfalar için saklanır. Bu sayfa açıkken anahtar kapatıldıysa
   (acil kapatma) sayfa bir kez yeniden yüklenir. */
sonra(function(){setTimeout(function(){
  anahtarAl().then(function(o){
    if(!o||o.yuzde==null)return;
    /* h: önbellekteki eski sayfaların yükleyicisi de okur (köprü kodu tarayıcıda varsa; yoksa o yükleyici ana sayfadan alır) */
    var kodVar=false;try{kodVar=!!JSON.parse(ls('e24v5-kod')||'null');}catch(e){}
    var kay={yuzde:+o.yuzde,surum:o.surum||surum,t:Date.now()};if(kodVar)kay.h=+o.yuzde>=100;
    if(ls('e24v5-anahtar',JSON.stringify(kay))===null)return;
    /* Z3: sayfa kapalı açıldıysa (gömülü yüzde ya da eski kayıt) ve anahtar açıyorsa v5 bu sayfada hemen kurulur */
    if(!acik&&karar(o.yuzde)){acik=true;surum=o.surum||surum;w.__e24v5.acik=true;w.__e24v5.surum=surum;etiket();kur(true);return;}
    try{if(acik&&!karar(o.yuzde)&&!sessionStorage.getItem('e24v5-yy')){sessionStorage.setItem('e24v5-yy','1');location.reload();}}catch(e){}
  }).catch(function(){});
  /* Reklam gösterimi (saha raporu): reklam alanı en az yarısı 1 sn görünür kalınca bir kez "reklam_gorunum" olayı (v5 açık ve kapalı aynı ölçüt) */
  try{var rg=new IntersectionObserver(function(l){l.forEach(function(x){var e=x.target;if(x.intersectionRatio>=0.5){if(!e.__rz)e.__rz=setTimeout(function(){rg.unobserve(e);
      if(typeof w.gtag==='function')w.gtag('event','reklam_gorunum',{reklam_yeri:(e.className||'').toString().split(' ')[0],non_interaction:true});},1000);}
    else if(e.__rz){clearTimeout(e.__rz);e.__rz=0;}});},{threshold:[0,0.5]});
    var rgTara=function(){[].forEach.call(d.querySelectorAll('.widget-advert,.v5-reklam300,.v5-reklam-genis'),function(e){if(!e.__rg&&(e.querySelector('img,iframe,ins'))){e.__rg=1;rg.observe(e);}});};
    rgTara();setTimeout(rgTara,4000);setTimeout(rgTara,10000);}catch(e){}
  /* Gerçek ziyaretçi ölçümü (U6): LCP, CLS, INP GA4'e olay olarak; v5 açık ve kapalı ayrı etiketli */
  var s=d.createElement('script');s.src=dosya('web-vitals.js');s.async=true;s.addEventListener('load',function(){try{
    var gonder=function(x){if(typeof w.gtag!=='function')return;w.gtag('event',x.name,{value:Math.round(x.name==='CLS'?x.delta*1000:x.delta),metric_id:x.id,metric_value:x.value,metric_rating:x.rating,v5_gorunum:acik?'acik':'kapali',v5_surum:acik?surum:'',non_interaction:true});};
    w.webVitals.onLCP(gonder);w.webVitals.onCLS(gonder);w.webVitals.onINP(gonder);}catch(e){}});
  d.head.appendChild(s);},1500);});
}catch(e){}})();
