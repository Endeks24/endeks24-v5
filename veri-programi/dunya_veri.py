"""Endeks24 Dünya Piyasaları verisi (28.10.2026). Yapay zeka çağrısı yoktur.

Kaynak: Yahoo Finance (yfinance), günlük kapanış; yaklaşık 15 dk gecikmeli. TCMB için EVDS (anahtar EVDS_API_KEY) varsa makro blok eklenir (fonlama maliyeti ve TÜFE).
Çıktı: <kök>/dunya/ozet.json. Bir sembol çekilemezse önceki dosyadaki son sağlam değeri korur ("eski": true).
Kullanım: python3 dunya_veri.py <kök_klasör> [--onceki <ozet.json>]
"""
import datetime, json, os, sys, time

GRUPLAR = [
    ('abd', 'ABD', [('^GSPC', 'S&P 500'), ('^IXIC', 'Nasdaq'), ('^DJI', 'Dow Jones'), ('^VIX', 'VIX korku endeksi')]),
    ('avrupa', 'Avrupa', [('^GDAXI', 'DAX'), ('^FTSE', 'FTSE 100'), ('^STOXX50E', 'Euro Stoxx 50')]),
    ('asya', 'Asya', [('^N225', 'Nikkei 225')]),
    ('emtia', 'Emtia', [('BZ=F', 'Brent petrol'), ('CL=F', 'WTI petrol'), ('GC=F', 'Ons altın')]),
    ('kur', 'Kur', [('USDTRY=X', 'Dolar/TL'), ('EURTRY=X', 'Euro/TL'), ('GBPTRY=X', 'Sterlin/TL'), ('EURUSD=X', 'Euro/Dolar')]),
]
TR = datetime.timezone(datetime.timedelta(hours=3))


def cek(sembol, deneme=3):
    import yfinance as yf
    for i in range(deneme):
        try:
            h = yf.Ticker(sembol).history(period='3mo')['Close'].dropna()
            if len(h) >= 2:
                return [(d.strftime('%Y-%m-%d'), float(v)) for d, v in h.items()]
        except Exception as e:
            print('uyarı', sembol, str(e)[:80], flush=True)
        time.sleep(2 * (i + 1))
    return None


def satir(sembol, ad, seri, eski):
    if not seri:
        if eski:
            eski = dict(eski)
            eski['eski'] = True
            return eski
        return None
    son, onc = seri[-1][1], seri[-2][1]
    nd = 4 if son < 10 else 2
    return {'sembol': sembol, 'ad': ad, 'tarih': seri[-1][0], 'son': round(son, nd), 'onceki': round(onc, nd),
            'fark': round(son - onc, nd), 'yuzde': round((son / onc - 1) * 100, 2),
            'seri': [round(v, nd) for _, v in seri[-30:]], 'gunler': [d for d, _ in seri[-30:]]}


def iso(t):
    """EVDS tarihi (gg-aa-yyyy ya da yyyy-a) ISO güne çevirir."""
    p = t.split('-')
    if len(p[0]) == 4:
        return f'{p[0]}-{int(p[1]):02d}-01'
    return f'{p[2]}-{p[1]}-{p[0]}'


def politika():
    """TCMB politika faizi (1 hafta vadeli repo ihale faizi): TCMB'nin resmi 'Merkez Bankası Faiz Oranları > 1 Hafta Repo' sayfasındaki tablo.
    EVDS'de bu serinin kodu yayımlanmadığı için resmi sayfa okunur. Başarısızsa None."""
    import re, urllib.request
    u = ('https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/'
         'Merkez+Bankasi+Faiz+Oranlari/1+Hafta+Repo')
    try:
        h = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 Endeks24'}), timeout=40).read().decode('utf-8', 'ignore')
        tb = re.search(r'<table[^>]*id="midTable".*?</table>', h, re.S).group(0)
        satir = []
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            td = [re.sub(r'<[^>]+>', '', x).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(td) >= 3 and re.match(r'\d\d\.\d\d\.\d{4}$', td[0]):
                try:
                    g, a, y = td[0].split('.')
                    satir.append((f'{y}-{a}-{g}', float(td[-1])))
                except ValueError:
                    pass
        if len(satir) < 2:
            return None
        satir.sort()
        return {'ad': 'TCMB politika faizi (1 hafta vadeli repo ihale faizi)', 'son': satir[-1][1], 'tarih': satir[-1][0],
                'onceki': satir[-2][1], 'seri': satir[-12:]}
    except Exception as e:
        print('uyarı politika', str(e)[:80], flush=True)
        return None


# Merkez bankası karar günleri, resmi takvimlerden (28.10.2026'da doğrulandı): Fed (federalreserve.gov), ECB (ecb.europa.eu), BoJ (boj.or.jp), TCMB (tcmb.gov.tr).
# saat: Türkiye saati; None ise banka saati henüz açıklamadı. Kaynaktaki (borsapy) satır bu günlerden ±3 gün uzakta kalıyorsa atılır, resmi satır konur.
RESMI = {
    'Fed': {'adlar': ('Fed',), 'ulke': 'ABD', 'gunler': {'2026-10-28': '21:00'}},
    'ECB': {'adlar': ('ECB',), 'ulke': 'Euro Bölgesi', 'gunler': {'2026-10-29': '16:15', '2026-12-17': '16:15'}},
    'BoJ': {'adlar': ('BoJ',), 'ulke': 'Japonya', 'gunler': {'2026-10-30': None, '2026-12-18': None}},
    'TCMB': {'adlar': ('TCMB', 'PPK'), 'ulke': 'Türkiye', 'gunler': {'2026-12-10': None}},
}
# Resmi kaynaklarda çelişen ya da doğrulanamayan satırlar kaynaktan atılır (Eurostat Q3 öncü GSYH: takvim sayfası 29 Ekim, yayın takvimi PDF'si 30 Ekim diyor).
ATILAN = (('Euro Bölgesi', 'GSYH Büyüme Oranı', 'Öncü'),)


def resmi_duzelt(liste):
    import datetime as dt
    cikti = []
    for x in liste:
        if any(x['ulke'] == u and a in x['olay'] and b in x['olay'] for u, a, b in ATILAN):
            continue
        banka = next((k for k, v in RESMI.items() if x['olay'].split(' ')[0] in v['adlar'] and ('Faiz Kararı' in x['olay'] or 'Basın Toplantısı' in x['olay'])), None)
        if banka:
            g = dt.date.fromisoformat(x['tarih'])
            yakin = [d for d in RESMI[banka]['gunler'] if abs((dt.date.fromisoformat(d) - g).days) <= 3]
            if yakin and x['tarih'] not in yakin:
                continue
        cikti.append(x)
    bugun = datetime.datetime.now(TR).strftime('%Y-%m-%d')
    son = (datetime.datetime.now(TR) + datetime.timedelta(days=14)).strftime('%Y-%m-%d')
    for banka, v in RESMI.items():
        for d, saat in v['gunler'].items():
            if bugun <= d <= son and not any(y['tarih'] == d and y['ulke'] == v['ulke'] and 'Faiz Kararı' in y['olay'] for y in cikti):
                cikti.append({'tarih': d, 'saat': saat or 'Saat açıklanmadı', 'ulke': v['ulke'], 'olay': ('Fed' if banka == 'Fed' else banka) + ' Faiz Kararı',
                              'onceki': None, 'gerceklesen': None})
    cikti.sort(key=lambda y: (y['tarih'], '99' if y['saat'][0] == 'S' else y['saat']))
    return cikti


def takvim():
    """Önümüzdeki iki haftanın yüksek önemli olayları (borsapy ekonomik takvimi, saatler Türkiye saati). Başarısızsa None."""
    try:
        import re
        import borsapy as bp
        df = bp.economic_calendar(period='2w', country=['TR', 'US', 'EU', 'DE', 'GB', 'JP', 'CN'], importance='high')
        bugun = datetime.datetime.now(TR).strftime('%Y-%m-%d')
        gor, cikti = set(), []
        for _, r in df.iterrows():
            ad = re.sub(r'\s*\(-\)\s*$', '', re.sub(r'\s+', ' ', str(r['Event'])).strip())
            if re.search(r'Gösterge Faiz Oranı|Mevduat Faiz Oranı|Refinansman|Minimum|Maksimum|İskonto', ad):
                continue
            if str(r['Date'])[:10] < bugun:
                continue
            k = (str(r['Date'])[:10], str(r['Time']), ad)
            if k in gor:
                continue
            gor.add(k)
            def deger(x):
                x = str(x).strip()
                return None if x in ('', 'nan', 'None', '-') else x
            onc = None if 'Faiz Kararı' in ad else deger(r['Previous'])
            cikti.append({'tarih': str(r['Date'])[:10], 'saat': str(r['Time']), 'ulke': str(r['Country']), 'olay': ad,
                          'onceki': onc, 'gerceklesen': deger(r['Actual'])})
        cikti = resmi_duzelt(cikti)
        return cikti[:16] or None
    except Exception as e:
        print('uyarı takvim', str(e)[:80], flush=True)
        return None


def karsilastirma(oncul):
    """BIST 100, S&P 500 ve DAX ortak işlem günlerinde 100'e endekslenmiş seri."""
    ss = [('XU100.IS', 'BIST 100'), ('^GSPC', 'S&P 500'), ('^GDAXI', 'DAX')]
    veri = {}
    for sym, ad in ss:
        v = oncul.get(sym) or cek(sym)
        if not v:
            return None
        veri[sym] = dict(v)
    ortak = sorted(set.intersection(*[set(v) for v in veri.values()]))[-42:]
    if len(ortak) < 20:
        return None
    return {'gunler': ortak, 'seriler': [{'sembol': sym, 'ad': ad, 'deger': [round(veri[sym][g] / veri[sym][ortak[0]] * 100, 2) for g in ortak]}
                                          for sym, ad in ss]}


TANI = []   # EVDS hataları ozet.json'a 'evds_tani' olarak yazılır (GitHub günlüğü okunamadığı için)


def evds(anahtar):
    """TCMB ağırlıklı ortalama fonlama maliyeti (günlük) ve TÜFE yıllık değişim (aylık). Başarısızsa None."""
    import urllib.request
    bas = (datetime.date.today() - datetime.timedelta(days=800)).strftime('%d-%m-%Y')
    bit = datetime.date.today().strftime('%d-%m-%Y')
    # EVDS 2026'da evds3.tcmb.gov.tr/igmevdsms-dis adresine taşındı (eski evds2 adresi arayüze yönlendirir ve HTML döner); TÜFE serisi 2025=100 tabanına geçti.
    ss = [('fonlama', 'TP.APIFON4', 'TCMB ağırlıklı ortalama fonlama maliyeti'),
          ('tufe', 'TP.TUKFIY2025.GENEL', 'TÜFE (2025=100)')]
    cikti = {}
    for k, kod, ad in ss:
        try:
            u = f'https://evds3.tcmb.gov.tr/igmevdsms-dis/series={kod}&startDate={bas}&endDate={bit}&type=json'
            req = urllib.request.Request(u, headers={'key': anahtar})
            v = json.loads(urllib.request.urlopen(req, timeout=40).read())['items']
            alan = [x for x in v[-1].keys() if x not in ('Tarih', 'UNIXTIME')][0]
            nok = [(iso(x['Tarih']), float(x[alan])) for x in v if x.get(alan) not in (None, '')]
            if (datetime.date.today() - datetime.date.fromisoformat(nok[-1][0])).days > (75 if k == 'tufe' else 20):
                raise ValueError('son gözlem eski: ' + nok[-1][0])   # bırakılmış (arşiv) seri eski değerle gösterilmesin
            cikti[k] = {'ad': ad, 'kod': kod, 'son': nok[-1][1], 'tarih': nok[-1][0], 'seri': nok[-24:]}
        except Exception as e:
            TANI.append(f'{kod}: {str(e)[:120]}')
            print('uyarı evds', kod, str(e)[:80], flush=True)
    if 'tufe' in cikti and len(cikti['tufe']['seri']) >= 13:
        s = cikti['tufe']['seri']
        cikti['tufe']['yillik'] = round((s[-1][1] / s[-13][1] - 1) * 100, 2)
        cikti['tufe']['aylik'] = round((s[-1][1] / s[-2][1] - 1) * 100, 2)
    return cikti or None


def main():
    kok = sys.argv[1]
    onceki = {}
    if '--onceki' in sys.argv:
        try:
            onceki = json.load(open(sys.argv[sys.argv.index('--onceki') + 1]))
        except Exception:
            pass
    eskisi = {x['sembol']: x for g in onceki.get('gruplar', []) for x in g['satirlar']}
    gruplar, yok, oncul = [], 0, {}
    for kod, ad, liste in GRUPLAR:
        s = []
        for sym, sad in liste:
            oncul[sym] = cek(sym)
            r = satir(sym, sad, oncul[sym], eskisi.get(sym))
            if r is None:
                yok += 1
                print('YOK', sym, flush=True)
            else:
                s.append(r)
        gruplar.append({'kod': kod, 'ad': ad, 'satirlar': s})
    makro = None
    if os.environ.get('EVDS_API_KEY'):
        makro = evds(os.environ['EVDS_API_KEY'])
    else:
        TANI.append('EVDS_API_KEY tanımlı değil')
    pf = politika()
    if pf or makro:
        makro = dict(makro or {})
        if pf:
            makro['politika'] = pf
    ob = onceki.get('tcmb') or {}
    for k in ('politika', 'fonlama', 'tufe'):
        if not (makro or {}).get(k) and ob.get(k):
            makro = dict(makro or {})
            makro[k] = ob[k]
    kars = karsilastirma(oncul) or onceki.get('karsilastirma')
    tkv = takvim() or onceki.get('takvim')
    toplam = sum(len(g['satirlar']) for g in gruplar)
    if toplam < 8:
        print('çok az veri, dosya yazılmadı', flush=True)
        sys.exit(1)
    os.makedirs(f'{kok}/dunya', exist_ok=True)
    ozet = {'olusturma': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M:%S+03:00'),
            'kaynak': 'Yahoo Finance (günlük kapanış, gecikmeli)', 'gruplar': gruplar, 'tcmb': makro, 'takvim': tkv, 'karsilastirma': kars, 'evds_tani': TANI or None}
    json.dump(ozet, open(f'{kok}/dunya/ozet.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    print('TAMAM', toplam, 'satır,', yok, 'eksik', flush=True)


if __name__ == '__main__':
    main()
