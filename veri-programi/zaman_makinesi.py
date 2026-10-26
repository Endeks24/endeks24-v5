"""Endeks24 Zaman makinesi veri üreticisi (26.10.2026). Salt okuma; yapay zeka çağrısı yoktur.
Kullanım: python3 zaman_makinesi.py tani <kök>   EVDS'te mevduat faizi serisini bulur (günlüğe yazar)
          python3 zaman_makinesi.py uret <kök>   <kök>/zaman-makinesi/seri.json yazar
Anahtarlar: FINTABLES (Fintables MCP), EVDS_API_KEY (TCMB EVDS)."""
import bisect, datetime, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiyat_gecmisi as fg
import hafiza_hesapla as hh

EVDS = 'https://evds3.tcmb.gov.tr/igmevdsms-dis/'


def log(*a):
    print(*a, flush=True)


def evds_al(yol):
    anahtar = os.environ.get('EVDS_API_KEY', '').strip()
    req = urllib.request.Request(EVDS + yol, headers={'key': anahtar, 'User-Agent': 'Endeks24-zaman/1', 'Accept': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace'))


def tani():
    for kat in evds_al('categories/type=json'):
        ad = kat.get('TOPIC_TITLE_TR', '')
        if not any(k in ad.upper() for k in ('FAİZ', 'MEVDUAT', 'PARA')):
            continue
        log('kategori', kat.get('CATEGORY_ID'), ad)
        try:
            gruplar = evds_al(f"datagroups/mode=2&code={int(float(kat['CATEGORY_ID']))}&type=json")
        except Exception as e:
            log('  grup listesi alınamadı', str(e)[:80]); continue
        for g in gruplar:
            gad = g.get('DATAGROUP_NAME', '')
            if 'MEVDUAT' in gad.upper():
                log('  grup', g.get('DATAGROUP_CODE'), gad, g.get('START_DATE'), g.get('END_DATE'), g.get('FREQUENCY_STR'))
                try:
                    for x in evds_al(f"serieList/type=json&code={g['DATAGROUP_CODE']}")[:12]:
                        log('     seri', x.get('SERIE_CODE'), x.get('SERIE_NAME'), x.get('START_DATE'), x.get('END_DATE'), x.get('FREQUENCY_STR'))
                except Exception as e:
                    log('     seri listesi alınamadı', str(e)[:80])


BAS = '2010-01-01'


def gunluk(ft, tablo, kod):
    """{tarih: kapanış}; OFFSET sınırı için yıl yıl okunur."""
    out = {}
    for y in range(int(BAS[:4]), datetime.date.today().year + 1):
        sat = fg.sayfala(ft, f"SELECT zaman_utc, kapanis FROM {tablo} WHERE kod = '{kod}' AND zaman_utc >= TIMESTAMP '{y - 1}-12-31 12:00:00' AND zaman_utc < TIMESTAMP '{y}-12-31 12:00:00' ORDER BY zaman_utc")
        for x in sat:
            if x.get('kapanis') is not None:
                out[fg.gun(x['zaman_utc'])] = float(x['kapanis'])
    return out


def evds_seri(kod, bas='01-01-2010'):
    """[(tarih ISO, değer)] EVDS serisi (iki adres denenir)."""
    alan = kod.replace('.', '_')
    yol = f"series={kod}&startDate={bas}&endDate={datetime.date.today().strftime('%d-%m-%Y')}&type=json"
    for taban in (EVDS, 'https://evds2.tcmb.gov.tr/service/evds/'):
        try:
            anahtar = os.environ.get('EVDS_API_KEY', '').strip()
            req = urllib.request.Request(taban + yol, headers={'key': anahtar, 'User-Agent': 'Endeks24-zaman/1', 'Accept': 'application/json'})
            ham = urllib.request.urlopen(req, timeout=90).read().decode('utf-8', 'replace')
            if not ham.lstrip().startswith(('{', '[')):
                continue
            out = []
            for x in json.loads(ham).get('items', []):
                v = x.get(alan)
                if v in (None, ''):
                    continue
                t = x['Tarih'].split('-')
                if len(t) == 3:
                    iso = f"{t[2]}-{t[1]}-{t[0]}" if len(t[0]) <= 2 else f"{t[0]}-{t[1]}-{t[2]}"
                else:
                    iso = f"{int(t[0]):04d}-{int(t[1]):02d}-01"
                out.append((iso, float(v)))
            if out:
                return sorted(out)
        except Exception as e:
            log('evds hata', kod, taban, str(e)[:100])
    return []


def son_deger(tarihler, deger, t):
    i = bisect.bisect_right(tarihler, t) - 1
    return deger[i] if i >= 0 else None


def uret(kok):
    ft = hh.baglan()
    xu = gunluk(ft, 'endeks_mumlar_gunluk_gh', 'XU100')
    usd = gunluk(ft, 'mumlar_gunluk_gh', 'USDTRY')
    eur = gunluk(ft, 'mumlar_gunluk_gh', 'EURTRY')
    alt = gunluk(ft, 'mumlar_gunluk_gh', 'GRAMALTIN')
    log('günlük satır', len(xu), len(usd), len(eur), len(alt))
    if min(len(xu), len(usd), len(eur), len(alt)) < 2000:
        sys.exit('HATA: günlük seri kısa')
    # haftalık takvim: BIST 100 işlem günlerinden her ISO haftanın son günü
    hafta = {}
    for t in sorted(xu):
        d = datetime.date.fromisoformat(t)
        hafta[d.isocalendar()[:2]] = t
    g = sorted(hafta.values())
    def seri(d):
        k = sorted(d)
        v = [d[x] for x in k]
        return [round(son_deger(k, v, t), 4) if son_deger(k, v, t) is not None else None for t in g]
    ms = evds_seri('TP.TRY.MT02')
    log('mevduat', len(ms), ms[:1], ms[-1:])
    if len(ms) < 100:
        sys.exit('HATA: mevduat serisi kısa')
    mk = [t for t, _ in ms]; mv = [v for _, v in ms]
    mev = [100.0]
    for i in range(1, len(g)):
        r = son_deger(mk, mv, g[i - 1])
        gun = (datetime.date.fromisoformat(g[i]) - datetime.date.fromisoformat(g[i - 1])).days
        mev.append(mev[-1] * (1 + (r or 0) / 100 * gun / 365))
    # TÜFE: EVDS TP.GENENDEKS.T1 (Tüketici Fiyat Endeksi, genel, 2003=100, aylık)
    tufe = {t[:7]: v for t, v in evds_seri('TP.GENENDEKS.T1', '01-01-2005')}
    log('tüfe', len(tufe), min(tufe) if tufe else None, max(tufe) if tufe else None)
    if len(tufe) < 200:
        sys.exit('HATA: TÜFE serisi kısa')
    out = {'guncelleme': datetime.datetime.now(fg.TR).isoformat(timespec='minutes'), 'g': g, 'xu': seri(xu), 'usd': seri(usd), 'eur': seri(eur), 'alt': seri(alt),
           'mev': [round(x, 4) for x in mev], 'tufe': {m: round(v, 4) for m, v in sorted(tufe.items())}}
    os.makedirs(os.path.join(kok, 'zaman-makinesi'), exist_ok=True)
    yol = os.path.join(kok, 'zaman-makinesi', 'seri.json')
    json.dump(out, open(yol, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    log('yazıldı', yol, os.path.getsize(yol), 'bayt;', len(g), 'hafta;', g[0], g[-1])


def tufe_tani():
    """2005 numaralı kategorideki (TÜFE, TÜİK) bütün gruplarda adında 'genel' geçen serileri yazar."""
    for g in evds_al('datagroups/mode=2&code=2005&type=json'):
        log('grup', g.get('DATAGROUP_CODE'), g.get('DATAGROUP_NAME'), g.get('START_DATE'), g.get('END_DATE'), g.get('FREQUENCY_STR'))
        try:
            for x in evds_al(f"serieList/type=json&code={g['DATAGROUP_CODE']}"):
                ad = (x.get('SERIE_NAME') or '')
                if 'genel' in ad.lower() or 'general' in ad.lower() or 'TÜFE' == ad.strip():
                    log('     seri', x.get('SERIE_CODE'), ad, x.get('START_DATE'), x.get('END_DATE'), x.get('FREQUENCY_STR'))
        except Exception as e:
            log('     seri listesi alınamadı', str(e)[:80])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == 'tani':
        tani()
    elif sys.argv[1] == 'tufe-tani':
        tufe_tani()
    else:
        uret(sys.argv[2] if len(sys.argv) > 2 else '.')
