"""Endeks24 veri programı (Halit Bey onayı 19.10.2026).
Fintables MCP'den (salt okuma) BIST verisini, Coinbase'den kripto fiyatını alır; sitenin canlı veri bloklarını taban alıp
yalnız aşağıdaki tabloları günceller ve veri.json olarak yazar. Site bu dosyayı okur; dosya eskiyse paneldeki veriyi kullanır.
Anahtar FINTABLES ortam değişkeninde (GitHub secret); dosyaya ya da çıktıya yazılmaz.
Kullanım: python3 fintables_veri.py <cikti.json> [--kripto-yalniz]
"""
import base64, collections, copy, datetime, html, json, os, re, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veri_sema import dogrula

MCP = 'https://evo.fintables.com/mcp'
SITE = 'https://www.endeks24.com/'
TR = datetime.timezone(datetime.timedelta(hours=3))
PIYASA_BOLUM = ('PİYASALAR', 'KAP HABERLERİ', 'HALKA ARZ', 'KRİPTO', 'BIST 100', 'ALTIN', 'DOLAR VE DÖVİZ', 'FON KRİZİ', 'TCMB VE FAİZ')
YOLLAR = ['rakamlar.piyasa', 'rakamlar.gundem', 'piyasa.seans', 'piyasa.hareket', 'piyasa.sektor_performans', 'fiyat.tum', 'hisseler', 'kap.temettu',
          'doviz.kurlar', 'enerji.brent', 'kripto.varliklar']  # sektorler.* ayrıca


def hata(m):
    print('HATA:', m); sys.exit(1)


def istek(url, veri=None, bas=None, zaman=40):
    r = urllib.request.Request(url, data=veri, headers=dict({'User-Agent': 'Endeks24-veri/1'}, **(bas or {})))
    with urllib.request.urlopen(r, timeout=zaman) as y:
        return y.read().decode('utf-8'), dict(y.headers)


class Fintables:
    def __init__(self, anahtar):
        self.b = {'Authorization': 'Bearer ' + anahtar, 'Content-Type': 'application/json',
                  'Accept': 'application/json, text/event-stream'}
        self.n = 0
        r = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                    'clientInfo': {'name': 'endeks24-veri', 'version': '1'}})
        self.bildir('notifications/initialized')

    def _gonder(self, govde):
        try:
            t, h = istek(MCP, json.dumps(govde).encode(), self.b)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                hata('Fintables anahtarı geçersiz ya da süresi dolmuş (401). Giriş sayfasından yeniden izin verilmeli.')
            hata(f'Fintables HTTP {e.code}: {e.read()[:300]!r}')
        sid = h.get('Mcp-Session-Id') or h.get('mcp-session-id')
        if sid:
            self.b['Mcp-Session-Id'] = sid
        return t

    def bildir(self, yontem):
        self._gonder({'jsonrpc': '2.0', 'method': yontem})

    def rpc(self, yontem, param):
        self.n += 1
        t = self._gonder({'jsonrpc': '2.0', 'id': self.n, 'method': yontem, 'params': param})
        if t.lstrip().startswith('{'):
            j = json.loads(t)
        else:  # SSE
            j = None
            for sat in t.splitlines():
                if sat.startswith('data:'):
                    x = json.loads(sat[5:])
                    if x.get('id') == self.n:
                        j = x
            if j is None:
                hata('Fintables yanıtı çözülemedi: ' + t[:300])
        if 'error' in j:
            hata('Fintables hata: ' + json.dumps(j['error'], ensure_ascii=False)[:300])
        return j['result']

    def sorgu(self, sql):
        r = self.rpc('tools/call', {'name': 'veri_sorgula', 'arguments': {'sql': sql, 'purpose': 'Endeks24 sitesi veri güncellemesi'}})
        metin = ''.join(c.get('text', '') for c in r.get('content', []) if c.get('type') == 'text')
        if r.get('isError'):
            hata('Sorgu hatası: ' + metin[:300])
        j = json.loads(metin)
        sat = j['table'].split('\n')
        bas = [x.strip() for x in sat[0].strip().strip('|').split('|')]
        out = []
        for s in sat[2:]:
            c = [x.strip() for x in s.strip().strip('|').split('|')]
            if len(c) == len(bas):
                out.append(dict(zip(bas, c)))
        return out


def canli_taban(yedek):
    try:
        t, _ = istek(SITE + '?v=' + str(int(datetime.datetime.now().timestamp())))
        v = {}
        for sid in ('e24-veri', 'e24-veri-2', 'e24-veri-3'):
            m = re.search(r'<script type="application/json" id="' + sid + r'">(.*?)</script>', t, re.S)
            if not m:
                raise ValueError(sid + ' yok')
            for k, x in json.loads(m.group(1).replace('<\\/', '</')).items():
                v.setdefault(k, x)
        return v
    except Exception as e:
        print('Uyarı: sitenin canlı verisi okunamadı (' + str(e) + '); önceki dosya taban alınıyor.')
        if yedek:
            return yedek
        hata('Taban veri yok.')


def r2(x):
    return round(x, 2)


def tr(x, n=2):
    return f'{x:,.{n}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def bist(y, ft, simdi):
    bugun = simdi.date().isoformat()
    ix = {r['endeks_kodu']: r for r in ft.sorgu("SELECT endeks_kodu, son_fiyat, son_fiyat_zaman_utc, gunici_getiri FROM endeksler_k WHERE endeks_kodu IN ('XU100','XU030','XU050','XUMAL','XUSIN','XHARZ') LIMIT 10")}
    z = datetime.datetime.fromisoformat(ix['XU100']['son_fiyat_zaman_utc'].replace('Z', '+00:00')).astimezone(TR)
    if z.date() != simdi.date():
        print('BIST bugün işlem görmedi (son veri ' + z.isoformat() + '); BIST tabloları güncellenmedi.')
        return False
    kapali = z.hour * 60 + z.minute >= 18 * 60 + 5 or simdi.hour * 60 + simdi.minute >= 18 * 60 + 30
    T = z.replace(second=0, microsecond=0).isoformat() if not kapali else simdi.replace(hour=18, minute=10, second=0, microsecond=0).isoformat()
    satir = []
    for o in (0, 300, 600):
        satir += ft.sorgu('SELECT h.hisse_senedi_kodu kod, h.son_fiyat fiyat, h.gunici_getiri deg, h.son_fiyat_zaman_utc zaman, s.baslik sektor, h.endeksler endeks '
                          f'FROM hisse_senetleri h LEFT JOIN sektorler s ON s.id=h.sektor_id ORDER BY h.hisse_senedi_kodu LIMIT 300 OFFSET {o}')
    B = {}
    for r in satir:
        try:
            if r['zaman'][:10] and datetime.datetime.fromisoformat(r['zaman'].replace('Z', '+00:00')).astimezone(TR).date().isoformat() == bugun and r['fiyat']:
                B[r['kod']] = {'f': float(r['fiyat']), 'g': r2(float(r['deg'])), 's': r['sektor'], 'x100': 'XU100' in r['endeks']}
        except ValueError:
            pass
    if len(B) < 300:
        hata(f'Bugün fiyatı olan hisse sayısı az ({len(B)}); yazılmadı.')
    f = lambda k: B[k]['f']; g = lambda k: B[k]['g']
    ftum = y['fiyat']['tum']; ftum['tarih'] = T
    ftum['satirlar'] = [{'kod': s['kod'], 'kapanis': f(s['kod']), 'degisim': g(s['kod'])} for s in ftum['satirlar'] if s['kod'] in B]
    y['hisseler']['tarih'] = T
    for k, v in y['hisseler']['liste'].items():
        if k in B:
            v['fiyat'] = f(k); v['degisim'] = g(k)
    se = y['piyasa']['seans']; x100 = [k for k in B if B[k]['x100']]
    yu = sum(g(k) > 0 for k in x100); du = sum(g(k) < 0 for k in x100); de = len(x100) - yu - du
    son, dg = float(ix['XU100']['son_fiyat']), r2(float(ix['XU100']['gunici_getiri']))
    se.update(tarih=T, durum='kapali' if kapali else 'acik', endeks=son, degisim=dg, kaynak='Borsa İstanbul (Fintables)')
    yon = 'yükselişle' if dg > 0 else 'düşüşle' if dg < 0 else 'değişimsiz'
    yuzde = f'yüzde {tr(abs(dg))} ' if dg else ''
    if kapali:
        se['yorum'] = f'BIST 100 günü {yuzde}{yon} {tr(son)} puandan kapattı. Endeksteki {len(x100)} hisseden {du} hisse geriledi, {yu} hisse yükseldi.'
    else:
        se['yorum'] = f'BIST 100 saat {z.strftime("%H.%M")} itibarıyla {yuzde}{yon} {tr(son)} puanda. Endeksteki {len(x100)} hisseden {du} hisse geriliyor, {yu} hisse yükseliyor.'
    AD = {'BIST 30': 'XU030', 'BIST 50': 'XU050', 'BIST Mali': 'XUMAL', 'BIST Sınai': 'XUSIN', 'BIST Halka Arz': 'XHARZ'}
    for a in se['alt']:
        r = ix.get(AD.get(a['ad']))
        if r:
            a['deger'] = float(r['son_fiyat']); a['degisim'] = r2(float(r['gunici_getiri']))
    hac = {r['kod']: float(r['hacim_mn']) for r in ft.sorgu(
        "SELECT m.kod, ROUND((m.hacim_15_dk_gecikmeli/1000000)::numeric,1) hacim_mn FROM mumlar_gunluk_gh m JOIN hisse_senetleri h ON h.hisse_senedi_kodu=m.kod "
        f"WHERE m.zaman_utc >= TIMESTAMP '{(simdi - datetime.timedelta(hours=simdi.hour, minutes=simdi.minute) - datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:00')}' AND 'XU100' = ANY(h.endeksler) ORDER BY m.hacim_15_dk_gecikmeli DESC LIMIT 120")}
    sira = sorted(x100, key=lambda k: -g(k))
    sat = lambda k: {'kod': k, 'fiyat': f(k), 'degisim': g(k), 'hacim_mn': hac.get(k, 0.0)}
    hr = y['piyasa']['hareket']; hr['tarih'] = T
    hr['yukselenler'] = [sat(k) for k in sira[:5]]; hr['dusenler'] = [sat(k) for k in sira[::-1][:5]]
    hr['hacim'] = [sat(k) for k in sorted((k for k in hac if k in B), key=lambda k: -hac[k])[:5]]
    hr['genislik'] = {'yukselen': yu, 'dusen': du, 'degismeyen': de}
    gr = collections.defaultdict(list)
    for k, v in B.items():
        if v['s']:
            gr[v['s']].append(v['g'])
    sp = y['piyasa']['sektor_performans']; sp['tarih'] = T
    sp['satirlar'] = sorted([{'ad': a, 'degisim': r2(sum(l) / len(l))} for a, l in gr.items() if len(l) >= 4], key=lambda z: -z['degisim'])
    for ad, v in y['sektorler'].items():
        ks = [h['kod'] for h in v['hisseler'] if h['kod'] in B]
        if not ks:
            continue
        v.update(tarih=T, kapanis=kapali, islem_goren=len(ks), yukselen=sum(g(k) > 0 for k in ks), dusen=sum(g(k) < 0 for k in ks), ortalama=r2(sum(g(k) for k in ks) / len(ks)))
        v['hisseler'] = sorted([{'kod': k, 'fiyat': f(k), 'degisim': g(k)} for k in ks], key=lambda z: -z['degisim'])
    tm = y['kap']['temettu']; tm['tarih'] = T
    tm['satirlar'] = [dict(r, verim=r2(r['brut'] / f(r['kod']) * 100)) if r['kod'] in B else r for r in tm['satirlar'] if r['hak_kullanim'] >= bugun]
    # döviz, altın, Brent: haftalık değişim önceki haftanın son kapanışına göre
    pzt = simdi.date() - datetime.timedelta(days=simdi.weekday())
    m = ft.sorgu("SELECT kod, zaman_utc, kapanis FROM mumlar_gunluk_gh WHERE kod IN ('USDTRY','EURTRY','GBPTRY','GRAMALTIN','BRENT') "
                 f"AND zaman_utc >= TIMESTAMP '{(pzt - datetime.timedelta(days=10)).isoformat()} 00:00:00' ORDER BY kod, zaman_utc LIMIT 100")
    seri = collections.defaultdict(list)
    for r in m:
        gun = (datetime.datetime.fromisoformat(r['zaman_utc'].replace('Z', '+00:00')) + datetime.timedelta(hours=3)).date()
        seri[r['kod']].append((gun, float(r['kapanis'])))
    def son_ve_taban(kod):
        s = seri.get(kod) or []
        once = [x for x in s if x[0] < pzt]
        return (s[-1][1], once[-1][1]) if s and once else (None, None)
    dv = y['doviz']['kurlar']; KOD = {'USD': 'USDTRY', 'EUR': 'EURTRY', 'GBP': 'GBPTRY', 'GA': 'GRAMALTIN'}
    yaz = False
    for r in dv['satirlar']:
        s, t0 = son_ve_taban(KOD.get(r['kod'], ''))
        if s:
            r['son'] = round(s, 4 if r['kod'] != 'GA' else 2); r['haftalik'] = r2((s / t0 - 1) * 100); yaz = True
    if yaz:
        dv['tarih'] = T
    s, _ = son_ve_taban('BRENT')
    if s:
        y['enerji']['brent'].update(tarih=T, deger=r2(s))
    print(se['yorum'])
    return True


def kripto(y, simdi):
    v = y['kripto']['varliklar']; yeni = []
    for r in v['satirlar']:
        t, _ = istek(f'https://api.exchange.coinbase.com/products/{r["kod"]}-USD/stats')
        j = json.loads(t)
        son = float(j['last'])
        c, _ = istek(f'https://api.exchange.coinbase.com/products/{r["kod"]}-USD/candles?granularity=86400')
        mum = json.loads(c)  # [zaman, low, high, open, close, volume], yeniden eskiye
        dun = float(mum[1][4])
        yeni.append(dict(r, dolar=son if son >= 100 else round(son, 4), degisim=r2((son / dun - 1) * 100)))
    v['satirlar'] = yeni; v['tarih'] = simdi.replace(second=0, microsecond=0).isoformat(); v['kaynak'] = 'Coinbase'


def rakamlar(y, simdi, onbellek):
    """Haberlerdeki rakam işaretlerinden (span.e24-rakam, Kısaca kutusunda) "Rakamlarla piyasa" ve "Rakamlarla gündem"
    kartları. Halit Bey onayı 20.10.2026. Son 72 saatin haberleri; her bölümde en yeni 8. Haber başına bir işaret."""
    t, _ = istek(SITE + 'sitemap-news.xml')
    adres = re.findall(r'<loc>([^<]+)</loc>', t)[:60]
    bulunan = []
    for u in adres:
        if u not in onbellek:
            try:
                h, _ = istek(u, zaman=25)
            except Exception:
                continue
            m = re.search(r'<span class="e24-rakam"([^>]*)>([^<]+)</span>', h)
            kayit = None
            if m:
                yon = re.search(r'data-yon="(up|dn)"', m.group(1))
                li = h.rfind('<li', 0, m.start()); son = h.find('</li>', m.end())
                cumle = re.sub(r'<[^>]+>', '', h[li:son] if li > 0 and son > 0 else m.group(2))
                cumle = html.unescape(re.sub(r'\s+', ' ', cumle)).strip().rstrip('.')
                parca = [p.strip() for p in cumle.split(';')]
                sayi = html.unescape(m.group(2)).strip()
                # Kart başlıksız gösterilir: açıklama tek başına anlaşılmalı. Cümle kısaysa tamamı, uzunsa sayının geçtiği bölüm.
                ac = cumle if len(cumle) <= 150 else next((p for p in parca if sayi in p), cumle)
                if len(ac) > 150:
                    ac = ac[:147].rsplit(' ', 1)[0] + '…'
                ac = ac[:1].upper() + ac[1:]
                ys = re.fullmatch(r'yüzde\s+([\d.,]+)', sayi)
                if ys:
                    sayi = '%' + ys.group(1)
                elif re.fullmatch(r'[\d.,]+', sayi) and re.search(r'yüzde\s+' + re.escape(sayi) + r'\b', cumle):
                    sayi = '%' + sayi  # metinde "yüzde 34,7" olarak geçen yalın sayı
                AYLAR = 'Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık'
                if re.search(r'\b(' + AYLAR + r')\b', sayi) or re.fullmatch(r'(19|20)\d\d', sayi):
                    m = None  # tarih işaretlenmez (Y.20261017.04 madde 2)
            if m:
                bas = re.search(r'<meta property="og:title" content="([^"]*)"', h)
                h1 = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
                zm = re.search(r'"datePublished":"([^"]+)"', h)
                bol = re.search(r'"articleSection":"([^"]+)"', h)
                kayit = {'sayi': sayi, 'yon': yon.group(1) if yon else '', 'aciklama': ac, 'link': u,
                         'baslik': html.unescape(re.sub(r'<[^>]+>', '', h1.group(1)).strip() if h1 else (bas.group(1) if bas else '')),
                         'haber_tarihi': zm.group(1) if zm else None,
                         'bolum': json.loads('"' + bol.group(1) + '"') if bol else ''}
                if sayi.startswith('%'):
                    try:
                        o = float(sayi[1:].replace('.', '').replace(',', '.'))
                        if 0 <= o <= 100:
                            kayit['oran'] = o
                    except ValueError:
                        pass
            onbellek[u] = kayit
        if onbellek.get(u):
            bulunan.append(onbellek[u])
    sinir = simdi - datetime.timedelta(hours=72)
    def yeni_mi(k):
        try:
            return datetime.datetime.fromisoformat(k['haber_tarihi']) >= sinir
        except Exception:
            return False
    bulunan = sorted([k for k in bulunan if k.get('haber_tarihi') and yeni_mi(k)], key=lambda k: k['haber_tarihi'], reverse=True)
    T = simdi.replace(second=0, microsecond=0).isoformat()
    for ad, kosul in (('piyasa', lambda k: k['bolum'] in PIYASA_BOLUM), ('gundem', lambda k: k['bolum'] not in PIYASA_BOLUM)):
        sat = [{x: v for x, v in k.items() if x != 'bolum'} for k in bulunan if kosul(k)][:8]
        if len(sat) >= 3:
            y['rakamlar'][ad] = {'tarih': T, 'kaynak': 'Endeks24', 'satirlar': sat}
    for u in [u for u in onbellek if u not in adres]:
        del onbellek[u]
    print('rakamlar:', {a: len(y['rakamlar'][a]['satirlar']) for a in ('piyasa', 'gundem')})


def main():
    cikti = sys.argv[1]
    simdi = datetime.datetime.now(TR)
    onceki = json.load(open(cikti)) if os.path.exists(cikti) else None
    taban = canli_taban(onceki and onceki.get('veri'))
    y = copy.deepcopy(taban)
    if '--kripto-yalniz' not in sys.argv:
        paket = os.environ.get('FINTABLES', '').strip()
        if not paket:
            hata('FINTABLES anahtarı tanımlı değil.')
        try:
            p = json.loads(base64.b64decode(paket))
        except Exception:
            hata('FINTABLES anahtarı bozuk; giriş sayfasındaki anahtar eksiksiz kopyalanmalı.')
        if p.get('bitis') and p['bitis'] / 1000 < simdi.timestamp():
            hata('Fintables anahtarının süresi doldu; pazar günü giriş sayfasından yeniden izin verilmeli.')
        bist(y, Fintables(p['a']), simdi)
    try:
        kripto(y, simdi)
    except Exception as e:
        print('Uyarı: kripto alınamadı:', e)
    onbellek = (onceki or {}).get('rakam_onbellek', {})
    try:
        rakamlar(y, simdi, onbellek)
    except Exception as e:
        print('Uyarı: rakamlar alınamadı:', e)
    hatalar = dogrula(y)
    if hatalar:
        hata('Şema hatası, yazılmadı: ' + '; '.join(hatalar[:5]))
    # Site yalnız YOLLAR'daki tabloları ve sektorler altındaki tabloları, kendi verisinden yeniyse kullanır
    cik = {'olusturma': simdi.isoformat(timespec='seconds'), 'yollar': YOLLAR + ['sektorler.*'],
           'veri': y, 'rakam_onbellek': onbellek}
    json.dump(cik, open(cikti, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('TAMAM:', cikti, os.path.getsize(cikti), 'bayt;', 'seans', y['piyasa']['seans']['tarih'], '; kripto', y['kripto']['varliklar']['tarih'])


if __name__ == '__main__':
    main()
