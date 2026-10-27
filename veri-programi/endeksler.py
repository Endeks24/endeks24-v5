"""Endeks24 endeksleri (27.10.2026): kural tabanlı, eşit ağırlıklı fiyat endeksleri. Yapay zeka çağrısı yoktur; Fintables'a da sorgu atmaz,
yalnız depodaki dosyalardan hesaplar:
  fiyat/<KOD>.json, fiyat/takvim.json   günlük kapanışlar (bölünmeye göre düzeltilmiş)       (main)
  analiz/fon-dedektifi.json             fonların aylık net hisse alımı                         (main)
  profil/<KOD>.json                     pazar, sektör, ilk işlem tarihi, net borç, FAVÖK, PD   (profil-veri dalı)
  borsa/hisse/<KOD>.json                20 günlük ortalama hacim                               (borsa-veri dalı)

Endeksler
  halka-arz   Son 36 ayda işlem görmeye başlamış, Yıldız/Ana Pazar'da, günlük ortalama hacmi >= 25 mn TL olan en likit 20 hisse. Çeyrek başında yenilenir.
  net-nakit   Finans dışı (banka, sigorta, GYO, holding, yatırım ortaklığı hariç), net borcu negatif, 12 aylık FAVÖK'ü pozitif, Yıldız/Ana Pazar,
              hacim >= 25 mn TL; net nakdin piyasa değerine oranı en yüksek 20 hisse. Çeyrek başında yenilenir.
  fon-akisi   Fonların son aylık portföy raporunda en çok net aldığı hisseler (Yıldız/Ana Pazar, hacim >= 25 mn TL, bedelsiz şüphelileri hariç). Aylık yenilenir.

Hesap: yenileme gününün kapanışında eşit tutarlı alım; sonraki günlerde adetler sabit (ağırlık kayar); bir sonraki yenilemede yeniden eşitlenir.
Yalnızca fiyat endeksidir, temettü içermez. Geriye dönük kısım "simülasyon" olarak işaretlenir (bugünün hisse evreni ve filtreleri tarihe uygulanır;
sonradan işlemden kalkan şirketler evrende yoktur). 'canli_baslangic' tarihinden sonrası canlı hesaptır.

Kullanım: python3 endeksler.py <kök> --profil <dizin> --borsa <dizin>
"""
import datetime, glob, json, os, sys

TR = datetime.timezone(datetime.timedelta(hours=3))
CANLI = '2026-10-27'          # bu tarihten sonraki günler canlı hesap
HACIM_MIN = 25e6
EN_FAZLA = 20
FINANS = ('MALİ KURULUŞLAR', 'FİNANS', 'BANKA', 'SİGORTA', 'GAYRİMENKUL', 'YATIRIM ORTAKLI', 'HOLDİNG', 'FAKTORİNG', 'LEASING', 'FİNANSMAN')
ADLAR = {
    'halka-arz': {'ad': 'Endeks24 Halka Arz Endeksi', 'kisa': 'Halka Arz Endeksi', 'baslangic': '2024-01-02', 'yenileme': 'ceyrek',
                  'kural': 'Son 36 ayda Borsa İstanbul\'da işlem görmeye başlamış ve Yıldız veya Ana Pazar\'da işlem gören tüm hisseler, eşit ağırlıkla. Her çeyreğin ilk işlem gününde (Ocak, Nisan, Temmuz, Ekim) yenilenir; o güne kadar 36 ayını dolduran hisseler çıkar, yeni halka arzlar girer. Hacim eşiği ya da hisse sayısı sınırı yoktur, çünkü bunlar geçmiş günlere uygulanamaz.'},
    'net-nakit': {'ad': 'Endeks24 Net Nakit Endeksi', 'kisa': 'Net Nakit Endeksi', 'baslangic': '2026-10-26', 'yenileme': 'ceyrek',
                  'kural': 'Finans dışı şirketlerden (banka, sigorta, GYO, holding ve yatırım ortaklıkları hariç), net borcu negatif (kasası borcundan büyük), son 12 ay FAVÖK\'ü pozitif, Yıldız veya Ana Pazar\'da işlem gören ve günlük ortalama hacmi en az 25 milyon TL olan hisselerden, net nakdin piyasa değerine oranı en yüksek 20\'si. Her çeyreğin ilk işlem gününde, o gün yayımlanmış en son bilançolarla yenilenir.'},
    'fon-akisi': {'ad': 'Endeks24 Fon Akışı Endeksi', 'kisa': 'Fon Akışı Endeksi', 'baslangic': '2026-10-26', 'yenileme': 'ay',
                  'kural': 'Yatırım fonlarının son aylık portföy raporunda en çok net aldığı hisselerden (bedelsiz sermaye artırımı şüphesi olanlar hariç), Yıldız veya Ana Pazar\'da işlem gören ve günlük ortalama hacmi en az 25 milyon TL olanlar. Fon portföy raporları bir ay gecikmeli yayımlanır; liste her ay yeni rapor geldiğinde yenilenir.'},
}


def oku(yol, varsayilan=None):
    try:
        return json.load(open(yol, encoding='utf-8'))
    except Exception:
        return varsayilan


def r(x, n=2):
    return None if x is None else round(x, n)


def yildiz_ana(p):
    s = (p.get('pazar') or '').upper()
    if any(x in s for x in ('YAKIN İZLEME', 'GÖZALTI', 'PİYASA ÖNCESİ')):   # sığ ya da izleme kapsamındaki tahtalar dışarıda
        return False
    return 'YILDIZ PAZAR' in s or 'ANA PAZAR' in s


def finans_mi(p):
    s = (p.get('sektor') or '').upper()
    return any(x in s for x in FINANS)


class Fiyat:
    def __init__(self, kok):
        t = oku(os.path.join(kok, 'fiyat', 'takvim.json'))
        self.gun = t['gun']
        self.ix = {g: i for i, g in enumerate(self.gun)}
        self.kok = kok
        self.on = {}

    def seri(self, kod):
        if kod not in self.on:
            d = oku(os.path.join(self.kok, 'fiyat', kod + '.json'))
            c = [None] * len(self.gun)
            if d:
                for i, v in enumerate(d['c']):
                    if d['b'] + i < len(c):
                        c[d['b'] + i] = v
            son = None
            for i, v in enumerate(c):      # eksik günler önceki kapanışla doldurulur
                if v is None:
                    c[i] = son
                else:
                    son = v
            self.on[kod] = c
        return self.on[kod]


def yenileme_gunleri(gunler, bas, periyot):
    """İlk işlem günleri: çeyrek (Oca, Nis, Tem, Eki) ya da ay başı. bas: ilk gün."""
    out, son = [], None
    for g in gunler:
        if g < bas:
            continue
        anahtar = (g[:4], (int(g[5:7]) - 1) // 3) if periyot == 'ceyrek' else g[:7]
        if anahtar != son:
            out.append(g)
            son = anahtar
    return out


def evren_halka_arz(tarih, P, B):
    sinir = (datetime.date.fromisoformat(tarih) - datetime.timedelta(days=1095)).isoformat()
    # Tarihe uygulanabilir tek kural ilk işlem tarihidir; hacim eşiği ve sıralama bugünün verisi olduğundan geçmişe uygulanırsa sonucu şişirir (denendi), bu yüzden kullanılmaz.
    return sorted(k for k, p in P.items() if (p.get('ilk_islem') or '')[:10] and sinir < (p.get('ilk_islem') or '')[:10] < tarih and yildiz_ana(p) and k in B)


def evren_net_nakit(tarih, P, B):
    L = []
    for k, p in P.items():
        f = p.get('fin') or {}
        pd = p.get('pd')
        nb, fav = f.get('nb'), (f.get('ttm') or {}).get('favok')
        if (k in B and not finans_mi(p) and yildiz_ana(p) and nb is not None and nb < 0 and fav and fav > 0 and pd and pd > 0
                and (B[k].get('hacim_ort') or 0) >= HACIM_MIN):
            L.append((k, -nb / pd))
    return [k for k, _ in sorted(L, key=lambda z: -z[1])[:EN_FAZLA]]


def evren_fon(tarih, P, B, fon):
    sus = set(fon.get('bedelsiz_suphesi') or [])
    L = []
    for x in fon.get('alinan') or []:
        k = x['kod']
        p = P.get(k)
        if p and k not in sus and yildiz_ana(p) and k in B and (B[k].get('hacim_ort') or 0) >= HACIM_MIN:
            L.append((k, x['net_tl']))
    return [k for k, _ in sorted(L, key=lambda z: -z[1])[:EN_FAZLA]]


def hesapla(ad, tanim, fp, evren_f, xu, kayit):
    gunler = [g for g in fp.gun if g >= tanim['baslangic']]
    if not gunler:
        return None
    yen = yenileme_gunleri(gunler, tanim['baslangic'], tanim['yenileme'])
    seviye, gl = [100.0], [yen[0]]
    L = 100.0
    gecmis, onceki, uyeler_son, i0son = [], set(), [], None
    for ri, rg in enumerate(yen):
        i0 = fp.ix[rg]
        if rg in kayit:                      # geçmiş yenileme listesi dondurulmuştur, bugünün verisiyle yeniden hesaplanmaz
            uyeler = [k for k in kayit[rg] if fp.seri(k)[i0]]
        elif ad == 'halka-arz' or rg >= max(kayit, default='0000-00-00'):
            uyeler = [k for k in evren_f(rg) if fp.seri(k)[i0]]
            kayit[rg] = uyeler
        else:
            continue
        if not uyeler:
            continue
        gecmis.append({'tarih': rg, 'giren': sorted(set(uyeler) - onceki), 'cikan': sorted(onceki - set(uyeler)), 'n': len(uyeler)})
        onceki = set(uyeler)
        i1 = fp.ix[yen[ri + 1]] if ri + 1 < len(yen) else len(fp.gun) - 1
        for i in range(i0 + 1, i1 + 1):
            v = sum((fp.seri(k)[i] or fp.seri(k)[i0]) / fp.seri(k)[i0] for k in uyeler) / len(uyeler)
            seviye.append(r(L * v, 3))
            gl.append(fp.gun[i])
        if i1 > i0:
            L = seviye[-1]
        uyeler_son, i0son = uyeler, i0
    if not uyeler_son or len(gl) < 1:
        return None
    xs = [xu[fp.ix[g]] for g in gl]
    bist = [r(100 * x / xs[0], 3) for x in xs]
    ag = {k: fp.seri(k)[-1] / fp.seri(k)[i0son] for k in uyeler_son}
    top = sum(ag.values()) or 1
    return {'gunler': gl, 'seviye': seviye, 'bist100': bist, 'uyeler': uyeler_son, 'agirlik': {k: r(100 * v / top, 2) for k, v in ag.items()},
            'getiri_1a': {k: r((fp.seri(k)[-1] / fp.seri(k)[max(0, len(fp.gun) - 23)] - 1) * 100, 1) for k in uyeler_son if fp.seri(k)[max(0, len(fp.gun) - 23)]},
            'getiri_yenileme': {k: r((fp.seri(k)[-1] / fp.seri(k)[i0son] - 1) * 100, 1) for k in uyeler_son}, 'yenilemeler': gecmis[-8:]}


AYLAR = ['', 'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def tr(x, n=1):
    return f'{x:,.{n}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def yuz(x, n=1):
    if 0 < abs(x) < 0.1:
        n = 2
    return ('+' if x > 0 else '−' if x < 0 else '') + '%' + tr(abs(x), n)


def gun_yaz(g):
    return f'{int(g[8:10])} {AYLAR[int(g[5:7])]} {g[:4]}'


def getiri(d, n):
    S, B = d['seviye'], d['bist100']
    i = len(S) - 1 - n
    if n < 1 or i < 0:
        return None
    return (S[-1] / S[i] - 1) * 100, (B[-1] / B[i] - 1) * 100


def ozet_uret(cikti, kok):
    """Medya kuruluşları ve haber masaları için: her endeksin dönemsel getirileri, öne çıkan bileşenleri ve hazır, olgusal cümleler. Yön tahmini ya da tavsiye içermez."""
    ATIF = 'Kaynak: Endeks24 Endeksleri (https://www.endeks24.com/endeksler)'
    out = {'guncelleme': datetime.datetime.now(TR).isoformat(timespec='minutes'), 'atif': ATIF,
           'kullanim': 'Serbestçe alıntılanabilir; kaynak olarak Endeks24 Endeksleri belirtilmeli ve bağlantı verilmelidir. Yatırım tavsiyesi değildir; resmi bir borsa endeksi değildir.', 'endeksler': {}}
    for ad, d in cikti.items():
        gl = d['gunler']
        e = {'ad': d['ad'], 'sayfa': 'https://www.endeks24.com/endeks24-' + ad + '-endeksi', 'veri': f'https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/endeksler/{ad}.json',
             'csv': f'https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/endeksler/{ad}.csv', 'tarih': gl[-1], 'deger': d['seviye'][-1], 'bist100': d['bist100'][-1], 'baslangic': gl[0],
             'uye_sayisi': len(d['uyeler']), 'yenileme': d['yenileme'], 'simulasyon_sonu': d['canli_baslangic'], 'getiri': {}}
        yil_basi = next((i for i, g in enumerate(gl) if g[:4] == gl[-1][:4]), None)
        for ad_, n in (('1_gun', 1), ('1_hafta', 5), ('1_ay', 22), ('3_ay', 63), ('baslangictan', len(gl) - 1)):
            g = getiri(d, n)
            if g:
                e['getiri'][ad_] = {'endeks': round(g[0], 2), 'bist100': round(g[1], 2), 'fark_puan': round(g[0] - g[1], 2)}
        if yil_basi and yil_basi > 0:
            g = getiri(d, len(gl) - 1 - (yil_basi - 1))
            if g:
                e['getiri']['yil_basi'] = {'endeks': round(g[0], 2), 'bist100': round(g[1], 2), 'fark_puan': round(g[0] - g[1], 2)}
        ay = d.get('getiri_1a') or {}
        sirali = sorted(ay.items(), key=lambda z: z[1])
        ad_ = d.get('adlar') or {}
        e['en_cok_artan'] = [{'kod': k, 'ad': ad_.get(k), 'getiri_1_ay': v} for k, v in sirali[::-1][:3]]
        e['en_cok_dusen'] = [{'kod': k, 'ad': ad_.get(k), 'getiri_1_ay': v} for k, v in sirali[:3]]
        y = (d.get('yenilemeler') or [])[-1:] or [{}]
        e['son_yenileme'] = {'tarih': y[0].get('tarih'), 'giren': y[0].get('giren'), 'cikan': y[0].get('cikan')}
        c = []
        t = gun_yaz(gl[-1])
        g1 = e['getiri'].get('1_gun')
        if g1:
            c.append(f"{d['ad']} {t} tarihinde {yuz(g1['endeks'])} değişti; aynı gün BIST 100 {yuz(g1['bist100'])} değişti.")
        for k, etiket in (('1_ay', 'Son bir ayda'), ('3_ay', 'Son üç ayda'), ('yil_basi', 'Yıl başından bu yana'), ('baslangictan', f'{gun_yaz(gl[0])} başlangıcından bu yana')):
            g = e['getiri'].get(k)
            if g:
                yon = 'önünde' if g['fark_puan'] > 0 else 'gerisinde' if g['fark_puan'] < 0 else 'aynı seviyesinde'
                c.append(f"{etiket} {d['ad']} {yuz(g['endeks'])} değişirken BIST 100 {yuz(g['bist100'])} değişti; endeks BIST 100'ün {tr(abs(g['fark_puan']))} puan {yon}.")
        if sirali:
            c.append(f"Son bir ayda {d['ad']} bileşenleri arasında en çok yükselen {sirali[-1][0]} ({yuz(sirali[-1][1])}), en çok düşen {sirali[0][0]} ({yuz(sirali[0][1])}) oldu.")
        if d['canli_baslangic'] and gl[0] < d['canli_baslangic'] < gl[-1] and ad == 'halka-arz':
            c.append('Halka arz endeksinin ' + gun_yaz(d['canli_baslangic']) + ' öncesi geçmişi simülasyondur (bugünün hisse evreni geçmişe uygulanmıştır).')
        e['hazir_cumleler'] = c
        out['endeksler'][ad] = e
    out['gunun_notu'] = [x for e in out['endeksler'].values() for x in e['hazir_cumleler'][:1]]
    json.dump(out, open(os.path.join(kok, 'endeksler', 'ozet.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for ad, d in cikti.items():
        with open(os.path.join(kok, 'endeksler', ad + '.csv'), 'w', encoding='utf-8') as f:
            f.write('tarih,endeks,bist100\n')
            for g, a, b in zip(d['gunler'], d['seviye'], d['bist100']):
                f.write(f'{g},{a},{b}\n')


def main(kok, profil, borsa):
    fp = Fiyat(kok)
    P = {os.path.basename(f)[:-5]: oku(f, {}) for f in glob.glob(os.path.join(profil, 'profil', '*.json'))}
    B = {os.path.basename(f)[:-5]: oku(f, {}) for f in glob.glob(os.path.join(borsa, 'borsa', 'hisse', '*.json'))}
    fon = oku(os.path.join(kok, 'analiz', 'fon-dedektifi.json'), {})
    xu = Fiyat(kok).seri('XU100')
    for k in list(P):
        fp.seri(k)
    kayitlar = oku(os.path.join(kok, 'endeksler', 'uyelik.json'), {})
    cikti = {}
    ev = {'halka-arz': lambda t: evren_halka_arz(t, P, B), 'net-nakit': lambda t: evren_net_nakit(t, P, B), 'fon-akisi': lambda t: evren_fon(t, P, B, fon)}
    for ad, f in ev.items():
        h = hesapla(ad, ADLAR[ad], fp, f, xu, kayitlar.setdefault(ad, {}))
        if not h:
            print('endeks', ad, 'hesaplanamadı')
            continue
        d = dict(ADLAR[ad])
        d.update(h)
        d['canli_baslangic'] = CANLI
        d['guncelleme'] = datetime.datetime.now(TR).isoformat(timespec='minutes')
        d['adlar'] = {k: (P.get(k) or {}).get('ad') for k in h['uyeler']}
        d['not'] = ('Eşit ağırlıklı fiyat endeksidir; temettü içermez. Bu çalışma ticari bir finansal ürün ya da resmi borsa endeksi değil, Endeks24\'ün gazetecilik faaliyeti kapsamında ürettiği istatistiki bir veri serisidir; '
                    'yatırım tavsiyesi değildir. Geriye dönük kısım simülasyondur: bugünün hisse evreni ve filtreleri geçmişe uygulanır, sonradan işlemden kalkan şirketler dahil değildir.')
        cikti[ad] = d
        print('endeks', ad, 'gün', len(h['gunler']), 'son', h['seviye'][-1], 'bist', h['bist100'][-1], 'üye', len(h['uyeler']))
    os.makedirs(os.path.join(kok, 'endeksler'), exist_ok=True)
    json.dump(kayitlar, open(os.path.join(kok, 'endeksler', 'uyelik.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    for ad, d in cikti.items():
        json.dump(d, open(os.path.join(kok, 'endeksler', ad + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    ozet_uret(cikti, kok)
    json.dump({'guncelleme': datetime.datetime.now(TR).isoformat(timespec='minutes'),
               'liste': [{'id': a, 'ad': d['ad'], 'kisa': d['kisa'], 'son': d['seviye'][-1], 'bist100': d['bist100'][-1], 'baslangic': d['baslangic'], 'n': len(d['uyeler']), 'canli_baslangic': CANLI} for a, d in cikti.items()]},
              open(os.path.join(kok, 'endeksler', 'liste.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    a = sys.argv
    if len(a) < 6 or '--profil' not in a or '--borsa' not in a:
        sys.exit(__doc__)
    main(a[1], a[a.index('--profil') + 1], a[a.index('--borsa') + 1])
