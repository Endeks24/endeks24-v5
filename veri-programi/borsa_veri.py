"""Endeks24 Borsa Ekranı ve hisse sayfaları verisi (26.10.2026). Yapay zeka çağrısı yoktur; Fintables MCP'den salt okunur.

Çıktı (<kök>/borsa/): ozet.json (ekran: nabız, hareketliler, hacim haritası, BIST 100 serisi, hisse tablosu, günün "neden" kartı)
ve hisse/<KOD>.json (her hissenin sayfası: künye, 60 günlük seri, hedef fiyatlar, açığa satış, tedbir, KAP ve KAP'tan bu yana, "neden" kartı).
Kullanım: python3 borsa_veri.py <kök_klasör>     Anahtar FINTABLES ortam değişkeninde.
Fiyatlar günlük kapanıştır (hacim 15 dk gecikmeli kaynaktan); sayfa "son kapanış" der.
"""
import collections, datetime, json, os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiyat_gecmisi as fg
import hafiza_hesapla as hh

TR = fg.TR


def log(*a):
    print(*a, flush=True)


def num(x):
    try:
        return float(x) if x not in (None, '', 'null') else None
    except ValueError:
        return None


def r(x, n=2):
    return None if x is None else round(x, n)


def yuzde(a, b):
    return None if not a or not b else (b / a - 1) * 100


def parcala(liste, n):
    for i in range(0, len(liste), n):
        yield liste[i:i + n]


def kodlu(k):
    return ', '.join("'" + x.replace("'", '') + "'" for x in k)


def tr_gun(utc_iso):
    return datetime.datetime.fromisoformat(utc_iso.replace('Z', '+00:00')).astimezone(TR)


# ------------------------------------------------------------------ okuma
def hisseler(ft):
    out = {}
    for s in fg.sayfala(ft, "SELECT hisse_senedi_kodu, unvan, sektor_id, fiili_dolasim_orani, endeksler, piyasa_degeri FROM hisse_senetleri ORDER BY hisse_senedi_kodu"):
        try:
            e = json.loads(s['endeksler']) if s.get('endeksler') else []
        except ValueError:
            e = []
        out[s['hisse_senedi_kodu']] = {'ad': s['unvan'], 'sektor': s['sektor_id'], 'dolasim': num(s['fiili_dolasim_orani']), 'endeksler': e, 'pd': num(s['piyasa_degeri'])}
    return out


def mumlar(ft, kodlar, bas):
    seri = collections.defaultdict(list)
    for grup in parcala(sorted(kodlar), 40):
        sat = fg.sayfala(ft, f"SELECT kod, zaman_utc, yuksek, dusuk, kapanis, hacim_15_dk_gecikmeli AS h FROM mumlar_gunluk_gh WHERE kod IN ({kodlu(grup)}) "
                             f"AND zaman_utc >= TIMESTAMP '{bas} 00:00:00' ORDER BY kod, zaman_utc")
        for s in sat:
            c = num(s['kapanis'])
            if c:
                seri[s['kod']].append((fg.gun(s['zaman_utc']), c, num(s['yuksek']), num(s['dusuk']), num(s['h']) or 0.0))
        log('  mum', sum(len(v) for v in seri.values()))
    return seri


def endeks_seri(ft, bas):
    sat = fg.sayfala(ft, f"SELECT zaman_utc, kapanis FROM endeks_mumlar_gunluk_gh WHERE kod = 'XU100' AND zaman_utc >= TIMESTAMP '{bas} 00:00:00' ORDER BY zaman_utc")
    return [(fg.gun(s['zaman_utc']), float(s['kapanis'])) for s in sat if num(s['kapanis'])]


def usd_seri(ft, bas):
    sat = fg.sayfala(ft, f"SELECT zaman_utc, kapanis FROM mumlar_gunluk_gh WHERE kod = 'USDTRY' AND zaman_utc >= TIMESTAMP '{bas} 00:00:00' ORDER BY zaman_utc")
    return [(fg.gun(s['zaman_utc']), float(s['kapanis'])) for s in sat if num(s['kapanis'])]


def gun_ici(ft, kod, gun, tablo='mumlar_15dk_gh'):
    """Bir işlem gününün 15 dakikalık kapanışları (TR saatiyle). {'t': [...], 'c': [...], 'v': [mn TL]}"""
    g = datetime.date.fromisoformat(gun)
    b = datetime.datetime.combine(g - datetime.timedelta(days=1), datetime.time(21, 0))
    e = datetime.datetime.combine(g, datetime.time(21, 0))
    sat = fg.sayfala(ft, f"SELECT zaman_utc, kapanis, hacim_15_dk_gecikmeli AS h FROM {tablo} WHERE kod = '{kod}' AND zaman_utc >= TIMESTAMP '{b:%Y-%m-%d %H:%M:%S}' "
                         f"AND zaman_utc < TIMESTAMP '{e:%Y-%m-%d %H:%M:%S}' ORDER BY zaman_utc")
    out = {'t': [], 'c': [], 'v': []}
    for x in sat:
        z = tr_gun(x['zaman_utc'])
        if z.hour < 10 or (z.hour == 18 and z.minute > 15) or z.hour > 18:
            continue
        out['t'].append(f'{z:%H:%M}'); out['c'].append(num(x['kapanis'])); out['v'].append(round((num(x['h']) or 0) / 1e6))
    return out


def gun_ici_toplu(ft, kodlar, gun):
    """Birçok hissenin son seans 15 dakikalık kapanışları (kod -> {'t','c','v'}); 40'lı gruplarla"""
    g = datetime.date.fromisoformat(gun)
    b = datetime.datetime.combine(g - datetime.timedelta(days=1), datetime.time(21, 0))
    e = datetime.datetime.combine(g, datetime.time(21, 0))
    out = collections.defaultdict(lambda: {'t': [], 'c': [], 'v': []})
    for grup in parcala(sorted(kodlar), 40):
        try:
            sat = fg.sayfala(ft, f"SELECT kod, zaman_utc, kapanis, hacim_15_dk_gecikmeli AS h FROM mumlar_15dk_gh WHERE kod IN ({kodlu(grup)}) AND zaman_utc >= TIMESTAMP '{b:%Y-%m-%d %H:%M:%S}' "
                                 f"AND zaman_utc < TIMESTAMP '{e:%Y-%m-%d %H:%M:%S}' ORDER BY kod, zaman_utc")
        except Exception as x:
            log('  gün içi grup atlandı', str(x)[:80]); continue
        for x in sat:
            z = tr_gun(x['zaman_utc'])
            if z.hour < 10 or (z.hour == 18 and z.minute > 15) or z.hour > 18 or not num(x['kapanis']):
                continue
            o = out[x['kod']]; o['t'].append(f'{z:%H:%M}'); o['c'].append(num(x['kapanis'])); o['v'].append(round((num(x['h']) or 0) / 1e6))
    log('  gün içi hisse', len(out))
    return out


def seri_limit(c):
    """Son kapanışlardan geriye, art arda tavan (+) ya da taban (-) gün sayısı. (yön, adet)"""
    yon, n = 0, 0
    for i in range(len(c) - 1, 0, -1):
        d = yuzde(c[i - 1], c[i])
        y = 1 if d is not None and d >= 9.4 else -1 if d is not None and d <= -9.4 else 0
        if y == 0 or (yon and y != yon):
            break
        yon = y; n += 1
    return yon, n


def hedefler(ft, bas, bit):
    out = collections.defaultdict(list)
    t = datetime.date.fromisoformat(bas)
    son = datetime.date.fromisoformat(bit)
    while t <= son:
        u = min(t + datetime.timedelta(days=10), son + datetime.timedelta(days=1))
        sat = fg.sayfala(ft, "SELECT hf.hisse_senedi_kodu AS kod, ak.kisa_unvan AS kurum, hf.araci_kurum_kodu AS kk, hf.yayin_tarihi_europe_istanbul AS t, hf.tavsiye, hf.hedef_fiyat AS h "
                             "FROM hisse_senedi_araci_kurum_hedef_fiyatlari hf LEFT JOIN araci_kurumlar ak ON ak.araci_kurum_kodu = hf.araci_kurum_kodu "
                             f"WHERE hf.yayin_tarihi_europe_istanbul >= DATE '{t.isoformat()}' AND hf.yayin_tarihi_europe_istanbul < DATE '{u.isoformat()}' AND hf.hedef_fiyat IS NOT NULL ORDER BY hf.hisse_senedi_kodu, hf.yayin_tarihi_europe_istanbul")
        for s in sat:
            out[s['kod']].append({'k': s['kurum'] or s['kk'], 't': s['t'][:10], 'v': s['tavsiye'], 'h': num(s['h'])})
        t = u
    return out


def aciga(ft, bas):
    out = collections.defaultdict(list)
    t = datetime.date.fromisoformat(bas)
    while t <= datetime.datetime.now(TR).date():
        sat = fg.sayfala(ft, f"SELECT hisse_senedi_kodu AS kod, aciga_satis_hacmi_tl AS a, toplam_islem_hacmi_tl AS y FROM gunluk_aciga_satis_istatistikleri WHERE tarih_europe_istanbul = DATE '{t.isoformat()}'")
        for s in sat:
            a, y = num(s['a']), num(s['y'])
            if a and y:
                out[s['kod']].append((t.isoformat(), a / y * 100))
        t += datetime.timedelta(days=1)
    return out


def tedbirler(ft, bugun):
    out = collections.defaultdict(list)
    for s in fg.sayfala(ft, f"SELECT hisse_senedi_kodu AS kod, tedbir_tipi AS t, tedbir_bitis_tarihi_europe_istanbul AS b FROM hisse_vbts_tedbirleri WHERE DATE '{bugun}' BETWEEN tedbir_baslangic_tarihi_europe_istanbul AND tedbir_bitis_tarihi_europe_istanbul"):
        out[s['kod']].append({'tip': s['t'], 'bitis': (s['b'] or '')[:10]})
    return out


KAP_TIP = {'ODA': 'Özel durum açıklaması', 'FR': 'Finansal rapor', 'DUY': 'Duyuru'}


def kap(ft, bas, bit):
    """[bas, bit) arası ODA ve FR bildirimleri (günlük pencerelerle; 1000 sınırına dayanırsa pencere bölünür). {kod: [bildirim]}"""
    out = collections.defaultdict(dict)

    def pencere(b, e, tip, derinlik=0):
        filtre = (f'dokuman_tipi = "kap_haberi" AND kap_bildirim_tipi = "{tip}" AND yayinlanma_tarihi_utc >= "{b.strftime("%Y-%m-%dT%H:%M:%SZ")}" '
                  f'AND yayinlanma_tarihi_utc < "{e.strftime("%Y-%m-%dT%H:%M:%SZ")}"')
        s1 = ft.arac('dokumanlarda_ara', {'query': '', 'filter': filtre, 'sayfa': 1, 'sayfa_basi': 50, 'sirala': 'yayinlanma_tarihi_utc:desc'})
        if s1.get('toplam', 0) >= 1000 and (e - b) > datetime.timedelta(hours=2):
            o = b + (e - b) / 2
            pencere(b, o, tip, derinlik + 1); pencere(o, e, tip, derinlik + 1)
            return
        for s in range(1, s1.get('toplam_sayfa', 1) + 1):
            res = s1 if s == 1 else ft.arac('dokumanlarda_ara', {'query': '', 'filter': filtre, 'sayfa': s, 'sayfa_basi': 50, 'sirala': 'yayinlanma_tarihi_utc:desc'})
            for x in res.get('sonuclar', []):
                sem = x.get('iliskili_semboller') or []
                if not sem or len(sem) > 6:
                    continue
                for k in sem:
                    out[k][x['kap_bildirim_id']] = {'id': x['kap_bildirim_id'], 'u': x['yayinlanma_tarihi_utc'], 'tip': tip, 'konu': x.get('kap_bildirim_konu') or x.get('document_title'),
                                                    'baslik': x.get('document_title'), 'url': x.get('dokuman_orijinal_url')}
    t = bas
    while t < bit:
        u = min(t + datetime.timedelta(days=1), bit)
        for tip in ('ODA', 'FR'):
            try:
                pencere(t, u, tip)
            except Exception as ex:
                log('  kap hatası', t, tip, str(ex)[:80])
        t = u
    return {k: sorted(v.values(), key=lambda z: z['u'], reverse=True) for k, v in out.items()}


# ------------------------------------------------------------------ hesap
def ortalama(a):
    return sum(a) / len(a) if a else None


def neden_kartlari(kod, mum, xu, ac, ted, kp, hacim_ort):
    """Günün ve 25 günün 'neden' maddeleri. Her madde {t: etiket, m: metin}."""
    c = mum
    if len(c) < 3:
        return None
    son, onc = c[-1], c[-2]
    d = yuzde(onc[1], son[1])
    xd = {g: v for g, v in xu}
    xg = yuzde(xd.get(onc[0]), xd.get(son[0]))
    maddeler = []
    if d is not None and xg is not None:
        fark = d - xg
        maddeler.append({'t': 'Endeks', 'm': f"BIST 100 aynı gün %{abs(xg):.2f}".replace('.', ',') + (' düştü' if xg < 0 else ' yükseldi') + f"; {kod} endeksten yaklaşık {abs(fark):.0f} puan " + ('zayıf' if fark < 0 else 'güçlü') + ' kaldı.'})
    if hacim_ort:
        oran = son[4] / hacim_ort
        maddeler.append({'t': 'Hacim', 'm': f"{son[4] / 1e9:.1f} milyar TL".replace('.', ',') + f", son 20 işlem günü ortalamasının {oran:.1f} katı.".replace('.', ',') if oran >= 1.3 else f"{son[4] / 1e9:.1f} milyar TL; son 20 gün ortalamasına yakın.".replace('.', ',')})
    a = [x for x in ac if x[0] <= son[0]][-2:]
    if a:
        maddeler.append({'t': 'Açığa satış', 'm': f"Hacmin %{a[-1][1]:.1f}'i".replace('.', ',') + (f" (önceki gün %{a[-2][1]:.1f})".replace('.', ',') if len(a) > 1 else '') + ('; ' + ('aktif tedbir: ' + ', '.join(x['tip'] for x in ted)) if ted else '; aktif tedbir yok') + '.'})
    elif ted:
        maddeler.append({'t': 'Tedbir', 'm': 'Aktif tedbir: ' + ', '.join(x['tip'] for x in ted) + '.'})
    gun_kap = [k for k in kp if tr_gun(k['u']).date().isoformat() >= (datetime.date.fromisoformat(onc[0]) + datetime.timedelta(days=0)).isoformat() and tr_gun(k['u']).date().isoformat() <= son[0]]
    if gun_kap:
        k = gun_kap[0]
        z = tr_gun(k['u'])
        maddeler.append({'t': 'KAP', 'm': f"{z.day} {AYLAR[z.month - 1]} {z:%H.%M}: {k['konu']}.", 'u': k.get('url')})
    return {'d': r(d), 'maddeler': maddeler}


AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def main(kok):
    ft = hh.baglan()
    bugun = datetime.datetime.now(TR).date()
    bas = (bugun - datetime.timedelta(days=100)).isoformat()
    H = hisseler(ft)
    log('hisse', len(H))
    M = mumlar(ft, list(H), bas)
    XU = endeks_seri(ft, bas)
    if len(XU) < 20:
        sys.exit('HATA: BIST 100 serisi kısa')
    son_gun = XU[-1][0]
    log('son gün', son_gun)
    HF = hedefler(ft, (bugun - datetime.timedelta(days=120)).isoformat(), bugun.isoformat())
    AC = aciga(ft, (bugun - datetime.timedelta(days=14)).isoformat())
    TD = tedbirler(ft, son_gun)
    KP = kap(ft, datetime.datetime.combine(bugun - datetime.timedelta(days=21), datetime.time(0, 0)), datetime.datetime.combine(bugun + datetime.timedelta(days=1), datetime.time(0, 0)))
    log('hedef', len(HF), 'aciga', len(AC), 'kap', len(KP))
    USD = usd_seri(ft, bas)
    xd = dict(XU)
    kayitlar, tablo, seriler = {}, [], []
    GI = gun_ici_toplu(ft, [k for k, v in M.items() if k in H and v and v[-1][0] == son_gun], son_gun)
    for kod, v in M.items():
        if kod not in H or not v or v[-1][0] != son_gun or len(v) < 3:
            continue
        son, onc = v[-1], v[-2]
        d = yuzde(onc[1], son[1])
        g5 = yuzde(v[-6][1], son[1]) if len(v) >= 6 else None
        g30 = yuzde(v[-23][1], son[1]) if len(v) >= 23 else None
        hacim_ort = ortalama([x[4] for x in v[-21:-1]]) if len(v) >= 21 else None
        pd = H[kod]['pd']
        hr = son[4] / hacim_ort if hacim_ort else None
        fr_gun = [k for k in KP.get(kod, []) if k['tip'] == 'FR' and onc[0] <= tr_gun(k['u']).date().isoformat() <= son_gun]
        oda_gun = [k for k in KP.get(kod, []) if k['tip'] == 'ODA' and onc[0] < tr_gun(k['u']).date().isoformat() <= son_gun]
        n_et, n_tur = '', ''
        if d is not None and d >= 9.5:
            n_et, n_tur = ('Bilanço sonrası tavan' if fr_gun else 'Tavan'), 'y'
        elif d is not None and d <= -9.5:
            n_et, n_tur = ('Bilanço sonrası taban' if fr_gun else 'Taban'), 'k'
        elif hr and hr >= 2:
            n_et, n_tur = f"Hacim {hr:.1f}×".replace('.', ','), 'n'
        elif oda_gun and d is not None and abs(d) >= 3:
            n_et, n_tur = 'KAP açıklaması', 'n'
        yon, adet = seri_limit([x[1] for x in v[-25:]])
        if adet >= 3:
            seriler.append({'k': kod, 'y': yon, 'n': adet, 'c': [round(x[1], 2) for x in v[-21:]], 's': son[1], 'd': r(yuzde(v[-adet - 1][1], son[1]), 1)})
        tablo.append({'k': kod, 's': son[1], 'd': r(d), 'h5': r(g5, 1), 'h30': r(g30, 1), 'hc': round(son[4] / 1e6), 'hr': r(hr, 1), 'pd': pd, 'sp': [round(x[1], 2) for x in v[-20:]],
                      'n': n_et, 'nt': n_tur, 'e': [x for x in H[kod]['endeksler'] if x in ('XU030', 'XU100', 'XUGRA')]})
        # seri
        n25 = v[-25:]
        x0, x1 = xd.get(n25[0][0]), xd.get(n25[-1][0])
        perf = yuzde(n25[0][1], n25[-1][1])
        xperf = yuzde(x0, x1)
        ac = AC.get(kod, [])
        ac8 = ac[-8:]
        kp = KP.get(kod, [])
        # KAP'tan bu yana
        etki = []
        fiyat_gun = {g: c for g, c, *_ in v}
        for k in kp:
            z = tr_gun(k['u'])
            g = z.date().isoformat()
            if g not in fiyat_gun:
                gs = [x for x in fiyat_gun if x >= g]
                if not gs:
                    continue
                g = gs[0]
            etki.append({'t': k['u'][:16], 'konu': k['konu'], 'u': k.get('url'), 'y': r(yuzde(fiyat_gun[g], son[1]), 1)})
            if len(etki) >= 5:
                break
        hf = sorted([x for x in HF.get(kod, [])], key=lambda z: z['t'], reverse=True)
        son_kurum = {}
        for x in hf:
            son_kurum.setdefault(x['k'], x)
        hs = sorted(son_kurum.values(), key=lambda z: -z['h'])
        med = statistics.median([x['h'] for x in hs]) if hs else None
        neden = neden_kartlari(kod, v, XU, ac, TD.get(kod, []), kp, hacim_ort)
        kayitlar[kod] = {
            'kod': kod, 'ad': H[kod]['ad'], 'sektor': H[kod]['sektor'], 'endeksler': H[kod]['endeksler'], 'dolasim': H[kod]['dolasim'], 'pd': pd,
            'tarih': son_gun, 'son': son[1], 'd': r(d), 'yuksek': son[2], 'dusuk': son[3], 'hacim': son[4], 'hacim_ort': r(hacim_ort, 0),
            'gi': GI.get(kod) if GI.get(kod) and len(GI[kod]['c']) >= 8 else None, 'on': onc[1],
            'g': [x[0] for x in v[-60:]], 'c': [x[1] for x in v[-60:]], 'h': [round(x[4] / 1e6) for x in v[-60:]], 'xu': [xd.get(x[0]) for x in v[-60:]],
            'perf25': r(perf, 1), 'xu25': r(xperf, 1), 'bas25': n25[0][1], 'basg25': n25[0][0], 'xu0': x0, 'xu1': x1,
            'hedef': [{'k': x['k'], 'h': x['h'], 't': x['t'], 'v': x['v']} for x in hs], 'hedef_medyan': r(med), 'hedef_n': len(hs),
            'as': [{'t': t, 'o': r(o, 1)} for t, o in ac8], 'tedbir': TD.get(kod, []),
            'kap': [{'t': k['u'][:16], 'konu': k['konu'], 'tip': k['tip'], 'u': k.get('url')} for k in kp[:6]], 'etki': etki, 'neden': neden}
    # akran: aynı sektör, piyasa değerine göre
    by = collections.defaultdict(list)
    for kod, k in kayitlar.items():
        by[k['sektor']].append((k['pd'] or 0, kod))
    for kod, k in kayitlar.items():
        k['akran'] = [c for _, c in sorted(by[k['sektor']], reverse=True) if c != kod][:4]
    # ekran özeti
    yuk = sum(1 for t in tablo if t['d'] and t['d'] > 0)
    dus = sum(1 for t in tablo if t['d'] and t['d'] < 0)
    tavan = sum(1 for t in tablo if t['d'] is not None and t['d'] >= 9.5)
    taban = sum(1 for t in tablo if t['d'] is not None and t['d'] <= -9.5)
    hareketli = sorted([t for t in tablo if t['hc'] >= 300 and t['d'] is not None], key=lambda z: -abs(z['d']))[:12]
    hacimli = sorted(tablo, key=lambda z: -z['hc'])[:12]
    aday = sorted([t for t in tablo if t['d'] is not None and abs(t['d']) >= 3 and t['hc'] >= 1000], key=lambda z: -(abs(z['d']) * z['hc']))
    neden = None
    if aday:
        k = aday[0]['k']
        gi = gun_ici(ft, k, son_gun)
        olay = []
        for x in KP.get(k, []):
            z = tr_gun(x['u'])
            if z.date().isoformat() == son_gun and 'evre' in (x['konu'] or ''):
                olay.append({'t': f'{z:%H:%M}', 'm': x['konu']})
        neden = {'k': k, 'ad': H[k]['ad'], 's': aday[0]['s'], 'd': aday[0]['d'], 'onceki': kayitlar[k]['c'][-2], 'hacim_mn': aday[0]['hc'], 'hr': aday[0]['hr'],
                 'neden': kayitlar[k]['neden'], 'gunici': gi, 'olay': sorted(olay, key=lambda z: z['t']), 'kap': kayitlar[k]['kap'][:3]}
    gor, son_kap = set(), []
    for kd, lst in KP.items():
        for x in lst:
            if x['id'] not in gor:
                gor.add(x['id'])
                son_kap.append({'u': x['u'], 'k': kd, 'konu': x['konu'], 'url': x.get('url')})
    son_kap = sorted(son_kap, key=lambda z: z['u'], reverse=True)[:10]
    os.makedirs(os.path.join(kok, 'borsa', 'hisse'), exist_ok=True)
    for kod, k in kayitlar.items():
        json.dump(k, open(os.path.join(kok, 'borsa', 'hisse', kod + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    ozet = {'guncelleme': datetime.datetime.now(TR).isoformat(timespec='minutes'), 'tarih': son_gun, 'n': len(tablo), 'yuk': yuk, 'dus': dus, 'tavan': tavan, 'taban': taban,
            'bist100': {'gi': gun_ici(ft, 'XU100', son_gun, 'endeks_mumlar_15dk_gh'), 'on': XU[-2][1], 'son': XU[-1][1], 'd': r(yuzde(XU[-2][1], XU[-1][1])), 'g': [x[0] for x in XU[-32:]], 'c': [x[1] for x in XU[-32:]]},
            'usd': {'g': [x[0] for x in USD[-32:]], 'c': [x[1] for x in USD[-32:]]},
            'seri': sorted(seriler, key=lambda z: -z['n'])[:6], 'kap': son_kap,
            'hareketli': hareketli, 'hacimli': hacimli, 'neden': neden, 'tablo': sorted(tablo, key=lambda z: -z['hc'])}
    json.dump(ozet, open(os.path.join(kok, 'borsa', 'ozet.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('yazıldı: hisse', len(kayitlar), 'tablo', len(tablo), 'yuk', yuk, 'dus', dus)


def canli(ft, kok):
    """Seans açıkken hafif güncelleme (borsa/canli.json): BIST 100 gün içi çizgisi, güncel fiyat ve değişim, hisse başına [son, değişim %, hacim mn TL].
    Önceki kapanışlar borsa-veri dalındaki ozet.json'dan alınır. Günlük kapanış çalışması yazılana kadar arayüz ozet.json'u bununla örter."""
    import urllib.request
    gun = datetime.datetime.now(TR).date().isoformat()
    ozet = json.load(urllib.request.urlopen('https://raw.githubusercontent.com/Endeks24/endeks24-v5/borsa-veri/borsa/ozet.json', timeout=30))
    if ozet['tarih'] >= gun:
        log('canlı: kapanış verisi zaten bugünün'); return
    xu = gun_ici(ft, 'XU100', gun, 'endeks_mumlar_15dk_gh')
    if not xu['c']:
        log('canlı: bugün endeks mumu yok'); return
    on = ozet['bist100']['son']
    b = datetime.datetime.combine(datetime.date.fromisoformat(gun) - datetime.timedelta(days=1), datetime.time(21, 0))
    e = datetime.datetime.combine(datetime.date.fromisoformat(gun), datetime.time(21, 0))
    hac = {x['kod']: (num(x['h']) or 0) for x in fg.sayfala(ft, f"SELECT kod, SUM(hacim_15_dk_gecikmeli) AS h FROM mumlar_15dk_gh WHERE zaman_utc >= TIMESTAMP '{b:%Y-%m-%d %H:%M:%S}' AND zaman_utc < TIMESTAMP '{e:%Y-%m-%d %H:%M:%S}' GROUP BY kod ORDER BY kod")}
    mz = fg.sayfala(ft, f"SELECT MAX(zaman_utc) AS z FROM mumlar_15dk_gh WHERE zaman_utc >= TIMESTAMP '{b:%Y-%m-%d %H:%M:%S}' AND zaman_utc < TIMESTAMP '{e:%Y-%m-%d %H:%M:%S}'")[0]['z']
    z0 = datetime.datetime.fromisoformat(str(mz).replace('Z', '+00:00')) - datetime.timedelta(minutes=45)
    son = {}
    for x in fg.sayfala(ft, f"SELECT kod, zaman_utc, kapanis FROM mumlar_15dk_gh WHERE zaman_utc >= TIMESTAMP '{z0:%Y-%m-%d %H:%M:%S}' AND zaman_utc < TIMESTAMP '{e:%Y-%m-%d %H:%M:%S}' ORDER BY kod, zaman_utc"):
        if num(x['kapanis']):
            son[x['kod']] = num(x['kapanis'])
    h, yuk, dus, tavan, taban = {}, 0, 0, 0, 0
    for t in ozet['tablo']:
        k = t['k']
        if k not in son or not t['s']:
            continue
        d = yuzde(t['s'], son[k])
        h[k] = [son[k], r(d), round(hac.get(k, 0) / 1e6)]
        if d is not None:
            yuk += d > 0; dus += d < 0; tavan += d >= 9.5; taban += d <= -9.5
    if len(h) < 100:
        log('canlı: hisse sayısı az', len(h)); return
    out = {'tarih': gun, 'saat': xu['t'][-1], 'guncelleme': datetime.datetime.now(TR).isoformat(timespec='minutes'),
           'bist100': {'gi': xu, 'on': on, 'son': xu['c'][-1], 'd': r(yuzde(on, xu['c'][-1]))}, 'yuk': yuk, 'dus': dus, 'tavan': tavan, 'taban': taban, 'h': h}
    os.makedirs(os.path.join(kok, 'borsa'), exist_ok=True)
    json.dump(out, open(os.path.join(kok, 'borsa', 'canli.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('canlı yazıldı:', out['saat'], 'hisse', len(h), 'BIST 100', out['bist100']['son'], out['bist100']['d'])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if '--canli' in sys.argv:
        canli(hh.baglan(), sys.argv[1])
    else:
        main(sys.argv[1])
