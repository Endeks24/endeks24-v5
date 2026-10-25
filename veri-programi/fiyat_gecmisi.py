"""Endeks24 "Haberden bu yana" fiyat geçmişi (25.10.2026).
Fintables MCP'den (salt okuma) BIST hisseleri ve XU100 için günlük kapanışları okur; <cikti>/fiyat/ altına yazar:
  takvim.json   {"guncelleme", "gun": [işlem günleri], "kodlar": [dosyası olan kodlar]}
  <KOD>.json    {"b": takvimde ilk gün sırası, "c": [kapanışlar; işlem görmeyen gün 0]}
Site yalnız habere uygun kodların dosyasını okur, hesap tarayıcıdadır; yapay zeka çağrısı yoktur.
Kapanışlar bölünmeye (bedelsiz) göre düzeltilmiştir; yeni bölünme olunca eski kapanışlar değişir. Bu yüzden her çalışmada son
ARTIM gün yeniden okunur, mevcut kayıtla çakışan günlerde fark varsa o kodun geçmişi baştan okunur.
Kullanım: python3 fiyat_gecmisi.py <cikti_klasoru> [--bas 2023-01-02] [--sinir N] [--tam] [--kod A,B]
Anahtar FINTABLES ortam değişkeninde (GitHub secret).
"""
import datetime, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hafiza_hesapla as hh

TR = datetime.timezone(datetime.timedelta(hours=3))
ENDEKS = 'XU100'
ARTIM = 12        # her çalışmada yeniden okunan takvim günü
TOLERANS = 0.002  # çakışan günde göreli fark; üstü bölünme sayılır
KOD_GRUP = 15     # artımlı okumada tek sorgudaki kod sayısı


def log(*a):
    print(*a, flush=True)


def arg(ad, varsayilan=None):
    return sys.argv[sys.argv.index(ad) + 1] if ad in sys.argv else varsayilan


def gun(zaman_utc):
    return datetime.datetime.fromisoformat(zaman_utc.replace('Z', '+00:00')).astimezone(TR).date().isoformat()


def sayfala(ft, sorgu):
    """OFFSET ile sayfalar; boş sayfaya kadar okur."""
    out, off = [], 0
    while True:
        sat = ft.sql(f'{sorgu} LIMIT 1000 OFFSET {off}')
        if not sat:
            return out
        out += sat
        off += len(sat)


def oku_kod(ft, kod, bas):
    tablo = 'endeks_mumlar_gunluk_gh' if kod == ENDEKS else 'mumlar_gunluk_gh'
    sat = sayfala(ft, f"SELECT zaman_utc, kapanis FROM {tablo} WHERE kod = '{kod}' AND zaman_utc >= TIMESTAMP '{bas} 00:00:00' ORDER BY zaman_utc")
    return {gun(r['zaman_utc']): float(r['kapanis']) for r in sat if r.get('kapanis') is not None}


def oku_grup(ft, kodlar, bas):
    sonuc = {k: {} for k in kodlar}
    liste = ','.join(f"'{k}'" for k in kodlar)
    for r in sayfala(ft, f"SELECT zaman_utc, kod, kapanis FROM mumlar_gunluk_gh WHERE kod IN ({liste}) AND zaman_utc >= TIMESTAMP '{bas} 00:00:00' ORDER BY kod, zaman_utc"):
        if r.get('kapanis') is not None:
            sonuc[r['kod']][gun(r['zaman_utc'])] = float(r['kapanis'])
    return sonuc


def yukle(klasor, kod, takvim):
    """Dosyadan {tarih: kapanis}."""
    yol = os.path.join(klasor, kod + '.json')
    if not os.path.exists(yol):
        return {}
    d = json.load(open(yol, encoding='utf-8'))
    return {takvim[d['b'] + i]: c for i, c in enumerate(d['c']) if c and d['b'] + i < len(takvim)}


def yaz(klasor, kod, seri, indeks):
    ts = [t for t in seri if t in indeks]
    if not ts:
        return False
    b, s = min(indeks[t] for t in ts), max(indeks[t] for t in ts)
    c = [0] * (s - b + 1)
    for t in ts:
        c[indeks[t] - b] = round(seri[t], 4)
    json.dump({'b': b, 'c': c}, open(os.path.join(klasor, kod + '.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    return True


def cakisma_farkli(eski, yeni):
    ortak = [t for t in yeni if t in eski]
    return any(abs(yeni[t] / eski[t] - 1) > TOLERANS for t in ortak if eski[t])


def birlestir(eski, yeni):
    """Tam okuma yeni sayılır; artımlı okumada yeni günler eskinin üstüne yazılır."""
    out = dict(eski)
    out.update(yeni)
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith('--'):
        sys.exit(__doc__)
    klasor = os.path.join(sys.argv[1], 'fiyat')
    os.makedirs(klasor, exist_ok=True)
    bas = arg('--bas', '2023-01-02')
    sinir = int(arg('--sinir', 0) or 0)
    tam = '--tam' in sys.argv
    ft = hh.baglan()

    takvim_yol = os.path.join(klasor, 'takvim.json')
    eski_takvim = json.load(open(takvim_yol, encoding='utf-8')) if os.path.exists(takvim_yol) and not tam else {'gun': [], 'kodlar': []}
    eski_gun = eski_takvim['gun']

    kodlar = arg('--kod')
    kodlar = kodlar.split(',') if kodlar else sorted({r['hisse_senedi_kodu'] for r in ft.sql("SELECT hisse_senedi_kodu FROM hisse_senetleri LIMIT 2000")})
    if sinir:
        kodlar = kodlar[:sinir]
    log('kod', len(kodlar))

    # takvim: XU100 işlem günleri
    artim_bas = (datetime.date.fromisoformat(eski_gun[-ARTIM]) if len(eski_gun) > ARTIM else datetime.date.fromisoformat(bas)).isoformat()
    endeks_yeni = oku_kod(ft, ENDEKS, bas if not eski_gun else artim_bas)
    if not endeks_yeni:
        sys.exit('HATA: XU100 verisi boş')
    gun_kume = sorted(set(eski_gun) | set(endeks_yeni))
    if gun_kume[:len(eski_gun)] != eski_gun:
        sys.exit('HATA: takvim geriye değişti; --tam ile baştan oluşturun')
    indeks = {t: i for i, t in enumerate(gun_kume)}

    eski_endeks = yukle(klasor, ENDEKS, eski_gun)
    if eski_endeks and cakisma_farkli(eski_endeks, endeks_yeni):
        log('XU100 çakışması farklı, baştan okunuyor')
        endeks_yeni = oku_kod(ft, ENDEKS, bas)
        eski_endeks = {}
    yaz(klasor, ENDEKS, birlestir(eski_endeks, endeks_yeni), indeks)

    # hisseler
    yeniden, yazilan = [], []
    eski_kodlar = {k: yukle(klasor, k, eski_gun) for k in kodlar} if eski_gun else {}
    ilk = [k for k in kodlar if not eski_kodlar.get(k)]
    artimli = [k for k in kodlar if eski_kodlar.get(k)]
    for i in range(0, len(artimli), KOD_GRUP):
        g = artimli[i:i + KOD_GRUP]
        yeni = oku_grup(ft, g, artim_bas)
        for k in g:
            if cakisma_farkli(eski_kodlar[k], yeni[k]):
                yeniden.append(k)
                continue
            if yaz(klasor, k, birlestir(eski_kodlar[k], yeni[k]), indeks):
                yazilan.append(k)
        log('  artımlı', min(i + KOD_GRUP, len(artimli)), '/', len(artimli))
    tam_liste = ilk + yeniden
    log('tam okunacak', len(tam_liste), '(bölünme şüphesi:', len(yeniden), ')')
    for n, k in enumerate(tam_liste):
        seri = oku_kod(ft, k, bas)
        if yaz(klasor, k, seri, indeks):
            yazilan.append(k)
        if n % 25 == 0:
            log('  tam', n, '/', len(tam_liste))
    dosyali = sorted(k for k in kodlar if os.path.exists(os.path.join(klasor, k + '.json')))
    json.dump({'guncelleme': datetime.datetime.now(TR).isoformat(timespec='seconds'), 'son': gun_kume[-1], 'gun': gun_kume, 'kodlar': dosyali},
              open(takvim_yol, 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False)
    log('TAMAM', len(dosyali), 'kod,', len(gun_kume), 'gün, son', gun_kume[-1])


if __name__ == '__main__':
    main()
