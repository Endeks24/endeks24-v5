"""Endeks24 Hisse Tarayıcısı verisi (28.10.2026). Yapay zeka ve ek veri çağrısı yoktur.

Girdi: profil-veri dalındaki profil/<KOD>.json (finansal tablolar, haftalık) ve borsa-veri dalındaki borsa/ozet.json (güncel fiyat, getiri, hacim, piyasa değeri).
Çıktı: <kök>/tarayici/ozet.json. Hisse sayfasındaki "Temel göstergeler" ile aynı formüller:
  F/K = piyasa değeri / son 12 ay ana ortaklık net kârı (zarar eden şirkette boş), PD/DD = piyasa değeri / ana ortaklık özkaynağı,
  FD/FAVÖK = (piyasa değeri + net borç) / son 12 ay FAVÖK, temettü verimi = son 12 ay ödenen temettü / piyasa değeri.
Kullanım: python3 tarayici_veri.py <profil_klasörü> <borsa_ozet.json> <kök_klasör>
"""
import datetime, glob, json, os, sys

TR = datetime.timezone(datetime.timedelta(hours=3))


def r(x, n=2):
    return None if x is None else round(x, n)


def tr_baslik(s):
    """'TOPTAN VE PERAKENDE TİCARET' -> 'Toptan ve Perakende Ticaret' (Türkçe büyük/küçük harf kuralıyla)."""
    kucuk = lambda x: x.replace('İ', 'i').replace('I', 'ı').lower()
    buyuk = lambda x: x.replace('i', 'İ').replace('ı', 'I').upper()
    out = []
    for w in s.split():
        w = kucuk(w)
        out.append(w if w in ('ve', 'ile') else buyuk(w[0]) + w[1:])
    return ' '.join(out)


def main():
    profil_dir, ozet_yol, kok = sys.argv[1:4]
    oz = json.load(open(ozet_yol))
    tablo = {t['k']: t for t in oz['tablo']}
    satirlar, sektorler = [], set()
    for f in sorted(glob.glob(f'{profil_dir}/*.json')):
        p = json.load(open(f))
        t = tablo.get(p['kod'])
        if not t:
            continue
        pd = t.get('pd') or p.get('pd')
        F = p.get('fin') or {}
        T = F.get('ttm') or {}
        net, favok, satis = T.get('net'), T.get('favok'), T.get('satis')
        ozk, nb = F.get('oz'), F.get('nb')
        tmt = (p.get('tmt') or {}).get('ttm')
        O = F.get('oran') or {}
        sek = tr_baslik((p.get('sektor') or '').split(' / ')[0].strip()) or None
        if sek:
            sektorler.add(sek)
        # BIST'te günlük fiyat sınırı %10'dur; kapanışlar arasında bundan büyük sıçrama bölünme/bedelsiz gibi sermaye işlemi sayılır (fiyat düzeltilmemiştir), getiri gösterilmez.
        # Art arda taban serisi (ör. her gün %10 düşüş) gerçek fiyat hareketidir ve gösterilir.
        nm_ = r(net / satis * 100, 1) if satis and satis > 0 and net is not None else None
        nm_ = nm_ if nm_ is None or abs(nm_) <= 100 else None   # %100'ü aşan marj faaliyet dışı kalemlerden (değerleme geliri vb.) gelir, gösterilmez
        roe_ = r(O.get('Özkaynak Karlılığı'), 1)
        roe_ = roe_ if roe_ is None or abs(roe_) <= 100 else None
        sp = t.get('sp') or []
        bozuk = any(b and abs(a / b - 1) > 0.106 for b, a in zip(sp, sp[1:]))
        # İkinci sınıf paylar (ör. ISBTR, ISKUR): piyasa değeri ile bilanço aynı birimde değildir (PD/DD 0,02'nin altı ya da 200'ün üstü), çarpanlar anlamsızdır ve gösterilmez.
        sinif = bool(pd and ozk and ozk > 0 and not 0.02 <= pd / ozk <= 200) or bool(pd and net and net > 0 and pd / net < 0.02)
        satirlar.append({
            'k': p['kod'], 'ad': p['ad'], 'sek': sek, 's': t['s'], 'd': t['d'], 'h5': None if bozuk else t.get('h5'), 'h1a': None if bozuk else t.get('h30'), 'sk': 1 if bozuk else 0, 'hc': t['hc'],
            'pd': pd, 'fk': None if sinif else (r(pd / net, 1) if pd and net and net > 0 else None), 'zarar': 1 if net is not None and net <= 0 else 0,
            'pddd': None if sinif else (r(pd / ozk, 2) if pd and ozk and ozk > 0 else None),
            'fdf': None if sinif else r((pd + nb) / favok, 1) if pd and favok and favok > 0 and nb is not None and pd + nb > 0 else None,
            'tv': None if sinif else (r(tmt / pd * 100, 2) if pd and tmt and tmt > 0 else None),
            'nm': nm_, 'roe': roe_, 'e': t.get('e') or [], 'bil': F.get('donem'),
        })
    satirlar.sort(key=lambda z: -(z['pd'] or 0))
    if len(satirlar) < 300:
        print('çok az hisse, dosya yazılmadı', len(satirlar))
        sys.exit(1)
    os.makedirs(f'{kok}/tarayici', exist_ok=True)
    cikti = {'olusturma': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M:%S+03:00'), 'fiyat_tarihi': oz.get('tarih'),
             'n': len(satirlar), 'sektorler': sorted(sektorler), 'hisseler': satirlar}
    json.dump(cikti, open(f'{kok}/tarayici/ozet.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    say = lambda a: sum(1 for z in satirlar if z[a] is not None)
    print('TAMAM', len(satirlar), 'hisse | F/K', say('fk'), 'PD/DD', say('pddd'), 'FD/FAVÖK', say('fdf'), 'temettü', say('tv'))


if __name__ == '__main__':
    main()
