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


def evds(anahtar):
    """TCMB ağırlıklı ortalama fonlama maliyeti (günlük) ve TÜFE yıllık değişim (aylık). Başarısızsa None."""
    import urllib.request
    bas = (datetime.date.today() - datetime.timedelta(days=800)).strftime('%d-%m-%Y')
    bit = datetime.date.today().strftime('%d-%m-%Y')
    ss = [('fonlama', 'TP.APIFON4', 'TCMB ağırlıklı ortalama fonlama maliyeti'),
          ('tufe', 'TP.FG.J0', 'TÜFE (2003=100)')]
    cikti = {}
    for k, kod, ad in ss:
        try:
            u = f'https://evds2.tcmb.gov.tr/service/evds/series={kod}&startDate={bas}&endDate={bit}&type=json'
            req = urllib.request.Request(u, headers={'key': anahtar})
            v = json.loads(urllib.request.urlopen(req, timeout=40).read())['items']
            alan = [x for x in v[-1].keys() if x not in ('Tarih', 'UNIXTIME')][0]
            nok = [(iso(x['Tarih']), float(x[alan])) for x in v if x.get(alan) not in (None, '')]
            cikti[k] = {'ad': ad, 'kod': kod, 'son': nok[-1][1], 'tarih': nok[-1][0], 'seri': nok[-24:]}
        except Exception as e:
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
    gruplar, yok = [], 0
    for kod, ad, liste in GRUPLAR:
        s = []
        for sym, sad in liste:
            r = satir(sym, sad, cek(sym), eskisi.get(sym))
            if r is None:
                yok += 1
                print('YOK', sym, flush=True)
            else:
                s.append(r)
        gruplar.append({'kod': kod, 'ad': ad, 'satirlar': s})
    makro = None
    if os.environ.get('EVDS_API_KEY'):
        makro = evds(os.environ['EVDS_API_KEY']) or onceki.get('tcmb')
    toplam = sum(len(g['satirlar']) for g in gruplar)
    if toplam < 8:
        print('çok az veri, dosya yazılmadı', flush=True)
        sys.exit(1)
    os.makedirs(f'{kok}/dunya', exist_ok=True)
    ozet = {'olusturma': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M:%S+03:00'),
            'kaynak': 'Yahoo Finance (günlük kapanış, gecikmeli)', 'gruplar': gruplar, 'tcmb': makro}
    json.dump(ozet, open(f'{kok}/dunya/ozet.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    print('TAMAM', toplam, 'satır,', yok, 'eksik', flush=True)


if __name__ == '__main__':
    main()
