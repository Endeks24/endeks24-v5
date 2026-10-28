"""Endeks24 Temettü Takvimi verisi (28.10.2026). Yapay zeka çağrısı yoktur; Fintables doküman havuzundan KAP "Kar Payı Dağıtım İşlemlerine İlişkin Bildirim" metinleri okunur.

Her bildirimden nakit kâr payı tutarı (1 TL nominal paya brüt/net), hak kullanım, kayıt ve ödeme tarihleri ve durum (yönetim kurulu önerisi, genel kurulca onaylanan,
kesinleşen) ayrıştırılır. Aynı hisse için en son yayımlanan bildirim geçerlidir; son bildirim kâr dağıtılmayacağını söylüyorsa hisse listeden çıkar.
Çıktı: <kök>/temettu/ozet.json. Kullanım: python3 temettu_veri.py <kök_klasör> <borsa_ozet.json> [--gun 120]. Anahtar FINTABLES ortam değişkeninde.
"""
import datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TR = datetime.timezone(datetime.timedelta(hours=3))
KONU = 'Kar Payı Dağıtım İşlemlerine İlişkin Bildirim'


def log(*a):
    print(*a, flush=True)


def sayi(s):
    s = (s or '').strip()
    if not s or s == '-':
        return None
    try:
        return float(s.replace('.', '').replace(',', '.')) if ',' in s else float(s)
    except ValueError:
        return None


def tarih(s):
    m = re.fullmatch(r'\s*(\d{2})\.(\d{2})\.(\d{4})\s*', s or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else None


def tablolar(metin):
    """Markdown tablolarını [satırlar(hücre listesi)] olarak döndürür; başlık satırı ilk satırdır."""
    out, cur = [], []
    for ln in metin.split('\n'):
        if ln.startswith('|'):
            if re.fullmatch(r'\|[\s\-|:]+\|?', ln):
                continue
            cur.append([c.strip() for c in ln.strip().strip('|').split('|')])
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def hisse_kodu(hucre):
    """'A Grubu, FROTO, TRAOTOSN91H6' -> 'FROTO'; işlem görmeyen sınıf -> None."""
    for p in [x.strip() for x in hucre.split(',')]:
        if re.fullmatch(r'[A-ZÇĞİÖŞÜ0-9]{3,6}', p) and not p.startswith('TR'):
            return p
    return None


def ayristir(metin, bildirim_tarihi=None):
    """Bildirim metninden {'durum', 'kalemler': [{'k','odeme','brut','net','stopaj','hak','kayit','odeme_tarihi'}], 'genel_kurul'} üretir; nakit dağıtım yoksa kalemler boştur."""
    satirlar = [x for x in metin.split('\n') if x.strip()]
    baslik = satirlar[1].strip() if len(satirlar) > 1 else ''
    durum = 'oneri'
    if re.search(r'Genel Kurulca Onaylan|Kesinleşen|Onaylanması|Onaylandı', baslik + ' ' + (satirlar[2] if len(satirlar) > 2 else ''), re.I):
        durum = 'onayli'
    gk = None
    for t in tablolar(metin):
        for r in t:
            if len(r) >= 2 and r[0].startswith('Konunun Gündemde Yer Aldığı Genel Kurul Tarihi'):
                gk = tarih(r[1])
    nakit, tarihler = [], {}
    for t in tablolar(metin):
        baslik_satiri = ' '.join(t[0])
        if 'Brüt(TL)' in baslik_satiri and 'Pay Grup Bilgileri' in baslik_satiri:
            for r in t[1:]:
                k = hisse_kodu(r[0])
                if k and len(r) >= 6:
                    nakit.append({'k': k, 'odeme': r[1], 'brut': sayi(r[2]), 'stopaj': sayi(r[4]), 'net': sayi(r[5])})
        elif 'Hak Kullanım Tarihi' in baslik_satiri and 'Ödeme Tarihi' in baslik_satiri:
            for r in t[1:]:
                if len(r) >= 5:
                    tarihler[r[0]] = {'teklif': tarih(r[1]), 'kesin': tarih(r[2]), 'odeme': tarih(r[3]), 'kayit': tarih(r[4])}
    kalemler = []
    for n in nakit:
        d = tarihler.get(n['odeme'], {})
        hak = d.get('kesin') or d.get('teklif')
        kalemler.append({**n, 'hak': hak, 'kesin': bool(d.get('kesin')), 'kayit': d.get('kayit'), 'odeme_tarihi': d.get('odeme')})
    if durum == 'onayli' or any(k['kesin'] for k in kalemler):
        durum = 'onayli'
    kalemler = [k for k in kalemler if k['brut']]
    # Taksitli ödemelerde tabloda ayrıca "toplam" satırı bulunabilir (diğer satırların toplamı); ayrı kayıt sayılmaz.
    for k in list(kalemler):
        digerleri = [x for x in kalemler if x is not k and x['k'] == k['k']]
        if len(digerleri) >= 2 and abs(sum(x['brut'] for x in digerleri) - k['brut']) <= 0.01 * k['brut']:
            kalemler.remove(k)
    return {'durum': durum, 'kalemler': kalemler, 'genel_kurul': gk, 'baslik': baslik}


def ara(ft, bas, bit):
    """[bas, bit) aralığındaki bildirimlerin ilk parçalarını {kap_id: sonuç} olarak toplar."""
    sonuc = {}
    f = (f'dokuman_tipi = "kap_haberi" AND kap_bildirim_tipi = "CA" AND kap_bildirim_konu = "{KONU}" '
         f'AND yayinlanma_tarihi_utc >= "{bas.strftime("%Y-%m-%dT%H:%M:%SZ")}" AND yayinlanma_tarihi_utc < "{bit.strftime("%Y-%m-%dT%H:%M:%SZ")}"')
    s = 1
    while True:
        r = ft.arac('dokumanlarda_ara', {'query': '', 'filter': f, 'sayfa': s, 'sayfa_basi': 50, 'sirala': 'yayinlanma_tarihi_utc:asc'})
        for x in r.get('sonuclar', []):
            k = x['kap_bildirim_id']
            if k not in sonuc or x.get('sayfa_no', 1) < sonuc[k].get('sayfa_no', 99):
                sonuc[k] = x
        if s >= r.get('toplam_sayfa', 1):
            return sonuc
        s += 1


def main(kok, ozet_yol, gun):
    import hafiza_hesapla as hh
    ft = hh.baglan()
    oz = json.load(open(ozet_yol))
    fiyat = {t['k']: t['s'] for t in oz['tablo']}
    bit = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    bas = bit - datetime.timedelta(days=gun)
    adaylar = {}
    t = bas
    while t < bit:
        u = min(t + datetime.timedelta(days=20), bit)
        adaylar.update(ara(ft, t, u))
        t = u
    log('bildirim', len(adaylar))
    icerik = hh.icerikler(ft, [x['id'] for x in adaylar.values()])
    son = {}   # hisse -> (yayın zamanı, bildirim, sonuç)
    for k, x in adaylar.items():
        m = icerik.get(str(x['id']))
        if not m:
            continue
        try:
            a = ayristir(m)
        except Exception as e:
            log('  ayrıştırılamadı', k, str(e)[:60])
            continue
        kodlar = [s for s in (x.get('iliskili_semboller') or []) if s in fiyat] or list({y['k'] for y in a['kalemler']})
        for h in kodlar:
            z = x['yayinlanma_tarihi_utc']
            if h not in son or z > son[h][0]:
                son[h] = (z, x, a)
    bugun = datetime.datetime.now(TR).strftime('%Y-%m-%d')
    liste = []
    for h, (z, x, a) in son.items():
        for kal in a['kalemler']:
            if kal['k'] != h or h not in fiyat:
                continue
            f = fiyat[h]
            liste.append({'k': h, 'brut': kal['brut'], 'net': kal['net'], 'stopaj': kal['stopaj'], 'odeme': kal['odeme'], 'hak': kal['hak'], 'kayit': kal['kayit'], 'odeme_tarihi': kal['odeme_tarihi'],
                          'durum': a['durum'], 'genel_kurul': a['genel_kurul'], 'fiyat': f, 'verim': round(kal['brut'] / f * 100, 2) if f else None,
                          'yayin': z[:10], 'url': x.get('dokuman_orijinal_url')})
    liste.sort(key=lambda r: (r['hak'] or '9999', r['k']))
    os.makedirs(f'{kok}/temettu', exist_ok=True)
    cikti = {'olusturma': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M:%S+03:00'), 'fiyat_tarihi': oz.get('tarih'), 'bugun': bugun, 'kayit': liste}
    json.dump(cikti, open(f'{kok}/temettu/ozet.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('TAMAM', len(liste), 'kayıt')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    g = int(sys.argv[sys.argv.index('--gun') + 1]) if '--gun' in sys.argv else 120
    main(sys.argv[1], sys.argv[2], g)
