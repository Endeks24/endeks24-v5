"""Endeks24 fiyat hafızası (Halit Bey onayı 24.10.2026).
KAP kararlarından (bedelsiz, temettü, bedelli) sonra hisselerin 5 işlem gününde ne yaptığını BIST 100'e göre hesaplar.
Fintables MCP'den (salt okuma) KAP bildirimlerini ve günlük mumları okur; hafiza.json ve hafiza-olaylar.json yazar.
Anahtar FINTABLES ortam değişkeninde (GitHub secret). Yapay zeka çağrısı yoktur; aylık Actions çalışması yeter.
Kullanım: python3 hafiza_hesapla.py <cikti_klasoru> [--dene] [--pencere-ay 36]
"""
import base64, collections, datetime, json, os, re, statistics, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fintables_veri as fv

TR = datetime.timezone(datetime.timedelta(hours=3))
KONULAR = ['Sermaye Artırımı - Azaltımı İşlemlerine İlişkin Bildirim', 'Kar Payı Dağıtım İşlemlerine İlişkin Bildirim']
GUN = 5          # olaydan sonraki işlem günü sayısı (olay günü dahil)
ENDEKS = 'XU100'
EN_AZ_TUM = 10   # sitede kutu için asgari olay sayısı (hafiza.json'a yazılır, site uygular)
SEANS_KAPANIS = 18 * 60  # 18.00: bundan sonraki yayın ertesi seansa sayılır


def log(*a):
    print(*a, flush=True)


class FT(fv.Fintables):
    """Fintables istemcisi; 429 ve geçici hatalarda bekleyip yeniden dener, araç çağrısını ayrıştırır."""

    bekleme = 0

    def _gonder(self, govde):
        for deneme in range(7):
            try:
                t, h = fv.istek(fv.MCP, json.dumps(govde).encode(), self.b, zaman=90)
                sid = h.get('Mcp-Session-Id') or h.get('mcp-session-id')
                if sid:
                    self.b['Mcp-Session-Id'] = sid
                return t
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    fv.hata('Fintables anahtarı geçersiz ya da süresi dolmuş (401).')
                govde_e = e.read()[:300]
                if e.code == 429 and b'Saatlik' in govde_e and self.bekleme < 30:
                    self.bekleme += 1
                    log(f'  saatlik sınır; 10 dk bekleniyor ({self.bekleme}/30)'); time.sleep(600); continue
                if e.code in (429, 500, 502, 503, 504) and deneme < 6:
                    time.sleep(min(60, 3 * 2 ** deneme)); continue
                fv.hata(f'Fintables HTTP {e.code}: {govde_e!r}')
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if deneme < 6:
                    time.sleep(min(60, 3 * 2 ** deneme)); continue
                raise

    def arac(self, isim, args):
        args = dict(args, purpose='Endeks24 fiyat hafızası hesabı')
        r = self.rpc('tools/call', {'name': isim, 'arguments': args})
        metin = ''.join(c.get('text', '') for c in r.get('content', []) if c.get('type') == 'text')
        if r.get('isError'):
            raise RuntimeError(isim + ': ' + metin[:300])
        return json.loads(metin)

    def sql(self, q):
        try:
            return self.sorgu(q)
        except SystemExit:
            raise


def baglan():
    paket = os.environ.get('FINTABLES', '').strip()
    if not paket:
        fv.hata('FINTABLES anahtarı tanımlı değil.')
    try:
        p = json.loads(base64.b64decode(paket))
    except Exception:
        fv.hata('FINTABLES anahtarı bozuk.')
    if p.get('bitis') and p['bitis'] / 1000 < time.time():
        fv.hata('Fintables anahtarının süresi doldu; eski hafiza.json korunur.')
    return FT(p['a'])


# ---------- KAP olayları ----------
def tarih_utc(d):
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')


def ara_pencere(ft, konu, bas, bit, sonuc, derinlik=0):
    """[bas, bit) aralığındaki KAP bildirimlerini toplar; 1000 sınırına dayanırsa aralığı böler."""
    filtre = (f'dokuman_tipi = "kap_haberi" AND kap_bildirim_tipi = "CA" AND kap_bildirim_konu = "{konu}" '
              f'AND yayinlanma_tarihi_utc >= "{tarih_utc(bas)}" AND yayinlanma_tarihi_utc < "{tarih_utc(bit)}"')
    r = ft.arac('dokumanlarda_ara', {'query': '', 'filter': filtre, 'sayfa': 1, 'sayfa_basi': 50,
                                     'sirala': 'yayinlanma_tarihi_utc:asc'})
    top = r.get('toplam', 0)
    if top >= 1000 and (bit - bas) > datetime.timedelta(hours=2):
        orta = bas + (bit - bas) / 2
        ara_pencere(ft, konu, bas, orta, sonuc, derinlik + 1)
        ara_pencere(ft, konu, orta, bit, sonuc, derinlik + 1)
        return
    sayfalar = r.get('toplam_sayfa', 1)
    for s in range(1, sayfalar + 1):
        if s > 1:
            r = ft.arac('dokumanlarda_ara', {'query': '', 'filter': filtre, 'sayfa': s, 'sayfa_basi': 50,
                                             'sirala': 'yayinlanma_tarihi_utc:asc'})
        for x in r.get('sonuclar', []):
            sonuc[x['kap_bildirim_id']] = x


def kap_adaylari(ft, bas, bit, adim_gun=14):
    sonuc = {}
    for konu in KONULAR:
        t = bas
        while t < bit:
            u = min(t + datetime.timedelta(days=adim_gun), bit)
            ara_pencere(ft, konu, t, u, sonuc)
            t = u
        log(' ', konu, '->', len(sonuc), 'toplam aday')
    return sonuc


def icerikler(ft, idler):
    """Parça kimliklerinden metinleri çeker (20'şer)."""
    out = {}
    idler = list(idler)
    for i in range(0, len(idler), 20):
        grup = idler[i:i + 20]
        r = ft.arac('dokuman_chunk_yukle', {'ids': grup})
        for c in r:
            out[str(c['id'])] = c.get('content', '')
        if (i // 20) % 25 == 0:
            log('  metin', i, '/', len(idler))
    return out


def sayilar(hucreler):
    out = []
    for c in hucreler:
        c = c.strip()
        if re.fullmatch(r'\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?', c):
            out.append(float(c.replace('.', '').replace(',', '.')))
    return out


def nakit_tutar(satirlar):
    """'Nakit Kar Payı Ödeme Tutar ve Oranları' tablosundaki en büyük sayı; tablo yoksa 0."""
    for i, s in enumerate(satirlar):
        if s.startswith('Nakit Kar Payı Ödeme Tutar ve Oran'):
            en = 0.0
            for t in satirlar[i + 1:i + 12]:
                if not t.startswith('|'):
                    if en or t.startswith('Kar Payı Ödeme Tarihleri'):
                        break
                    continue
                en = max([en] + sayilar(t.strip('|').split('|')))
            return en
    return 0.0


def sinifla(metin):
    """(tur, altbaslik, guncelleme, duzeltme). Tür, alt başlığa değil bildirimin yapısına göre belirlenir (şirketler başlığı serbest yazıyor).
    Yalnız saf türler sayılır: bedelsiz (bedelli ya da tahsisli bölümü yok), bedelli (bedelsiz ya da tahsisli bölümü yok), temettü (nakit tutarı > 0)."""
    satirlar = [s.strip() for s in metin.split('\n') if s.strip()]
    ust = satirlar[0].lstrip('# ').strip() if satirlar else ''
    alt = satirlar[1] if len(satirlar) > 1 else ''
    g = re.search(r'Güncelleme mi \?\s*\|\s*(Evet|Hayır)', metin)
    d = re.search(r'Düzeltme mi \?\s*\|\s*(Evet|Hayır)', metin)
    guncel = (g.group(1) if g else '?'); duz = (d.group(1) if d else '?')
    yapi = [s for s in satirlar if s.startswith('|') or len(s) < 70]
    var = lambda k: any(k in s for s in yapi)
    tur = None
    if ust.startswith('Sermaye Artırımı') and var('Yönetim Kurulu Karar Tarihi'):
        bedelsiz, bedelli, tahsisli = var('Bedelsiz Pay Alma Oranı'), var('Rüçhan') or var('Bedelli Sermaye Artırımı'), var('Tahsisli')
        if bedelsiz and not bedelli and not tahsisli:
            tur = 'bedelsiz'
        elif bedelli and not bedelsiz and not tahsisli:
            tur = 'bedelli'
    elif ust.startswith('Kar Payı Dağıtım') and var('| Karar Tarihi') and nakit_tutar(satirlar) > 0:
        tur = 'temettu'
    return tur, alt, guncel, duz


# ---------- fiyatlar ----------
def gunluk(ft, tablo, kod, bas_tarih):
    """{tarih: kapanis} döner, tarih Europe/Istanbul gününe çevrilir."""
    out, off, sayfa = {}, 0, 1000
    while True:
        sat = ft.sql(f"SELECT zaman_utc, kapanis FROM {tablo} WHERE kod = '{kod}' AND zaman_utc >= TIMESTAMP '{bas_tarih} 00:00:00' "
                     f"ORDER BY zaman_utc LIMIT {sayfa} OFFSET {off}")
        if not sat:
            break
        for r in sat:
            t = datetime.datetime.fromisoformat(r['zaman_utc'].replace('Z', '+00:00')).astimezone(TR).date()
            out[t] = float(r['kapanis'])
        off += len(sat)
        if len(sat) < 50:
            break
    return out


def tepki(pub_tr, seri, endeks):
    """Olay sonrası GUN işlem günü getiri ve endekse göre fazla getiri; hesaplanamazsa None."""
    gunler = sorted(seri)
    dak = pub_tr.hour * 60 + pub_tr.minute
    t0 = None
    for g in gunler:
        if g > pub_tr.date() or (g == pub_tr.date() and dak < SEANS_KAPANIS):
            t0 = g; break
    if t0 is None:
        return None
    i = gunler.index(t0)
    if i == 0 or i + GUN - 1 >= len(gunler):
        return None
    baz, son = gunler[i - 1], gunler[i + GUN - 1]
    if baz not in endeks or son not in endeks or not seri[baz] or not endeks[baz]:
        return None
    if (son - baz).days > 14 + GUN * 2:  # uzun işlem durması
        return None
    r = seri[son] / seri[baz] - 1
    e = endeks[son] / endeks[baz] - 1
    return round(r * 100, 2), round((r - e) * 100, 2), t0


def ozet(vals):
    if not vals:
        return None
    ret = [v[0] for v in vals]; fz = [v[1] for v in vals]
    return {'n': len(vals), 'medyan': round(statistics.median(ret), 1), 'fazla_medyan': round(statistics.median(fz), 1),
            'pozitif': round(100 * sum(1 for x in ret if x > 0) / len(ret)),
            'fazla_pozitif': round(100 * sum(1 for x in fz if x > 0) / len(fz))}


def main():
    cikti = sys.argv[1] if len(sys.argv) > 1 else '.'
    dene = '--dene' in sys.argv
    ay = 36
    if '--pencere-ay' in sys.argv:
        ay = int(sys.argv[sys.argv.index('--pencere-ay') + 1])
    simdi = datetime.datetime.now(datetime.timezone.utc)
    bas = (simdi - datetime.timedelta(days=30.4 * ay)).replace(hour=0, minute=0, second=0, microsecond=0)
    ft = baglan()
    onbellek_yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hafiza-olay-onbellek.json')
    onbellek = {'tarama_bitis': None, 'olaylar': []}
    if os.path.exists(onbellek_yol) and '--onbellek-yok' not in sys.argv:
        onbellek = json.load(open(onbellek_yol, encoding='utf-8'))
        if onbellek.get('tarama_bitis'):
            bas_yeni = datetime.datetime.fromisoformat(onbellek['tarama_bitis']) - datetime.timedelta(days=10)
            bas = max(bas, bas_yeni)
    log('KAP adayları', bas.date(), '->', simdi.date(), '| önbellekte olay:', len(onbellek['olaylar']))
    ad = kap_adaylari(ft, bas, simdi)
    # yalnız ilk parçası ve tek şirketli bildirimler
    adaylar = {k: x for k, x in ad.items() if x.get('sayfa_no') == 1 and len(x.get('iliskili_semboller') or []) == 1}
    log('aday bildirim', len(adaylar))
    metin = icerikler(ft, [x['id'] for x in adaylar.values()])
    sayac = collections.Counter(); olaylar = []
    for k, x in adaylar.items():
        m = metin.get(str(x['id']), '')
        tur, alt, g, d = sinifla(m)
        sayac[(x['kap_bildirim_konu'][:12], alt[:60], g, d, tur)] += 1
        if tur and g == 'Hayır' and d == 'Hayır':
            pub = datetime.datetime.fromisoformat(x['yayinlanma_tarihi_utc']).astimezone(TR)
            olaylar.append({'hisse': x['iliskili_semboller'][0], 'tur': tur, 'pub': pub, 'kap': k})
    if '--imza' in sys.argv:
        isaret = ['Yönetim Kurulu Karar Tarihi', '| Karar Tarihi', 'Toplam Bedelsiz Pay Alma Oranı', 'Bedelli Sermaye Artırımı', 'Rüçhan', 'Tahsisli',
                  'Nakit Kar Payı Ödeme Tutar ve Oranları', 'Pay Olarak Kar Payı', 'Genel Kurul', 'SPK', 'Tescil', 'Görüşüldü', 'Dağıtılmayacak', 'Dağıtım Yapılmayacak']
        imza = collections.defaultdict(list)
        for k, x in adaylar.items():
            m = metin.get(str(x['id']), '')
            g = re.search(r'Güncelleme mi \?\s*\|\s*(Evet|Hayır)', m)
            if not g or g.group(1) != 'Hayır':
                continue
            imza[(x['kap_bildirim_konu'][:4], tuple(i[:14] for i in isaret if i in m))].append(k)
        log('--- imzalar (Güncelleme=Hayır) ---')
        for a, v in sorted(imza.items(), key=lambda t: -len(t[1]))[:30]:
            log(len(v), a, v[:3])
    if '--tani' in sys.argv:
        tani = collections.defaultdict(list)
        for k, x in adaylar.items():
            m = metin.get(str(x['id']), '')
            tur, alt, g, d = sinifla(m)
            if tur or g != 'Hayır' or d != 'Hayır':
                continue
            sat = [z.strip() for z in m.split('\n') if z.strip()]
            yapi = [z for z in sat if z.startswith('|') or len(z) < 70]
            v = lambda q: any(q in z for z in yapi)
            sa = x['kap_bildirim_konu'].startswith('Sermaye')
            anah = ('SA' if sa else 'KP', 'bedelsiz' if v('Bedelsiz Pay Alma Oranı') else '-', 'bedelli' if (v('Rüçhan') or v('Bedelli Sermaye Artırımı')) else '-',
                    'tahsisli' if v('Tahsisli') else '-', 'YKtar' if v('Yönetim Kurulu Karar Tarihi') else '-', 'Ktar' if v('| Karar Tarihi') else '-',
                    'nakit>0' if nakit_tutar(sat) > 0 else '-', 'GKtar' if v('Genel Kurul') else '-')
            tani[anah].append(k)
        log('--- TANI: sınıflanmayan Güncelleme=Hayır bildirimler ---')
        for a, v in sorted(tani.items(), key=lambda t: -len(t[1]))[:25]:
            log(len(v), a, v[:3])
    log('--- sınıflandırma dağılımı (en sık 40) ---')
    for k, n in sayac.most_common(40):
        log(n, k)
    # önbellekteki eski olaylarla birleştir (kap numarasına göre), pencere dışına çıkanları at
    eski = {o['kap']: dict(o, pub=datetime.datetime.fromisoformat(o['pub'])) for o in onbellek['olaylar']}
    for o in olaylar:
        eski[o['kap']] = o
    pencere_bas = (simdi - datetime.timedelta(days=30.4 * ay)).astimezone(TR)
    olaylar = [o for o in eski.values() if o['pub'] >= pencere_bas]
    os.makedirs(cikti, exist_ok=True)
    json.dump({'tarama_bitis': simdi.isoformat(), 'olaylar': [dict(o, pub=o['pub'].isoformat()) for o in sorted(olaylar, key=lambda o: o['pub'])]},
              open(os.path.join(cikti, 'hafiza-olay-onbellek.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    # aynı hisse ve türde 60 gün içindeki tekrarlar: yalnız ilk
    olaylar.sort(key=lambda o: o['pub'])
    son = {}; temiz = []
    for o in olaylar:
        a = (o['hisse'], o['tur'])
        if a in son and (o['pub'] - son[a]).days < 60:
            continue
        son[a] = o['pub']; temiz.append(o)
    log('olay', len(temiz), dict(collections.Counter(o['tur'] for o in temiz)))
    bist100 = {r['hisse_senedi_kodu'] for r in ft.sql("SELECT hisse_senedi_kodu FROM hisse_senetleri WHERE 'XU100' = ANY(endeksler) LIMIT 300")}
    bas_t = (pencere_bas - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
    endeks = gunluk(ft, 'endeks_mumlar_gunluk_gh', ENDEKS, bas_t)
    log('endeks gün', len(endeks))
    sonuc = []
    parti = 12
    for i in range(0, len(temiz), parti):
        grup = temiz[i:i + parti]
        kosul = ' OR '.join(
            f"(kod = '{o['hisse']}' AND zaman_utc >= TIMESTAMP '{(o['pub'] - datetime.timedelta(days=9)).strftime('%Y-%m-%d')} 00:00:00' "
            f"AND zaman_utc < TIMESTAMP '{(o['pub'] + datetime.timedelta(days=17)).strftime('%Y-%m-%d')} 00:00:00')" for o in grup)
        seriler = collections.defaultdict(dict); off = 0
        while True:
            sat = ft.sql(f"SELECT zaman_utc, kod, kapanis FROM mumlar_gunluk_gh WHERE {kosul} ORDER BY kod, zaman_utc LIMIT 300 OFFSET {off}")
            if not sat:
                break
            for r in sat:
                t = datetime.datetime.fromisoformat(r['zaman_utc'].replace('Z', '+00:00')).astimezone(TR).date()
                seriler[r['kod']][t] = float(r['kapanis'])
            off += len(sat)
            if len(sat) < 50:
                break
        for o in grup:
            t = tepki(o['pub'], seriler.get(o['hisse']) or {}, endeks)
            if t:
                sonuc.append({'hisse': o['hisse'], 'tur': o['tur'], 'tarih': t[2].isoformat(), 'kap': o['kap'],
                              'getiri': t[0], 'fazla': t[1], 'bist100': o['hisse'] in bist100})
        if (i // parti) % 10 == 0:
            log('  fiyat', i, '/', len(temiz))
    log('hesaplanan olay', len(sonuc), '/', len(temiz))
    tur_ad = {'bedelsiz': 'bedelsiz sermaye artırımı kararı', 'temettu': 'temettü (kar payı dağıtım) kararı',
              'bedelli': 'bedelli sermaye artırımı kararı'}
    cik = {'olusturma': simdi.astimezone(TR).isoformat(timespec='seconds'), 'gun': GUN, 'endeks': ENDEKS,
           'pencere': [bas.astimezone(TR).date().isoformat(), simdi.astimezone(TR).date().isoformat()], 'en_az': EN_AZ_TUM, 'bist100': sorted(bist100), 'tur': {}}
    for tur in tur_ad:
        ol = [s for s in sonuc if s['tur'] == tur]
        hisse = {}
        for h in sorted({s['hisse'] for s in ol}):
            oz = ozet([(s['getiri'], s['fazla']) for s in ol if s['hisse'] == h])
            if oz and oz['n'] >= 2:
                hisse[h] = oz
        cik['tur'][tur] = {'etiket': tur_ad[tur], 'tum': ozet([(s['getiri'], s['fazla']) for s in ol]),
                           'bist100': ozet([(s['getiri'], s['fazla']) for s in ol if s['bist100']]), 'hisse': hisse}
    os.makedirs(cikti, exist_ok=True)
    json.dump(cik, open(os.path.join(cikti, 'hafiza.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump(sorted(sonuc, key=lambda s: (s['tur'], s['tarih'])), open(os.path.join(cikti, 'hafiza-olaylar.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    for tur, v in cik['tur'].items():
        log(tur, 'tum', v['tum'], 'bist100', v['bist100'], 'hisse', len(v['hisse']))


if __name__ == '__main__':
    main()
