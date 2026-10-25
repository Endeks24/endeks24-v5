"""Endeks24 analiz modülleri (25.10.2026). Sitedeki kutuların JSON verisini üretir; yapay zeka çağrısı yoktur.
Fintables MCP'den (salt okuma) okur; <kok>/analiz/ altına yazar. Fiyatlar <kok>/fiyat/ klasöründen (fiyat_gecmisi.py) gelir.

  tahmin     aracı kurum kâr tahminlerinin günlük kopyası (analiz/tahmin-arsiv.json). Tablo tarih tutmadığı için "açıklanmadan önceki
             tahmin" yalnız bu arşivden bilinir.
  tasiyici   "Endeksi kim taşıdı": BIST 100 günlük puan değişimine hisse katkıları (analiz/endeksi-tasiyan.json).
  fon        "Fon dedektifi": fonların aylık hisse alım satımı ve kategori nakit akışı (analiz/fon-dedektifi.json).
  arz        "Halka arz röntgeni ve aracı kurum ligi" (analiz/halka-arz.json).
  surpriz    "Bilanço sürpriz tablosu" (analiz/bilanco-surpriz.json).

Kullanım: python3 analiz.py <modül> <kök_klasör>        Anahtar FINTABLES ortam değişkeninde (GitHub secret).
"""
import collections, datetime, json, os, statistics, sys, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiyat_gecmisi as fg

TR = datetime.timezone(datetime.timedelta(hours=3))


def log(*a):
    print(*a, flush=True)


def num(x):
    try:
        return float(x) if x not in (None, '') else None
    except ValueError:
        return None


def bugun():
    return datetime.datetime.now(TR).date()


def yaz(kok, ad, nesne):
    os.makedirs(os.path.join(kok, 'analiz'), exist_ok=True)
    json.dump(nesne, open(os.path.join(kok, 'analiz', ad), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


def oku(kok, ad, varsayilan):
    yol = os.path.join(kok, 'analiz', ad)
    return json.load(open(yol, encoding='utf-8')) if os.path.exists(yol) else varsayilan


def fiyat_kok(kok):
    klasor = os.path.join(kok, 'fiyat')
    takvim = json.load(open(os.path.join(klasor, 'takvim.json'), encoding='utf-8'))
    return klasor, takvim


def r(x, n=2):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- tahmin arşivi
def tahmin(ft, kok):
    ar = oku(kok, 'tahmin-arsiv.json', {'kayit': {}})
    gun = bugun().isoformat()
    sat = fg.sayfala(ft, "SELECT hisse_senedi_kodu, araci_kurum_kodu, yil, ay, satislar, favok, net_kar FROM hisse_senedi_araci_kurum_tahminleri "
                         "WHERE yil >= 2025 ORDER BY hisse_senedi_kodu, araci_kurum_kodu, yil, ay")
    if len(sat) < 200:
        sys.exit(f'HATA: tahmin satırı beklenenden az ({len(sat)}); arşiv değiştirilmedi')
    yeni = 0
    for s in sat:
        k = f"{s['hisse_senedi_kodu']}|{s['araci_kurum_kodu']}|{s['yil']}|{s['ay']}"
        v = [None if num(s[a]) is None else round(num(s[a])) for a in ('satislar', 'favok', 'net_kar')]
        liste = ar['kayit'].setdefault(k, [])
        if not liste or liste[-1][1:] != v:
            liste.append([gun] + v)
            yeni += 1
    ar['guncelleme'] = gun
    ar.setdefault('ilk', gun)
    yaz(kok, 'tahmin-arsiv.json', ar)
    log('tahmin: satır', len(sat), 'yeni/değişen kayıt', yeni, 'toplam anahtar', len(ar['kayit']))


# ---------------------------------------------------------------- Endeksi kim taşıdı
def katkilar(pay, seri, xu, gunler):
    """pay {kod: pay adedi}, seri {kod: {tarih: kapanış}}, xu {tarih: puan}, gunler artan tarih listesi.
    Ağırlık: bir önceki kapanışla fiili dolaşım piyasa değeri (resmî ağırlık listesi yok, tahmindir). Katkı puandır."""
    out = []
    for i in range(1, len(gunler)):
        d, p = gunler[i], gunler[i - 1]
        puan = xu[d] - xu[p]
        w = {k: pay[k] * seri[k][p] for k in pay if pay[k] and p in seri[k] and d in seri[k] and seri[k][p] > 0}
        W = sum(w.values())
        if len(w) < 0.9 * len(pay) or W <= 0:
            out.append({'tarih': d, 'kalite': 'yok'})
            continue
        kat = {k: w[k] / W * (seri[k][d] / seri[k][p] - 1) * xu[p] for k in w}
        toplam = sum(kat.values())
        fark = puan - toplam
        iyi = abs(fark) <= max(0.25 * abs(puan), 0.002 * xu[p])
        art = sorted(((k, v) for k, v in kat.items() if v > 0), key=lambda z: -z[1])[:5]
        dus = sorted(((k, v) for k, v in kat.items() if v < 0), key=lambda z: z[1])[:5]
        yon = art if puan >= 0 else dus
        out.append({'tarih': d, 'kapanis': r(xu[d]), 'puan': r(puan), 'yuzde': r((xu[d] / xu[p] - 1) * 100),
                    'kalite': 'iyi' if iyi else 'zayif', 'fark': r(fark), 'hisse': len(w),
                    'artiranlar': [[k, r(v)] for k, v in art], 'dusuranlar': [[k, r(v)] for k, v in dus],
                    'ilk5_pay': r(100 * sum(v for _, v in yon) / puan, 0) if puan else None})
    return out


def tasiyici(ft, kok, gun=6):
    klasor, T = fiyat_kok(kok)
    G = T['gun']
    uye = fg.sayfala(ft, "SELECT hisse_senedi_kodu, unvan, fiili_dolasim_pay_adedi FROM hisse_senetleri WHERE 'XU100' = ANY(endeksler) ORDER BY hisse_senedi_kodu")
    pay = {u['hisse_senedi_kodu']: num(u['fiili_dolasim_pay_adedi']) for u in uye if num(u['fiili_dolasim_pay_adedi'])}
    ad = {u['hisse_senedi_kodu']: u['unvan'] for u in uye}
    seri = {k: fg.yukle(klasor, k, G) for k in pay}
    xu = fg.yukle(klasor, 'XU100', G)
    gunler = [d for d in G if d in xu][-(gun + 1):]
    gl = katkilar(pay, seri, xu, gunler)
    yaz(kok, 'endeksi-tasiyan.json', {'guncelleme': bugun().isoformat(), 'son': gunler[-1], 'uye': len(pay), 'ad': {k: ad[k] for k in ad if k in pay},
                                      'not': 'Ağırlıklar fiili dolaşım piyasa değerine göredir; resmî ağırlık listesi değildir.', 'gunler': gl})
    log('tasiyici: üye', len(pay), 'gün', len(gl), 'son', gunler[-1], [g.get('kalite') for g in gl])


# ---------------------------------------------------------------- Fon dedektifi
def fon_hesapla(onceki, simdiki, fon_ikisi, fiyat, min_fon=3):
    """onceki, simdiki: {(fon, hisse): lot}. fon_ikisi: iki ayda da raporu olan fonlar. fiyat: {hisse: ay sonu kapanışı}.
    Bedelsiz şüphesi: pozisyonu olan fonların çoğunda lot aynı yönde ve toplam oranı 1,4 ve üstü ya da 0,7 ve altı ise hisse listeden ayrılır."""
    hisseler = collections.defaultdict(lambda: {'net': 0.0, 'al': 0, 'sat': 0, 'yeni': 0, 'cikan': 0, 'onceki': 0.0, 'simdiki': 0.0, 'artan': 0, 'azalan': 0, 'sabit': 0})
    anahtar = {k for k in list(onceki) + list(simdiki) if k[0] in fon_ikisi}
    for fon, h in anahtar:
        a, b = onceki.get((fon, h), 0.0), simdiki.get((fon, h), 0.0)
        x = hisseler[h]
        x['net'] += b - a
        x['onceki'] += a
        x['simdiki'] += b
        if b > a:
            x['al'] += 1
        elif b < a:
            x['sat'] += 1
        if a == 0 and b > 0:
            x['yeni'] += 1
        if b == 0 and a > 0:
            x['cikan'] += 1
        if a > 0 and b > 0:
            x['artan' if b > a * 1.0001 else 'azalan' if b < a * 0.9999 else 'sabit'] += 1
    liste, supheli = [], []
    for h, x in hisseler.items():
        p = fiyat.get(h)
        if not p or x['al'] + x['sat'] < min_fon:
            continue
        ortak = x['artan'] + x['azalan'] + x['sabit']
        oran = x['simdiki'] / x['onceki'] if x['onceki'] else None
        if ortak >= 5 and oran and (oran >= 1.4 or oran <= 0.7) and max(x['artan'], x['azalan']) / ortak >= 0.8:
            supheli.append(h)
            continue
        liste.append({'kod': h, 'net_tl': round(x['net'] * p), 'net_lot': round(x['net']), 'al': x['al'], 'sat': x['sat'], 'yeni': x['yeni'], 'cikan': x['cikan']})
    return liste, supheli


def ay_sonu(seri, yil, ay):
    son = (datetime.date(yil + (ay == 12), ay % 12 + 1, 1) - datetime.timedelta(days=1)).isoformat()
    ts = [t for t in seri if t <= son]
    return seri[max(ts)] if ts else None


def fon(ft, kok):
    klasor, T = fiyat_kok(kok)
    G = T['gun']
    aylar = [(int(s['yil']), int(s['ay']), int(s['n'])) for s in fg.sayfala(
        ft, "SELECT yil, ay, COUNT(*) AS n FROM fon_portfoy_dagilim_raporlari WHERE yil >= 2025 AND ay IS NOT NULL GROUP BY yil, ay ORDER BY yil DESC, ay DESC")]
    aylar = [(y, a) for y, a, n in aylar if n >= 300]
    if len(aylar) < 2:
        sys.exit('HATA: iki aylık fon raporu bulunamadı')
    (y1, a1), (y0, a0) = aylar[0], aylar[1]
    if (y1 * 12 + a1) - (y0 * 12 + a0) != 1:
        sys.exit(f'HATA: ardışık olmayan aylar {y0}-{a0} ve {y1}-{a1}')

    def yukle(y, a):
        lot = {}
        fonlar = sorted({s['fon_kodu'] for s in fg.sayfala(ft, f"SELECT fon_kodu FROM fon_portfoy_dagilim_raporlari WHERE yil = {y} AND ay = {a} ORDER BY fon_kodu")})
        for i in range(0, len(fonlar), 20):
            liste = ','.join(f"'{f}'" for f in fonlar[i:i + 20])
            for s in fg.sayfala(ft, "SELECT r.fon_kodu, s.fon_kodu AS hisse, s.fondaki_lot FROM fon_portfoy_dagilim_raporlari r "
                                    "JOIN fon_portfoy_dagilim_raporu_sembol_agirliklari s ON s.fon_portfoy_dagilim_raporu_id = r.fon_portfoy_dagilim_raporu_id "
                                    f"JOIN hisse_senetleri h ON h.hisse_senedi_kodu = s.fon_kodu WHERE r.yil = {y} AND r.ay = {a} AND r.fon_kodu IN ({liste}) "
                                    "ORDER BY r.fon_kodu, s.fon_kodu"):
                v = num(s['fondaki_lot'])
                if v:
                    lot[(s['fon_kodu'], s['hisse'])] = lot.get((s['fon_kodu'], s['hisse']), 0) + v
            if (i // 20) % 5 == 0:
                log('  fon', y, a, i, '/', len(fonlar))
        return lot, set(fonlar)
    l0, f0 = yukle(y0, a0)
    l1, f1 = yukle(y1, a1)
    ikisi = f0 & f1
    log('fon: aylar', (y0, a0), (y1, a1), 'fon', len(f0), len(f1), 'ortak', len(ikisi), 'pozisyon', len(l0), len(l1))
    hisse_kodlari = {h for _, h in list(l0) + list(l1)}
    fiyat = {}
    for h in hisse_kodlari:
        s = fg.yukle(klasor, h, G)
        p = ay_sonu(s, y1, a1) if s else None
        if p:
            fiyat[h] = p
    liste, supheli = fon_hesapla(l0, l1, ikisi, fiyat)
    alinan = sorted((x for x in liste if x['net_tl'] > 0), key=lambda x: -x['net_tl'])[:12]
    satilan = sorted((x for x in liste if x['net_tl'] < 0), key=lambda x: x['net_tl'])[:12]
    # kategori nakit akışı (son 30 gün ve 7 gün; fon birden çok kategoride olabilir)
    nakit = {}
    for ad, gun in (('30', 30), ('7', 7)):
        bas = (bugun() - datetime.timedelta(days=gun)).isoformat()
        for s in fg.sayfala(ft, "SELECT k.baslik, SUM(g.gunluk_nakit_giris_cikisi) AS net, COUNT(DISTINCT g.fon_kodu) AS fon FROM gunluk_fon_degerleri g "
                                "JOIN fon_kategori_iliskileri i ON i.fon_kodu = g.fon_kodu JOIN fon_kategorileri k ON k.fon_kategori_id = i.fon_kategori_id "
                                f"WHERE g.tarih_europe_istanbul >= '{bas}' AND k.fon_tipi = 'mutual' AND ABS(g.gunluk_nakit_giris_cikisi) <= 0.6 * g.fon_buyuklugu GROUP BY k.baslik ORDER BY k.baslik"):
            if num(s['net']) is not None:
                nakit.setdefault(s['baslik'], {'fon': int(s['fon'])})['g' + ad] = round(num(s['net']))
    kat = [{'ad': k, 'fon': v['fon'], 'g30': v.get('g30', 0), 'g7': v.get('g7', 0)} for k, v in nakit.items()]
    kat.sort(key=lambda x: -x['g30'])
    toplam = {}
    for ad, gun in (('g30', 30), ('g7', 7)):
        bas = (bugun() - datetime.timedelta(days=gun)).isoformat()
        for s in fg.sayfala(ft, "SELECT SUM(g.gunluk_nakit_giris_cikisi) AS net, COUNT(DISTINCT g.fon_kodu) AS fon FROM gunluk_fon_degerleri g JOIN fonlar f ON f.fon_kodu = g.fon_kodu "
                                f"WHERE g.tarih_europe_istanbul >= '{bas}' AND f.fon_tipi = 'mutual' AND ABS(g.gunluk_nakit_giris_cikisi) <= 0.6 * g.fon_buyuklugu ORDER BY net"):
            if num(s['net']) is not None:
                toplam[ad] = {'net': round(num(s['net'])), 'fon': int(s['fon'])}
    yaz(kok, 'fon-dedektifi.json', {'guncelleme': bugun().isoformat(), 'rapor_ay': [y1, a1], 'onceki_ay': [y0, a0], 'fon_sayisi': len(ikisi),
                                    'alinan': alinan, 'satilan': satilan, 'bedelsiz_suphesi': sorted(supheli), 'kategori_giren': kat[:8], 'kategori_cikan': kat[::-1][:8], 'kategoriler': kat, 'akis_toplam': toplam, 'akis_bitis': bugun().isoformat(),
                                    'not': 'Lot farkı ay sonu kapanışıyla TL\'ye çevrilmiştir; fiyat etkisi içermez. Raporlar ay sonundan sonra ilk 10 günde yayımlanır. Bir günde fon büyüklüğünün yüzde 60 üzerinde görünen nakit hareketleri (tasfiye, birleşme, veri hatası) kategori toplamına katılmaz.'})
    log('fon: alınan', len(alinan), 'satılan', len(satilan), 'şüpheli', len(supheli), 'kategori', len(kat))


# ---------------------------------------------------------------- Halka arz röntgeni
def kurumlar(metin):
    return [k.strip() for p in (metin or '').replace('\r', '\n').split('\n') for k in p.split(' & ') if k.strip()]


def arz_getiri(p0, p1, usd0, usd1, tufe0, tufe1):
    """p0 başlangıç, p1 bugünkü fiyat (ikisi de bölünmeye göre düzeltilmiş). Nominal, dolar bazı ve reel (TÜFE) getiri, yüzde."""
    nom = p1 / p0 - 1
    usd = (p1 / usd1) / (p0 / usd0) - 1 if usd0 and usd1 else None
    reel = (1 + nom) / (tufe1 / tufe0) - 1 if tufe0 and tufe1 else None
    return nom * 100, None if usd is None else usd * 100, None if reel is None else reel * 100


def kurum_ligi(arzlar, en_az=5):
    gruplar = collections.defaultdict(list)
    for a in arzlar:
        for k in a['kurumlar']:
            gruplar[k].append(a)
    out = []
    for k, ls in gruplar.items():
        if len(ls) < en_az:
            continue
        med = lambda ad: None if not [a[ad] for a in ls if a.get(ad) is not None] else round(statistics.median(a[ad] for a in ls if a.get(ad) is not None), 1)
        reeller = [a['reel'] for a in ls if a.get('reel') is not None]
        out.append({'ad': k, 'arz': len(ls), 'nom_medyan': med('nom'), 'usd_medyan': med('usd'), 'reel_medyan': med('reel'),
                    'reel_kazandiran': round(100 * sum(1 for x in reeller if x > 0) / len(reeller)) if reeller else None, 'reel_n': len(reeller)})
    out.sort(key=lambda x: (x['reel_medyan'] is None, -(x['reel_medyan'] or 0)))
    return out


def tufe_al(ft):
    """{(yil, ay): endeks}. EVDS_API_KEY varsa TCMB EVDS (TP.FE25.OKTG01, TÜFE 2025=100), yoksa Fintables TUFE serisi."""
    anahtar = os.environ.get('EVDS_API_KEY', '').strip()
    if anahtar:
        yol = f"series=TP.FE25.OKTG01&startDate=01-01-2020&endDate={bugun().strftime('%d-%m-%Y')}&type=json"
        for taban in ('https://evds3.tcmb.gov.tr/igmevdsms-dis/', 'https://evds2.tcmb.gov.tr/service/evds/'):
            try:
                req = urllib.request.Request(taban + yol, headers={'key': anahtar, 'User-Agent': 'Endeks24-analiz/1', 'Accept': 'application/json'})
                y = urllib.request.urlopen(req, timeout=60)
                ham = y.read().decode('utf-8', 'replace')
                if not ham.lstrip().startswith(('{', '[')):
                    log('tüfe: EVDS yanıtı JSON değil', taban, y.status, repr(ham[:80]))
                    continue
                out = {}
                for x in json.loads(ham).get('items', []):
                    yil, ay = x['Tarih'].split('-')[:2]
                    v = x.get('TP_FE25_OKTG01')
                    if v not in (None, ''):
                        out[(int(yil), int(ay))] = float(v)
                if len(out) > 12:
                    log('tüfe: EVDS', taban, max(out))
                    return out
                log('tüfe: EVDS yetersiz veri', taban, len(out))
            except urllib.error.HTTPError as e:
                log('tüfe: EVDS HTTP', taban, e.code, repr(e.read()[:120]))
            except Exception as e:
                log('tüfe: EVDS okunamadı', taban, str(e)[:100])
    out = {}
    for s in fg.sayfala(ft, "SELECT zaman_utc, kapanis FROM mumlar_gunluk_gh WHERE kod = 'TUFE' AND zaman_utc >= TIMESTAMP '2020-01-01 00:00:00' ORDER BY zaman_utc"):
        t = datetime.datetime.fromisoformat(s['zaman_utc'].replace('Z', '+00:00')).astimezone(TR).date()
        out[(t.year, t.month)] = float(s['kapanis'])
    log('tüfe: Fintables', max(out) if out else None)
    return out


def arz(ft, kok):
    sat = fg.sayfala(ft, "SELECT hisse_senedi_kodu, araci_kurum, ilk_islem_tarihi_europe_istanbul, halka_arz_fiyati, duzeltilmis_halka_arz_fiyati "
                         f"FROM halka_arzlar WHERE ilk_islem_tarihi_europe_istanbul >= DATE '2020-01-01' AND ilk_islem_tarihi_europe_istanbul <= DATE '{bugun().isoformat()}' "
                         "ORDER BY ilk_islem_tarihi_europe_istanbul, hisse_senedi_kodu")
    arzlar = [{'kod': s['hisse_senedi_kodu'], 'tarih': s['ilk_islem_tarihi_europe_istanbul'][:10], 'kurumlar': kurumlar(s['araci_kurum']),
               'fiyat': num(s['halka_arz_fiyati']), 'duz': num(s['duzeltilmis_halka_arz_fiyati'])} for s in sat]
    son = {s['hisse_senedi_kodu']: num(s['son_fiyat']) for s in fg.sayfala(ft, "SELECT hisse_senedi_kodu, son_fiyat FROM hisse_senetleri ORDER BY hisse_senedi_kodu")}
    usd = {}
    for s in fg.sayfala(ft, "SELECT zaman_utc, kapanis FROM mumlar_gunluk_gh WHERE kod = 'USDTRY' AND zaman_utc >= TIMESTAMP '2020-12-01 00:00:00' ORDER BY zaman_utc"):
        usd[fg.gun(s['zaman_utc'])] = float(s['kapanis'])
    usd_gunler = sorted(usd)
    usd_son = usd[usd_gunler[-1]]
    usd_tarih = lambda d: usd[max(x for x in usd_gunler if x <= d)] if usd_gunler and d >= usd_gunler[0] else None
    tufe = tufe_al(ft)
    tufe_son_ay = max(tufe) if tufe else None
    bu_ay = (bugun().year, bugun().month)
    tufe_taze = bool(tufe_son_ay) and (bu_ay[0] * 12 + bu_ay[1]) - (tufe_son_ay[0] * 12 + tufe_son_ay[1]) <= 2
    # ilk işlem günü kapanışı (bölünmeye göre düzeltilmiş seri), 12'şerli gruplar
    ilk = {}
    parti = 12
    for i in range(0, len(arzlar), parti):
        g = arzlar[i:i + parti]
        kosul = ' OR '.join(f"(kod = '{a['kod']}' AND zaman_utc >= TIMESTAMP '{(datetime.date.fromisoformat(a['tarih']) - datetime.timedelta(days=1)).isoformat()} 00:00:00' "
                            f"AND zaman_utc < TIMESTAMP '{(datetime.date.fromisoformat(a['tarih']) + datetime.timedelta(days=12)).isoformat()} 00:00:00')" for a in g)
        for s in fg.sayfala(ft, f"SELECT DISTINCT ON (kod) kod, zaman_utc, kapanis FROM mumlar_gunluk_gh WHERE {kosul} ORDER BY kod, zaman_utc"):
            ilk[s['kod']] = (fg.gun(s['zaman_utc']), float(s['kapanis']))
        log('  arz', min(i + parti, len(arzlar)), '/', len(arzlar))
    cikti, islem_yok, veri_yok = [], 0, 0
    for a in arzlar:
        k = a['kod']
        if not son.get(k):
            islem_yok += 1
            continue
        if k not in ilk:
            veri_yok += 1
            continue
        d1, c1 = ilk[k]
        t0 = tufe.get((int(d1[:4]), int(d1[5:7])))
        t1 = tufe.get(tufe_son_ay) if tufe_taze else None
        nom, usd_g, reel = arz_getiri(c1, son[k], usd_tarih(d1), usd_son, t0, t1)
        satir = {'kod': k, 'tarih': a['tarih'], 'kurumlar': a['kurumlar'], 'fiyat': a['fiyat'], 'nom': r(nom, 1), 'usd': r(usd_g, 1), 'reel': r(reel, 1)}
        if a['duz']:
            satir['arz_nom'] = r((son[k] / a['duz'] - 1) * 100, 1)
        cikti.append(satir)
    yaz(kok, 'halka-arz.json', {'guncelleme': bugun().isoformat(), 'tufe_son': f'{tufe_son_ay[0]}-{tufe_son_ay[1]:02d}' if tufe_son_ay else None, 'tufe_taze': tufe_taze,
                                'arz_sayisi': len(arzlar), 'islem_gormeyen': islem_yok, 'veri_yok': veri_yok, 'arzlar': cikti, 'kurumlar': kurum_ligi(cikti),
                                'not': 'Getiriler ilk işlem günü kapanışından bugüne, bölünme ve temettüye göre düzeltilmiş fiyatlarla hesaplanır; "arz_nom" halka arz fiyatından getiridir (yalnız düzeltilmiş arz fiyatı olanlar).'})
    log('arz: toplam', len(arzlar), 'hesaplanan', len(cikti), 'işlem görmeyen', islem_yok, 'veri yok', veri_yok, 'tüfe taze', tufe_taze)


# ---------------------------------------------------------------- Bilanço sürprizi
def tepki_gunu(G, yayin):
    """Yayın anı (datetime, TR) için fiyat tepkisinin ölçüleceği işlem günü sırası. 18.00'den sonra ya da işlem günü değilse sonraki işlem günü."""
    d = yayin.date().isoformat()
    dk = yayin.hour * 60 + yayin.minute
    if d in set(G) and dk < 1080:
        return G.index(d)
    for i, g in enumerate(G):
        if g > d:
            return i
    return None


def tepki(seri, xu, G, i, gun=5):
    """i: tepki günü sırası. 1 işlem günü ve 5 işlem günü getiri ile BIST 100'e göre fark (yüzde puan)."""
    if i is None or i < 1:
        return None
    b = G[i - 1]
    out = {}
    for ad, n in (('g1', 1), ('g5', gun)):
        if i + n - 1 >= len(G):
            continue
        d = G[i + n - 1]
        if b in seri and d in seri and b in xu and d in xu:
            h = (seri[d] / seri[b] - 1) * 100
            e = (xu[d] / xu[b] - 1) * 100
            out[ad] = r(h, 1)
            out[ad + '_fark'] = r(h - e, 1)
    return out or None


def surpriz_hesapla(tahminler, gercek, yayin_gun):
    """tahminler: {kurum: [(tarih, net_kar)...]} artan; yayın gününden (yayin_gun, ISO) ÖNCE alınmış son değerlerin medyanı.
    Yayından önce kopyası olmayan kurum sayılmaz. Gerçek: ana ortaklık çeyreklik net kâr (TL)."""
    deg = []
    for ls in tahminler.values():
        once = [v for t, v in ls if t < yayin_gun and v is not None]
        if once:
            deg.append(once[-1])
    if len(deg) < 3:
        return None
    med = statistics.median(deg)
    sur = (gercek - med) / abs(med) * 100 if med else None
    return {'tahmin_medyan': round(med), 'tahmin_min': round(min(deg)), 'tahmin_maks': round(max(deg)), 'kurum': len(deg), 'gercek': round(gercek),
            'surpriz': r(sur, 1) if sur is not None else None}


def surpriz(ft, kok):
    ar = oku(kok, 'tahmin-arsiv.json', None)
    if not ar or not ar.get('kayit'):
        sys.exit('HATA: tahmin arşivi yok; önce tahmin modülü çalışmalı')
    klasor, T = fiyat_kok(kok)
    G = T['gun']
    xu = fg.yukle(klasor, 'XU100', G)
    ev = oku(kok, 'bilanco-surpriz.json', {'kayitlar': {}})
    bas = (bugun() - datetime.timedelta(days=75)).isoformat()
    yay = []
    for s in fg.sayfala(ft, "SELECT hisse_senedi_kodu, yil, ay, yayinlanma_tarihi_utc FROM hisse_finansal_tablolari "
                            f"WHERE yayinlanma_tarihi_utc >= TIMESTAMP '{bas} 00:00:00' AND yayinlanma_tarihi_utc IS NOT NULL ORDER BY yayinlanma_tarihi_utc"):
        t = datetime.datetime.fromisoformat(s['yayinlanma_tarihi_utc'].replace('Z', '+00:00')).astimezone(TR)
        yay.append((s['hisse_senedi_kodu'], int(s['yil']), int(s['ay']), t))
    # arşivdeki tahminleri hisse ve döneme göre grupla
    grup = collections.defaultdict(dict)
    for k, ls in ar['kayit'].items():
        h, kurum, y, a = k.split('|')
        grup[(h, int(y), int(a))][kurum] = [(x[0], x[3]) for x in ls]
    aday = [(h, y, a, t) for h, y, a, t in yay if (h, y, a) in grup and ev['kayitlar'].get(f'{h}|{y}|{a}', {}).get('tepki') is None]
    log('surpriz: yayın', len(yay), 'tahmini olan aday', len(aday))
    for i in range(0, len(aday), 15):
        g = aday[i:i + 15]
        kosul = ' OR '.join(f"(hisse_senedi_kodu = '{h}' AND yil = {y} AND ay = {a})" for h, y, a, _ in g)
        gercek = {}
        for s in fg.sayfala(ft, "SELECT hisse_senedi_kodu, yil, ay, try_ceyreklik FROM hisse_finansal_tablolari_gelir_tablosu_kalemleri "
                                f"WHERE ({kosul}) AND kalem = 'Ana Ortaklık Payları' ORDER BY hisse_senedi_kodu, yil, ay"):
            if num(s['try_ceyreklik']) is not None:
                gercek[(s['hisse_senedi_kodu'], int(s['yil']), int(s['ay']))] = num(s['try_ceyreklik'])
        for h, y, a, t in g:
            if (h, y, a) not in gercek:
                continue
            sonuc = surpriz_hesapla(grup[(h, y, a)], gercek[(h, y, a)], t.date().isoformat())
            if not sonuc:
                continue
            seri = fg.yukle(klasor, h, G)
            sonuc.update({'kod': h, 'yil': y, 'ay': a, 'yayin': t.isoformat(timespec='minutes'), 'tepki': tepki(seri, xu, G, tepki_gunu(G, t))})
            ev['kayitlar'][f'{h}|{y}|{a}'] = sonuc
    ev['guncelleme'] = bugun().isoformat()
    ev['arsiv_baslangic'] = ar.get('ilk')
    ev['not'] = 'Tahmin: aracı kurumların bilanço yayımından önce alınan son çeyreklik net kâr tahminlerinin medyanı (arşiv tarihli kopyalara dayanır). Gerçekleşen: ana ortaklık payına düşen çeyreklik net kâr.'
    yaz(kok, 'bilanco-surpriz.json', ev)
    log('surpriz: kayıt', len(ev['kayitlar']))


def evds_tani(ft, kok):
    """EVDS'te güncel TÜFE serisi kodunu bulmak için kategori, veri grubu ve seri listesini günlüğe yazar."""
    anahtar = os.environ.get('EVDS_API_KEY', '').strip()
    taban = 'https://evds3.tcmb.gov.tr/igmevdsms-dis/'

    def al(yol):
        req = urllib.request.Request(taban + yol, headers={'key': anahtar, 'User-Agent': 'Endeks24-analiz/1', 'Accept': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace'))
    for kat in al('categories/type=json'):
        ad = kat.get('TOPIC_TITLE_TR', '')
        if 'FİYAT' in ad.upper() or 'ENFLASYON' in ad.upper() or 'TÜKETİCİ' in ad.upper():
            log('kategori', kat.get('CATEGORY_ID'), ad)
            try:
                gruplar = al(f"datagroups/mode=2&code={int(float(kat['CATEGORY_ID']))}&type=json")
            except Exception as e:
                log('  grup listesi alınamadı', str(e)[:80])
                continue
            for g in gruplar:
                gad = g.get('DATAGROUP_NAME', '')
                if 'TÜFE' in gad.upper() or 'TÜKETİCİ' in gad.upper():
                    log('  grup', g.get('DATAGROUP_CODE'), gad, g.get('END_DATE'))
                    try:
                        for x in al(f"serieList/type=json&code={g['DATAGROUP_CODE']}")[:6]:
                            log('     seri', x.get('SERIE_CODE'), x.get('SERIE_NAME'), x.get('START_DATE'), x.get('END_DATE'))
                    except Exception as e:
                        log('     seri listesi alınamadı', str(e)[:80])


MODULLER = {'tahmin': tahmin, 'tasiyici': tasiyici, 'fon': fon, 'arz': arz, 'surpriz': surpriz, 'evds': evds_tani}

if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in MODULLER:
        sys.exit(__doc__)
    import hafiza_hesapla as hh
    MODULLER[sys.argv[1]](hh.baglan(), sys.argv[2])
