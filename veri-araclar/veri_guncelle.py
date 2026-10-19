"""Veri Masası aracı: e24-veri JSON'unu paneldeki "v5 6-veri" widget'ına yazar.

İlk giriş (bir kişi):   python3 veri_guncelle.py --ilk-giris --oturum ./oturum.json
Veri yazma:             python3 veri_guncelle.py veri.json --etkilesimsiz --oturum ./oturum.json
Oturumu canlı tutma:    python3 veri_guncelle.py --tazele --oturum ./oturum.json
Yalnız doğrulama:       python3 veri_guncelle.py veri.json --kuru
Canlı veriyi okuma:     python3 veri_guncelle.py --canli-oku canli.json   (ana sayfadaki e24-veri, -2, -3 birleşik; oturum gerekmez)
3 şey:                  python3 veri_guncelle.py --3sey maddeler.json --oturum ./oturum.json
                        (17.10.2026: asıl kaynak e24-veri "ucsey" tablosu, veri.json ile yazılır; widget yalnız
                        24 saat içinde yazılmışsa ve ucsey yoksa kullanılır, ikisi de yoksa sayfa maddeleri kendisi seçer)
                        (17.10.2026 AA: piyasa.hareket yukselenler/dusenler/hacim/genislik ve kap.genel_kurul tabloları;
                        alanlar E24-VERI-SEMASI.md'de, doğrulama veri_sema.py ile)

Adımlar:
1. JSON'u E24-VERI-SEMASI.md şemasına göre doğrular; uymayan veri hiç yazılmaz.
2. Oturum dosyasıyla panele bağlanır; oturumun izinli hesaba ait olduğunu denetler.
3. Widget düzeninin tarihli yedeğini yedek/ altına alır (depodaysa commit eder).
4. Yalnız "v5 6-veri" widget'larının içeriğini değiştirir. 18.10.2026: panel bir widget'ta yaklaşık 51 bin karakterden
   fazlasını kaydetmiyor (500 hatası). Veri en büyük tablodan başlanarak "v5 6-veri", "v5 6-veri-2", "v5 6-veri-3"
   widget'larına bölünür (her biri en çok SINIR karakter); sayfa üçünü birleştirerek okur. Tek tablo SINIR'ı aşarsa yazılmaz.
   Ek widget'lar bir kez kurulur: python3 veri_guncelle.py --ek-widget-kur --oturum ./oturum.json
5. Yazdıktan sonra widget düzenini yedekle karşılaştırır (yalnız rastgele form kimlikleri yok sayılır).
   Başka fark varsa eski hale döndürür ve hata verir.

Oturum dosyası: --oturum ile verilir (yoksa E24_OTURUM, o da yoksa ~/.e24/oturum.json). Dosya yalnız çerezleri
JSON olarak tutar; e-posta, şifre ve 2FA kodu hiçbir zaman yazılmaz.
Hesap denetimi: oturum yalnız izinli hesaba aitse kaydedilir ve kullanılır: genel yayın yönetmeninin hesabı (panel
kullanıcı 8; "Veri Masası" kullanıcısı panele ayrı giriş yapamadığı için, 16.10.2026 kararı) ya da adı "Veri Masası"
olan hesap. Başka bir hesabın oturumu kaydedilmez ve onunla veri yazılmaz; --ilk-giris'te o oturum hemen kapatılır.
Panel oturumu her istekte 24 saat uzar; --tazele en az günde bir kez çalışırsa giriş bir daha gerekmez.
--etkilesimsiz: hiçbir şey sormaz; oturum kapalıysa veri yazmadan çıkar.
Çıkış kodları: 0 başarı, 1 hata (veri yazılmadı ya da geri alındı), 2 oturum kapalı (bir kişi --ilk-giris yapmalı).
Dosyalar tek klasörde de çalışır (veri_guncelle.py ile veri_sema.py yan yana); yedek o klasörün yedek/ altına yazılır.
"""
import sys, os, re, json, html, getpass, datetime, subprocess
from urllib.parse import urlencode

import requests

BURA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURA)
from veri_sema import dogrula  # noqa: E402
# Depoda araclar/ altındaysa yedek depo kökündeki yedek/ klasörüne, tek klasörde ise yanındaki yedek/ klasörüne
D = os.path.dirname(BURA) if os.path.basename(BURA) == 'araclar' else BURA
ETKILESIMSIZ = '--etkilesimsiz' in sys.argv


def arg(ad):
    i = sys.argv.index(ad) + 1 if ad in sys.argv else 0
    return sys.argv[i] if 0 < i < len(sys.argv) else None


SITE = 'https://www.endeks24.com'
B = SITE + '/xpanel'
OTURUM = arg('--oturum') or os.environ.get('E24_OTURUM') or os.path.expanduser('~/.e24/oturum.json')
# İzinli hesaplar: panel kullanıcı 8 (genel yayın yönetmeni; Veri Masası ayrı giriş yapamadığı için) ya da "Veri Masası"
IZINLI_ID = {'8'}
IZINLI_AD = 'Veri Masası'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
ALAN = 'home_bottom_section'
TEXT = 'TE\\Widget\\Widgets\\Text'
SINIF = 'e24v5-widget'
AD = 'v5 6-veri'
# Veri parçaları: (widget adı, script kimliği); SINIR: bir widget'a yazılan JSON'un en çok karakter sayısı (panel ~51 bin'de 500 veriyor)
PARCALAR = [('v5 6-veri', 'e24-veri'), ('v5 6-veri-2', 'e24-veri-2'), ('v5 6-veri-3', 'e24-veri-3')]
SINIR = 47000


def hata(m, kod=1):
    print('HATA:', m)
    sys.exit(kod)


def oturum(bos=False):
    s = requests.Session()
    s.headers['User-Agent'] = UA
    s.hesap_tamam = False
    if not bos and os.path.exists(OTURUM):
        try:
            # Bitiş saati yok sayılır: oturumun açık olup olmadığına panel karar verir (kapalıysa giris() 2 ile çıkar).
            # Böylece tazelenen oturum.json'u Drive'a geri yüklemek gerekmez.
            for c in json.load(open(OTURUM, encoding='utf-8'))['cerezler']:
                s.cookies.set(c['ad'], c['deger'], domain=c['alan'], path=c['yol'], secure=c.get('guvenli', True))
        except Exception as e:
            hata(f'Oturum dosyası okunamadı ({OTURUM}): {e}', 2)
    return s


def hesap(h):
    """Panel sayfasından oturumdaki kullanıcının numarası ve adı."""
    m = re.search(r'/xpanel/system/users/profile/(\d+)', h)
    a = re.search(r'<h5 class="m-b-0">([^<]*)</h5>', h)
    return (m.group(1) if m else None), (html.unescape(a.group(1)).strip() if a else None)


def hesap_denetle(s, h):
    kid, ad = hesap(h)
    tamam = kid is not None and (kid in IZINLI_ID or (ad or '').casefold() == IZINLI_AD.casefold())
    s.hesap_tamam = tamam
    return tamam, ad


def kaydet(s):
    if not s.hesap_tamam:
        hata('Oturum izinli bir hesaba ait değil, kaydedilmedi.')
    os.makedirs(os.path.dirname(os.path.abspath(OTURUM)), exist_ok=True)
    cerez = [{'ad': c.name, 'deger': c.value, 'alan': c.domain, 'yol': c.path, 'bitis': c.expires, 'guvenli': c.secure}
             for c in s.cookies if c.domain.endswith('endeks24.com')]
    t = OTURUM + '.tmp'
    fd = os.open(t, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'kayit': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'cerezler': cerez}, f)
    os.replace(t, OTURUM)


def jeton(h):
    m = re.search(r'name="_token"[^>]*value="([^"]+)"', h)
    return m.group(1) if m else ''


def giris(s):
    """Oturum açık ve izinli hesabınsa uzatıp kaydeder; kapalıysa 2, başka hesabınsa 1 ile çıkar."""
    r = s.get(B + '/widgets')
    if '/login' in r.url:
        hata('Panel oturumu kapalı. Bir kişi --ilk-giris ile giriş yapmalı; veri yazılmadı.', 2)
    tamam, ad = hesap_denetle(s, r.text)
    if not tamam:
        hata(f'Bu oturum "{ad or "?"}" hesabına ait, bu hesap izinli değil; kaydedilmedi, veri yazılmadı.')
    kaydet(s)


def ilk_giris():
    """E-posta, şifre ve 2FA kodunu ekrandan ister; hiçbirini yazmaz, yalnız izinli hesabın çerezini kaydeder."""
    if ETKILESIMSIZ:
        hata('--ilk-giris yalnız bir kişi başındayken çalışır.')
    s = oturum(bos=True)
    print(f'Panel girişi. Oturum dosyası: {OTURUM}')
    eposta = input('Panel e-postası: ').strip()
    sifre = getpass.getpass('Şifre: ')
    h = s.get(B + '/login').text
    r = s.post(B + '/login', data={'_token': jeton(h), 'email': eposta, 'password': sifre, 'remember': '1'}, headers={'Referer': B + '/login'})
    del sifre
    if '/login/2fa' in r.url:
        kod = getpass.getpass('2FA kodu (6 hane): ').strip()
        r = s.post(B + '/login/2fa', data={'_token': jeton(r.text), 'totp': kod}, headers={'Referer': B + '/login/2fa'})
        del kod
    if '/login' in r.url:
        return mevcutla_devam('Giriş başarısız (e-posta, şifre ya da 2FA kodu kabul edilmedi).')
    tamam, ad = hesap_denetle(s, s.get(B + '/widgets').text)
    if not tamam:
        s.get(B + '/logout')  # yanlış hesabın oturumu hemen kapatılır
        return mevcutla_devam(f'Giriş yapılan hesap "{ad or "?"}" izinli değil; o oturum kapatıldı.')
    kaydet(s)
    print(f'TAMAM. "{ad}" oturumu kaydedildi: {OTURUM}')


def mevcutla_devam(neden):
    """Yeni giriş olmazsa dosyadaki oturum geçerliyse onunla devam edilir; dosyaya dokunulmaz, yalnız süresi uzar."""
    print('UYARI:', neden)
    if not os.path.exists(OTURUM):
        hata('Kayıtlı oturum da yok; hiçbir şey kaydedilmedi.', 2)
    print('Kayıtlı oturum deneniyor:', OTURUM)
    giris(oturum())  # kapalıysa 2, başka hesabınsa 1 ile çıkar
    print('TAMAM. Mevcut oturum geçerli, onunla devam ediliyor (24 saat uzadı).')


def durum(s):
    r = s.get(B + '/widgets')
    if '/login' in r.url:
        hata('Oturum kapandı, veri yazılmadı. Bir kişi --ilk-giris ile giriş yapmalı.', 2)
    h = r.text
    k = 'window.__WIDGET_BOOTSTRAP__ = '
    d, _ = json.JSONDecoder().raw_decode(h[h.index(k) + len(k):])
    tok = re.search(r'name="csrf-token" content="([^"]+)"', h).group(1)
    return d, tok


def deger(form_html, ad):
    m = re.search(r'<textarea name="%s"[^>]*>(.*?)</textarea>' % ad, form_html, re.S)
    if m:
        return html.unescape(m.group(1))
    m = re.search(r'name="%s" value="([^"]*)"' % ad, form_html)
    return html.unescape(m.group(1)) if m else None


def ogeler(widgetlar, yeni_icerik=None, hedef_ad=None):
    hedef_ad = hedef_ad or AD
    out = []
    for w in widgetlar:
        ad, icerik = deger(w['form_html'], 'name'), deger(w['form_html'], 'content')
        if ad == hedef_ad and yeni_icerik is not None:
            icerik = yeni_icerik
        out.append(urlencode([('id', TEXT), ('name', ad), ('content', icerik), ('class', SINIF),
                              ('is_mobile', w.get('is_mobile') or 1), ('is_desktop', w.get('is_desktop') or 1)]))
    return out


def yaz(s, d, tok, items):
    r = s.post(SITE + d['routes']['save'], data=[('sidebar_id', ALAN)] + [('items[]', i) for i in items],
               headers={'X-CSRF-TOKEN': tok, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json', 'Referer': B + '/widgets'})
    kaydet(s)
    return r


def norm(x):
    # Panel form_html içinde her açılışta rastgele kimlik üretir (13 haneli onaltılık); yalnız bunlar yok sayılır
    return re.sub(r'[0-9a-f]{13}', 'X', json.dumps(x, sort_keys=True))

# ---------- Bugün bilmeniz gereken 3 şey ("v5 1-3sey" widget'ı) ----------
UC_AD = 'v5 1-3sey'
UC_SABLON = """<section class="e24v5-blok e24v5-3sey" data-e24v5="3sey" hidden>
<div class="e24v5-3sey-bas"><h2>Bugün bilmeniz gereken 3 şey</h2><time class="e24v5-tarih"></time></div>
<ol>
{maddeler}<!-- İÇERİK BEKLİYOR (her gün Yayın Masası): en fazla 3 madde, yalnızca yayımlanmış haberler.
<li><a href="/HABER-ADRESI"><span>ETİKET</span>Haber başlığı</a></li>
-->
</ol>
</section>"""
TR = datetime.timezone(datetime.timedelta(hours=3))


def uc_oku(icerik):
    """Widget içeriğinden maddeler ve aracın işareti (son yazım zamanı, maddelerin özeti)."""
    ol = re.sub(r'<!--.*?-->', '', icerik or '', flags=re.S)
    m = [{'link': html.unescape(a), 'etiket': html.unescape(e).strip(), 'baslik': html.unescape(b).strip()}
         for a, e, b in re.findall(r'<li><a href="([^"]+)"><span>(.*?)</span>(.*?)</a></li>', ol, re.S)]
    isaret = re.search(r'<!-- e24-3sey-arac zaman=(\S+) ozet=(\w+) -->', icerik or '')
    return m, (isaret.group(1), isaret.group(2)) if isaret else None


def uc_ozet(maddeler):
    import hashlib
    return hashlib.sha1(json.dumps([[x['link'], x['etiket'], x['baslik']] for x in maddeler], ensure_ascii=False).encode()).hexdigest()[:12]


def uc_yaz_icerik(maddeler):
    li = ''.join('<li><a href="%s"><span>%s</span>%s</a></li>\n' % (html.escape(x['link'], quote=True), html.escape(x['etiket'], quote=False), html.escape(x['baslik'], quote=False)) for x in maddeler)
    zaman = datetime.datetime.now(TR).isoformat(timespec='minutes')
    return UC_SABLON.format(maddeler=li) + '\n<!-- e24-3sey-arac zaman=%s ozet=%s -->' % (zaman, uc_ozet(maddeler))


def uc_haber(s, link):
    """Adres sitede 200 dönüyor ve yayımlanmış bir haber mi? Yayın zamanını döndürür; değilse hata metni."""
    yolu = re.sub(r'^https?://(www\.)?endeks24\.com', '', link.strip())
    if not re.fullmatch(r'/[a-z0-9-]{8,}', yolu):
        return None, yolu, 'adres /haber-adresi biçiminde olmalı'
    try:
        r = s.get(SITE + yolu, allow_redirects=False, timeout=30)
    except Exception as e:
        return None, yolu, f'açılamadı ({e.__class__.__name__})'
    if r.status_code != 200:
        return None, yolu, f'{r.status_code} döndü'
    if 'property="og:type" content="article"' not in r.text and '"@type":"NewsArticle"' not in r.text.replace(' ', ''):
        return None, yolu, 'haber sayfası değil'
    t = re.search(r'property="(?:og:)?article:published_time" content="([^"]+)"', r.text)
    try:
        return datetime.datetime.fromisoformat(t.group(1)), yolu, None
    except Exception:
        return None, yolu, 'yayın zamanı okunamadı'


def uc_sey(dosya):
    try:
        gelen = json.load(open(dosya, encoding='utf-8'))
    except Exception as e:
        hata(f'JSON okunamadı: {e}')
    gelen = gelen.get('maddeler') if isinstance(gelen, dict) else gelen
    if not isinstance(gelen, list) or not gelen:
        hata('Dosya {"maddeler": [{"link","etiket","baslik"}, ...]} biçiminde olmalı.')
    if len(gelen) > 3:
        hata('En fazla 3 madde yazılabilir.')
    s = oturum()
    simdi = datetime.datetime.now(TR)
    uyarilar = []

    def kontrol(mevcut):
        eski, isaret = uc_oku(mevcut)
        # Elle yapılmış giriş: maddeler aracın son yazdığından farklıysa ve bugün elle girildiyse üzerine yazılmaz
        if eski and (not isaret or isaret[1] != uc_ozet(eski)):
            bugun = isaret and isaret[0][:10] == simdi.date().isoformat()
            if not bugun:
                for x in eski:
                    t, _, _ = uc_haber(s, x['link'])
                    if t and t.astimezone(TR).date() == simdi.date():
                        bugun = True
                        break
            if bugun:
                print('UYARI: Widget\'ta bugün elle yapılmış bir giriş var; üzerine yazılmadı.')
                return None
        yeni = []
        for i, x in enumerate(gelen):
            neden = None
            if not isinstance(x, dict) or not all(isinstance(x.get(k), str) and x.get(k).strip() for k in ('link', 'etiket', 'baslik')):
                neden = 'link, etiket ve baslik dolu metin olmalı'
            elif len(x['baslik'].strip()) > 90:
                neden = f'başlık {len(x["baslik"].strip())} karakter (en fazla 90)'
            elif len(x['etiket'].strip()) > 30 or re.search(r'[<>]', x['baslik'] + x['etiket']):
                neden = 'etiket en fazla 30 karakter; < > kullanılmaz'
            if not neden:
                t, yolu, neden = uc_haber(s, x['link'])
            if neden:
                if i < len(eski):
                    yeni.append(eski[i])
                    print(f'  {i + 1}. madde geçmedi ({neden}); eski madde kaldı: {eski[i]["baslik"]}')
                else:
                    print(f'  {i + 1}. madde geçmedi ({neden}); yazılmadı.')
                continue
            if simdi - t > datetime.timedelta(hours=36):
                uyarilar.append(f'{i + 1}. madde 36 saatten eski ({t.astimezone(TR):%d.%m %H.%M}); yine de gösterilecek.')
            yeni.append({'link': yolu, 'etiket': x['etiket'].strip(), 'baslik': x['baslik'].strip()})
            print(f'  {i + 1}. madde TAMAM: {yolu}')
        if not yeni:
            print('Hiçbir madde doğrulanmadı; widget boşaltılmadı, eski hali kaldı.')
            return None
        if yeni == eski and isaret:
            print('Maddeler zaten güncel, yazılmadı.')
            return None
        return uc_yaz_icerik(yeni)

    widget_yaz(s, UC_AD, None, '3sey', kontrol)
    for u in uyarilar:
        print('UYARI:', u)



def main():
    if '--ilk-giris' in sys.argv:
        return ilk_giris()
    if '--3sey' in sys.argv:
        return uc_sey(arg('--3sey'))
    if '--canli-oku' in sys.argv:
        return canli_oku(arg('--canli-oku'))
    if '--ek-widget-kur' in sys.argv:
        return ek_widget_kur(oturum())
    if '--tazele' in sys.argv:
        giris(oturum())
        print('TAMAM. Oturum 24 saat uzadı.')
        return
    dosya = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith('--') and sys.argv[i - 1] not in ('--oturum', '--3sey')]
    if not dosya:
        hata('Kullanım: python3 veri_guncelle.py veri.json --oturum oturum.json [--etkilesimsiz] [--kuru]')
    try:
        veri = json.load(open(dosya[0], encoding='utf-8'))
    except Exception as e:
        hata(f'JSON okunamadı: {e}')
    h = dogrula(veri)
    if h:
        print('Şemaya uymuyor, hiçbir şey yazılmadı:')
        for x in h:
            print('  -', x)
        sys.exit(1)
    try:
        parca = bol(veri)
    except ValueError as e:
        hata(str(e))
    yeni = {}
    for (wad, sid), p in zip(PARCALAR, parca):
        metin = json.dumps(p, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        yeni[wad] = f'<script type="application/json" id="{sid}">' + metin + '</script>'
        print(f'  {wad}: {len(metin)} karakter ({", ".join(k for k in p if k != "surum") or "boş"})')
    print('Şema TAMAM.')
    if '--kuru' in sys.argv:
        return
    widgetlar_yaz(oturum(), yeni, 'veri')


def canli_oku(dosya):
    """Ana sayfadaki veri parçalarını birleştirip dosyaya yazar. Tur bu dosyayı değiştirip yazmalı; yalnız e24-veri okunursa diğer tablolar silinir."""
    t = requests.get(SITE + '/?v=' + str(int(datetime.datetime.now().timestamp())), headers={'User-Agent': 'Mozilla/5.0'}, timeout=30).text
    veri = {}
    for _, sid in PARCALAR:
        m = re.search(r'<script type="application/json" id="' + sid + r'">(.*?)</script>', t, re.S)
        if not m:
            hata(f'{sid} ana sayfada bulunamadı; yazmayın.')
        for k, x in json.loads(m.group(1).replace('<\\/', '</')).items():
            veri.setdefault(k, x)
    json.dump(veri, open(dosya, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'TAMAM. {dosya}: ' + ', '.join(k for k in veri if k != 'surum'))


def bol(veri):
    """Üst düzey tabloları büyükten küçüğe, sığdığı ilk parçaya koyar. Her parçada "surum" bulunur."""
    boy = lambda x: len(json.dumps(x, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    parca = [{'surum': veri.get('surum', 1)} for _ in PARCALAR]
    for k in sorted((k for k in veri if k != 'surum'), key=lambda k: -boy(veri[k])):
        for p in parca:
            if boy(dict(p, **{k: veri[k]})) <= SINIR:
                p[k] = veri[k]
                break
        else:
            raise ValueError(f'"{k}" tablosu ({boy(veri[k])} karakter) hiçbir parçaya sığmıyor; toplam sınır {len(PARCALAR)} x {SINIR}. Hiçbir şey yazılmadı.')
    return parca


def widgetlar_yaz(s, yeni, etiket):
    """yeni: {widget adı: içerik}. Hepsi tek kayıtta yazılır; yedek, karşılaştırma ve sorunda geri dönüş widget_yaz ile aynı."""
    giris(s)
    d, tok = durum(s)
    sb = {x['id']: x for x in d['sidebars']}
    hedef = sb[ALAN]['widgets']
    adlar = [deger(w['form_html'], 'name') for w in hedef]
    eksik = [a for a in yeni if a not in adlar]
    if eksik:
        hata('Widget bulunamadı: ' + ', '.join(eksik) + ' (bir kez: --ek-widget-kur)')
    if all(deger(hedef[adlar.index(a)]['form_html'], 'content') == c for a, c in yeni.items()):
        print('Zaten güncel, yazılmadı.')
        return
    zaman = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime('%Y-%m-%d_%H%M%S')
    yd = os.path.join(D, 'yedek', zaman + '-' + etiket)
    os.makedirs(yd, exist_ok=True)
    json.dump(d, open(os.path.join(yd, 'widgetlar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    if os.path.isdir(os.path.join(D, '.git')):
        subprocess.run(['git', '-C', D, 'add', yd], check=True)
        subprocess.run(['git', '-C', D, 'commit', '-q', '-m', f'{etiket} yazımı öncesi yedek ({zaman})'], check=True)
    print('Yedek:', yd)
    items = []
    for w in hedef:
        ad, ic = deger(w['form_html'], 'name'), deger(w['form_html'], 'content')
        items.append(urlencode([('id', TEXT), ('name', ad), ('content', yeni.get(ad, ic)), ('class', SINIF),
                                ('is_mobile', w.get('is_mobile') or 1), ('is_desktop', w.get('is_desktop') or 1)]))
    r = yaz(s, d, tok, items)
    print('Kayıt:', r.status_code)
    d2, tok2 = durum(s)
    sb2 = {x['id']: x for x in d2['sidebars']}
    sorun = [f'{k} alanı değişti' for k in sb if k != ALAN and norm(sb[k]['widgets']) != norm(sb2[k]['widgets'])]
    yw = sb2[ALAN]['widgets']
    if len(yw) != len(hedef):
        sorun.append(f'{ALAN} widget sayısı değişti')
    else:
        for a, b in zip(hedef, yw):
            ad = deger(a['form_html'], 'name')
            if deger(b['form_html'], 'name') != ad or deger(b['form_html'], 'content') != yeni.get(ad, deger(a['form_html'], 'content')):
                sorun.append(f'"{ad}" widget\'ı beklenenden farklı kaydedildi')
    if sorun:
        print('Sorun var, eski hale döndürülüyor:', '; '.join(sorun))
        yaz(s, d2, tok2, ogeler(hedef))
        d3, _ = durum(s)
        geri = norm({x['id']: x['widgets'] for x in d3['sidebars']}) == norm({x['id']: x['widgets'] for x in d['sidebars']})
        hata('Geri dönüş ' + ('TAMAM.' if geri else 'BAŞARISIZ, yedekten elle dönün: ' + yd))
    kaydet(s)
    print('TAMAM. Yalnız şu widget\'lar değişti: ' + ', '.join(yeni))


def ek_widget_kur(s):
    """Eksik veri parçası widget'larını home_bottom_section'ın sonuna ekler (boş JSON ile); diğer widget'lar aynı kalır."""
    giris(s)
    d, tok = durum(s)
    sb = {x['id']: x for x in d['sidebars']}
    hedef = sb[ALAN]['widgets']
    adlar = [deger(w['form_html'], 'name') for w in hedef]
    ekle = [(a, i) for a, i in PARCALAR if a not in adlar]
    if not ekle:
        print('Ek widget\'lar zaten var.')
        return
    zaman = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime('%Y-%m-%d_%H%M%S')
    yd = os.path.join(D, 'yedek', zaman + '-ek-widget')
    os.makedirs(yd, exist_ok=True)
    json.dump(d, open(os.path.join(yd, 'widgetlar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    if os.path.isdir(os.path.join(D, '.git')):
        subprocess.run(['git', '-C', D, 'add', yd], check=True)
        subprocess.run(['git', '-C', D, 'commit', '-q', '-m', f'ek widget kurulumu öncesi yedek ({zaman})'], check=True)
    items = ogeler(hedef) + [urlencode([('id', TEXT), ('name', a), ('content', f'<script type="application/json" id="{i}">{{"surum":1}}</script>'),
                                         ('class', SINIF), ('is_mobile', 1), ('is_desktop', 1)]) for a, i in ekle]
    r = yaz(s, d, tok, items)
    print('Kayıt:', r.status_code)
    d2, tok2 = durum(s)
    sb2 = {x['id']: x for x in d2['sidebars']}
    sorun = [f'{k} alanı değişti' for k in sb if k != ALAN and norm(sb[k]['widgets']) != norm(sb2[k]['widgets'])]
    yw = sb2[ALAN]['widgets']
    if len(yw) != len(hedef) + len(ekle) or norm(yw[:len(hedef)]) != norm(hedef) or [deger(w['form_html'], 'name') for w in yw[len(hedef):]] != [a for a, _ in ekle]:
        sorun.append('widget düzeni beklenenden farklı')
    if sorun:
        print('Sorun var, eski hale döndürülüyor:', '; '.join(sorun))
        yaz(s, d2, tok2, ogeler(hedef))
        hata('Geri döndürüldü, yedek: ' + yd)
    kaydet(s)
    print('TAMAM. Eklendi: ' + ', '.join(a for a, _ in ekle))


def widget_yaz(s, HAD, icerik, etiket, onkontrol=None):
    """Yalnız HAD adlı widget'ı yazar: yedek, yazma, diğer widget'larla karşılaştırma, sorunda geri dönüş.
    onkontrol(mevcut_icerik) yazılacak içeriği döner; None dönerse yazmadan çıkar."""
    giris(s)
    d, tok = durum(s)
    sb = {x['id']: x for x in d['sidebars']}
    hedef = sb[ALAN]['widgets']
    if any(w['widget_id'] != TEXT or SINIF not in (deger(w['form_html'], 'class') or '') for w in hedef):
        hata(f'{ALAN} içinde v5 dışı widget var, durdum.')
    hw = [w for w in hedef if deger(w['form_html'], 'name') == HAD]
    if len(hw) != 1:
        hata(f'"{HAD}" widget\'ı bulunamadı.')
    mevcut = deger(hw[0]['form_html'], 'content')
    if onkontrol:
        icerik = onkontrol(mevcut)
        if icerik is None:
            return
    if mevcut == icerik:
        print('Zaten güncel, yazılmadı.')
        return

    zaman = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime('%Y-%m-%d_%H%M%S')
    yd = os.path.join(D, 'yedek', zaman + '-' + etiket)
    os.makedirs(yd, exist_ok=True)
    json.dump(d, open(os.path.join(yd, 'widgetlar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    if os.path.isdir(os.path.join(D, '.git')):
        subprocess.run(['git', '-C', D, 'add', yd], check=True)
        subprocess.run(['git', '-C', D, 'commit', '-q', '-m', f'{etiket} yazımı öncesi yedek ({zaman})'], check=True)
    print('Yedek:', yd)

    r = yaz(s, d, tok, ogeler(hedef, icerik, HAD))
    print('Kayıt:', r.status_code)
    d2, tok2 = durum(s)
    sb2 = {x['id']: x for x in d2['sidebars']}
    sorun = []
    for k in sb:
        if k != ALAN and norm(sb[k]['widgets']) != norm(sb2[k]['widgets']):
            sorun.append(f'{k} alanı değişti')
    yeni = sb2[ALAN]['widgets']
    if len(yeni) != len(hedef):
        sorun.append(f'{ALAN} widget sayısı değişti')
    else:
        for a, b in zip(hedef, yeni):
            ad = deger(a['form_html'], 'name')
            beklenen = icerik if ad == HAD else deger(a['form_html'], 'content')
            if deger(b['form_html'], 'name') != ad or deger(b['form_html'], 'content') != beklenen:
                sorun.append(f'"{ad}" widget\'ı beklenenden farklı kaydedildi')
    if sorun:
        print('Sorun var, eski hale döndürülüyor:', '; '.join(sorun))
        yaz(s, d2, tok2, ogeler(hedef))
        d3, _ = durum(s)
        geri = norm({x['id']: x['widgets'] for x in d3['sidebars']}) == norm({x['id']: x['widgets'] for x in d['sidebars']})
        hata('Geri dönüş ' + ('TAMAM.' if geri else 'BAŞARISIZ, yedekten elle dönün: ' + yd))
    kaydet(s)
    print(f'TAMAM. Yalnız "{HAD}" değişti; diğer widget\'lar yedekle aynı.')


if __name__ == '__main__':
    main()
