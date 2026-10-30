"""Endeks24 Fon Karşılaştırma verisi (28.10.2026). Yapay zeka çağrısı yoktur; Fintables'tan (salt okuma) TEFAS'ta işlem gören yatırım ve emeklilik fonları okunur.

Çıktı (<kök>/fon/):
  ozet.json      {"olusturma","fiyat_tarihi","n","kategoriler":[...],"hafta":[tarihler],"fonlar":[{k,ad,t,pys,kat,r,yu,st,b,y,ak,h1h,h1a,h3a,h6a,hyb,h1y,vs,vsy}]}
  seri/<H>.json  {"<KOD>": [haftalık kapanışlar (ozet.hafta ile aynı sıra, yoksa null)]}   H = kodun ilk harfi
  dagilim/<H>.json {"<KOD>": [[varlık sınıfı, yüzde],...]} en büyük 6 sınıf
Getiri = fon fiyatındaki yüzde değişim (stopaj ve yönetim ücreti fiyata dahildir). Kullanım: python3 fon_veri.py <kök_klasör>. Anahtar FINTABLES ortam değişkeninde (GitHub sırrı; süresi dolunca yenilenir).
"""
import datetime, json, os, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TR = datetime.timezone(datetime.timedelta(hours=3))
HAFTA = 53


def log(*a):
    print(*a, flush=True)


def r(x, n=2):
    return None if x is None else round(float(x), n)


def gun(zaman_utc):
    return datetime.datetime.fromisoformat(zaman_utc.replace('Z', '+00:00')).astimezone(TR).date()


def ay_geri(d, ay):
    y, m = d.year, d.month - ay
    while m <= 0:
        m += 12
        y -= 1
    son = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return datetime.date(y, m, min(d.day, son))


def getiri(son, eski):
    """Yüzde değişim; fiyatlar yoksa ya da sonuç makul değilse (-%99 altı, +%5000 üstü) boş."""
    if not son or not eski or eski <= 0:
        return None
    g = (son / eski - 1) * 100
    return round(g, 2) if -99 <= g <= 5000 else None


def kodlar_sorgu(ft, sorgu):
    import fiyat_gecmisi as fg
    return fg.sayfala(ft, sorgu)


def kapanis_gunu(ft, bit, genislik=8):
    """[bit-genişlik, bit] aralığında fon başına son kapanış: {kod: (tarih, kapanış)}."""
    bas = bit - datetime.timedelta(days=genislik)
    sat = kodlar_sorgu(ft, f"SELECT kod, zaman_utc, kapanis FROM (SELECT m.kod, m.zaman_utc, m.kapanis, ROW_NUMBER() OVER (PARTITION BY m.kod ORDER BY m.zaman_utc DESC) rn "
                           f"FROM mumlar_gunluk_gh m JOIN fonlar f ON f.fon_kodu = m.kod WHERE m.zaman_utc >= TIMESTAMP '{bas.isoformat()} 00:00:00' "
                           f"AND m.zaman_utc < TIMESTAMP '{(bit + datetime.timedelta(days=1)).isoformat()} 00:00:00' AND f.tefasa_acik = true "
                           f"AND f.fon_tipi IN ('mutual', 'pension')) t WHERE rn = 1 ORDER BY kod")
    return {s['kod']: (gun(s['zaman_utc']), float(s['kapanis'])) for s in sat if s.get('kapanis') is not None}


def hafta_cuma(bugun):
    """Son HAFTA cuma günü (bugün cumaysa dahil, sonra eski -> yeni)."""
    d = bugun - datetime.timedelta(days=(bugun.weekday() - 4) % 7)
    return [d - datetime.timedelta(days=7 * i) for i in range(HAFTA - 1, -1, -1)]


def main(kok):
    import hafiza_hesapla as hh
    ft = hh.baglan()
    bugun = datetime.datetime.now(TR).date()
    istek = f"f.tefasa_acik = true AND f.fon_tipi IN ('mutual', 'pension')"

    fonlar = {s['fon_kodu']: s for s in kodlar_sorgu(ft, f"SELECT f.fon_kodu, f.unvan, f.fon_tipi, f.risk_seviyesi, f.yonetim_ucreti, f.stopaj, f.portfoy_yonetim_sirketi_kodu AS pk FROM fonlar f WHERE {istek} ORDER BY f.fon_kodu")}
    pys = {}
    for s in kodlar_sorgu(ft, "SELECT portfoy_yonetim_sirketi_kodu, unvan FROM portfoy_yonetim_sirketleri ORDER BY portfoy_yonetim_sirketi_kodu"):
        pys.setdefault(s['portfoy_yonetim_sirketi_kodu'], s['unvan'])
    log('fon', len(fonlar), 'pyş', len(pys))

    kat_ad, kat_fon = [], collections.defaultdict(list)
    for s in kodlar_sorgu(ft, f"SELECT i.fon_kodu, k.baslik FROM fon_kategori_iliskileri i JOIN fon_kategorileri k ON k.fon_kategori_id = i.fon_kategori_id JOIN fonlar f ON f.fon_kodu = i.fon_kodu WHERE {istek} ORDER BY i.fon_kodu, k.baslik"):
        if s['baslik'] not in kat_ad:
            kat_ad.append(s['baslik'])
        kat_fon[s['fon_kodu']].append(kat_ad.index(s['baslik']))

    bas_deger = (bugun - datetime.timedelta(days=12)).isoformat()
    deger = {s['fon_kodu']: s for s in kodlar_sorgu(ft, f"SELECT DISTINCT ON (g.fon_kodu) g.fon_kodu, g.tarih_europe_istanbul, g.fon_buyuklugu, g.yatirimci_sayisi FROM gunluk_fon_degerleri g "
                                                         f"JOIN fonlar f ON f.fon_kodu = g.fon_kodu WHERE g.tarih_europe_istanbul >= '{bas_deger}' AND {istek} ORDER BY g.fon_kodu, g.tarih_europe_istanbul DESC")}
    bas_akis = (bugun - datetime.timedelta(days=30)).isoformat()
    akis = {s['fon_kodu']: s['net'] for s in kodlar_sorgu(ft, f"SELECT g.fon_kodu, SUM(g.gunluk_nakit_giris_cikisi) AS net FROM gunluk_fon_degerleri g JOIN fonlar f ON f.fon_kodu = g.fon_kodu "
                                                          f"WHERE g.tarih_europe_istanbul >= '{bas_akis}' AND {istek} GROUP BY g.fon_kodu ORDER BY g.fon_kodu")}
    log('değer', len(deger), 'akış', len(akis))

    son = kapanis_gunu(ft, bugun, 10)
    fiyat_tarihi = max((v[0] for v in son.values()), default=None)
    if not fiyat_tarihi or len(son) < 800:
        log('çok az fon fiyatı, dosya yazılmadı', len(son))
        sys.exit(1)
    ref = {'h1h': bugun - datetime.timedelta(days=7), 'h1a': ay_geri(bugun, 1), 'h3a': ay_geri(bugun, 3), 'h6a': ay_geri(bugun, 6),
           'hyb': datetime.date(bugun.year - 1, 12, 31), 'h1y': ay_geri(bugun, 12)}
    eski = {a: kapanis_gunu(ft, d, 8) for a, d in ref.items()}
    log('getiri referansları', {a: len(v) for a, v in eski.items()})

    # Haftalık seri: cuma kapanışları (UTC'de perşembe 21:00). Tatile denk gelen cuma boş kalır, grafik o noktayı atlar.
    hafta = hafta_cuma(bugun)
    ilk = hafta[0]
    son_nokta = fiyat_tarihi if fiyat_tarihi > hafta[-1] else None   # grafik son kapanışla biter
    ham = collections.defaultdict(dict)
    kodlar = sorted(son)
    # Sorgu başına en fazla 5000 satır okunabilir (OFFSET sınırı): seri 80 fonluk, dağılım 300 fonluk gruplarla okunur.
    for i in range(0, len(kodlar), 80):
        liste = ','.join(f"'{k}'" for k in kodlar[i:i + 80])
        for s in kodlar_sorgu(ft, f"SELECT m.kod, m.zaman_utc, m.kapanis FROM mumlar_gunluk_gh m WHERE m.kod IN ({liste}) AND m.zaman_utc >= TIMESTAMP '{(ilk - datetime.timedelta(days=1)).isoformat()} 00:00:00' "
                                   f"AND EXTRACT(DOW FROM m.zaman_utc) = 4 ORDER BY m.kod, m.zaman_utc"):
            if s.get('kapanis') is not None:
                ham[s['kod']][gun(s['zaman_utc']).isoformat()] = float(s['kapanis'])
    log('seri', len(ham))

    dag = collections.defaultdict(list)
    bas_dag = (bugun - datetime.timedelta(days=45)).isoformat()
    for i in range(0, len(kodlar), 300):
        liste = ','.join(f"'{k}'" for k in kodlar[i:i + 300])
        for s in kodlar_sorgu(ft, f"SELECT d.fon_kodu, d.varlik_sinifi, d.yuzdesel_agirlik FROM gunluk_fon_varlik_sinifi_dagilimlari d JOIN (SELECT g.fon_kodu, MAX(g.tarih_europe_istanbul) AS t FROM gunluk_fon_varlik_sinifi_dagilimlari g "
                                   f"WHERE g.tarih_europe_istanbul >= '{bas_dag}' AND g.fon_kodu IN ({liste}) GROUP BY g.fon_kodu) m ON m.fon_kodu = d.fon_kodu AND m.t = d.tarih_europe_istanbul ORDER BY d.fon_kodu, d.yuzdesel_agirlik DESC, d.varlik_sinifi"):
            if s.get('yuzdesel_agirlik') and float(s['yuzdesel_agirlik']) > 0:
                dag[s['fon_kodu']].append([s['varlik_sinifi'], r(s['yuzdesel_agirlik'], 1)])

    satirlar = []
    for kod, f in fonlar.items():
        if kod not in son or (fiyat_tarihi - son[kod][0]).days > 7:
            continue   # fiyatı yok ya da durmuş fon
        c = son[kod][1]
        d = deger.get(kod) or {}
        b = d.get('fon_buyuklugu')
        s = {'k': kod, 'ad': f['unvan'], 't': 'e' if f['fon_tipi'] == 'pension' else 'y', 'pys': pys.get(f.get('pk')), 'kat': kat_fon.get(kod, []),
             'r': f.get('risk_seviyesi'), 'yu': r(f.get('yonetim_ucreti'), 2), 'st': r(f.get('stopaj'), 1),
             'b': r(b, 0) if b else None, 'y': d.get('yatirimci_sayisi'), 'ak': r(akis.get(kod), 0)}
        for a in ref:
            s[a] = getiri(c, (eski[a].get(kod) or (None, None))[1])
        top = dag.get(kod) or []
        s['vs'] = top[0][0] if top else None
        s['vsy'] = top[0][1] if top else None
        satirlar.append(s)
    satirlar.sort(key=lambda z: -(z['b'] or 0))
    if len(satirlar) < 800:
        log('çok az fon, dosya yazılmadı', len(satirlar))
        sys.exit(1)

    os.makedirs(f'{kok}/fon/seri', exist_ok=True)
    os.makedirs(f'{kok}/fon/dagilim', exist_ok=True)
    seri, dagil = collections.defaultdict(dict), collections.defaultdict(dict)
    for s in satirlar:
        kod = s['k']
        h = ham.get(kod, {})
        seri[kod[0]][kod] = [r(h.get(d.isoformat()), 6) for d in hafta] + ([r(son[kod][1], 6)] if son_nokta else [])
        dagil[kod[0]][kod] = (dag.get(kod) or [])[:6]
    for h, v in seri.items():
        json.dump(v, open(f'{kok}/fon/seri/{h}.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    for h, v in dagil.items():
        json.dump(v, open(f'{kok}/fon/dagilim/{h}.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    cikti = {'olusturma': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M:%S+03:00'), 'fiyat_tarihi': fiyat_tarihi.isoformat(), 'n': len(satirlar),
             'kategoriler': kat_ad, 'hafta': [d.isoformat() for d in hafta + ([son_nokta] if son_nokta else [])], 'fonlar': satirlar}
    json.dump(cikti, open(f'{kok}/fon/ozet.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    say = lambda a: sum(1 for z in satirlar if z[a] is not None)
    log('TAMAM', len(satirlar), 'fon | 1A', say('h1a'), '1Y', say('h1y'), 'YBB', say('hyb'), 'büyüklük', say('b'), 'dağılım', sum(1 for z in satirlar if z['vs']))


if __name__ == '__main__':
    main(sys.argv[1])
