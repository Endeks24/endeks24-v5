"""Endeks24 Göstergeleri (31.10.2026): Endeks24 Endekslerinin yanında, okurun ve medyanın ilgisini çekecek tek ürünlü ya da toplu göstergeler.
Yapay zeka çağrısı yoktur; Fintables'a sorgu atmaz, depodaki dosyalardan hesaplar:
  zaman-makinesi/seri.json             haftalık dolar, euro, gram altın (main)
  analiz/bilanco-surpriz.json          bilanço sürprizi (main)
  endeksler/gostergeler.json           önceki çıktı; günlük seriler buraya eklenerek büyür (main)
  endeksler/girdi/*.json               elle ve kaynaklı derlenen fiyatlar (Simit ve Menemen Endeksi, maaş karşılığı) (main)
  borsa/ozet.json, borsa/hisse/*.json  günlük kapanış, tavan/taban, aracı kurum hedef fiyatları (borsa-veri dalı)
  dunya/ozet.json                      Brent (dunya-veri dalı)

Göstergeler
  alim-gucu     Net asgari ücretin dolar, euro, gram altın ve Brent petrol cinsinden karşılığı (haftalık seri 2022'den).
  potansiyel    BIST 100 hisselerinde, en az 3 aracı kurumun kapsadığı hisseler için hedef fiyat medyanının güncel fiyata göre potansiyeli.
  tavan-taban   Günlük yükselen, düşen, tavan ve taban hisse sayıları.
  surpriz       Son bilanço döneminde beklentiyi aşan ve kaçıran şirketler.
  simit-menemen Simit ve Menemen Endeksi: aynı sepetin aylık bedeli (kaynaklı derleme).
  maas-kac      Asgari ücretle kaç iPhone, kaç PS5 (resmî ve perakende TL fiyatından, kaynaklı derleme).

Kullanım: python3 gostergeler.py <kök> --borsa <borsa-veri dizini> --dunya <dunya-veri dizini>
"""
import datetime, glob, json, os, statistics, sys

TR = datetime.timezone(datetime.timedelta(hours=3))
# Net asgari ücret (TL, aylık), ÇSGB; yürürlük tarihine göre
ASGARI = [('2022-01-01', 5500.35), ('2022-07-01', 6471.55), ('2023-01-01', 8506.80), ('2023-07-01', 11402.32),
          ('2024-01-01', 17002.12), ('2025-01-01', 22104.67), ('2026-01-01', 28075.50)]
UYARI = 'Resmî borsa endeksi ya da finansal ürün değildir; Endeks24 derlemesidir. Yatırım tavsiyesi değildir.'


def log(*a):
    print(*a, flush=True)


def oku(yol, varsayilan=None):
    try:
        return json.load(open(yol, encoding='utf-8'))
    except Exception:
        return varsayilan


def asgari(tarih):
    v = None
    for t, x in ASGARI:
        if tarih >= t:
            v = x
    return v


def r(x, n=2):
    return None if x is None else round(float(x), n)


def yuzde(a, b):
    return None if not b else round((a / b - 1) * 100, 1)


def tr(x, n=0):
    """Türkçe sayı biçimi: 28075.5 -> 28.075,50"""
    return f'{x:,.{n}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def gun_adi(t):
    ay = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
    y, m, d = t.split('-')
    return f'{int(d)} {ay[int(m) - 1]} {y}'


# ---------- Alım gücü ----------
def alim_gucu(kok, dunya):
    z = oku(f'{kok}/zaman-makinesi/seri.json')
    if not z:
        return None
    g, usd, eur, alt = z['g'], z['usd'], z['eur'], z['alt']
    bas = '2022-01-01'
    idx = [i for i, t in enumerate(g) if t >= bas and usd[i] and alt[i] and eur[i]]
    gg = [g[i] for i in idx]
    dolar = [r(asgari(g[i]) / usd[i], 1) for i in idx]
    altin = [r(asgari(g[i]) / alt[i], 2) for i in idx]
    euro = [r(asgari(g[i]) / eur[i], 1) for i in idx]
    son = idx[-1]
    tarih = g[son]
    maas = asgari(tarih)
    # Brent (dunya-veri): dolar/varil
    brent = None
    d = oku(f'{dunya}/dunya/ozet.json') if dunya else None
    for grp in (d or {}).get('gruplar', []):
        for s in grp.get('satirlar', []):
            if s.get('sembol') == 'BZ=F':
                brent = s.get('son')
    varil = r(maas / usd[son] / brent, 2) if brent else None

    def yilbasi(seri):
        for i, t in enumerate(gg):
            if t >= tarih[:4] + '-01-01':
                return seri[i]
        return None

    def yilonce(seri):
        hedef = str(int(tarih[:4]) - 1) + tarih[4:]
        for i, t in enumerate(gg):
            if t >= hedef:
                return seri[i]
        return None
    yb_d, yb_a, yb_e = yilbasi(dolar), yilbasi(altin), yilbasi(euro)
    kartlar = [
        {'k': 'Net asgari ücret', 'd': tr(maas, 2) + ' TL', 'a': 'ÇSGB, 1 Ocak 2026 itibarıyla'},
        {'k': 'Dolar cinsinden', 'd': tr(dolar[-1]) + ' dolar', 'y': yuzde(dolar[-1], yb_d), 'ya': 'yıl başına göre', 'y2': yuzde(dolar[-1], yilonce(dolar)), 'ya2': 'bir yıl öncesine göre'},
        {'k': 'Gram altın cinsinden', 'd': tr(altin[-1], 2) + ' gram', 'y': yuzde(altin[-1], yb_a), 'ya': 'yıl başına göre', 'y2': yuzde(altin[-1], yilonce(altin)), 'ya2': 'bir yıl öncesine göre'},
        {'k': 'Euro cinsinden', 'd': tr(euro[-1]) + ' euro', 'y': yuzde(euro[-1], yb_e), 'ya': 'yıl başına göre'},
    ]
    if varil:
        kartlar.append({'k': 'Brent petrol cinsinden', 'd': tr(varil, 2) + ' varil', 'a': 'Güncel Brent vadeli fiyatından'})
    cumleler = [f'{gun_adi(tarih)} itibarıyla net asgari ücret {tr(maas, 2)} TL; bu tutar {tr(dolar[-1])} dolara ve {tr(altin[-1], 2)} gram altına denk geliyor.']
    if yb_d and yb_a:
        yd, ya_ = yuzde(dolar[-1], yb_d), yuzde(altin[-1], yb_a)
        cumleler.append(f'Yıl başına göre asgari ücretin dolar karşılığı yüzde {tr(abs(yd), 1)} ' + ('arttı' if yd > 0 else 'azaldı') + f', gram altın karşılığı yüzde {tr(abs(ya_), 1)} ' + ('arttı.' if ya_ > 0 else 'azaldı.'))
    return {
        'id': 'alim-gucu', 'ad': 'Endeks24 Alım Gücü Endeksi', 'kisa': 'Alım Gücü', 'tarih': tarih,
        'baslik': 'Asgari ücret kaç dolar, kaç gram altın, kaç varil petrol?',
        'lead': 'Net asgari ücretin dolar, euro, gram altın ve Brent petrol karşılığı. Her haftanın son kapanışıyla, 2022 başından bugüne.',
        'kartlar': kartlar, 'cumleler': cumleler,
        'seri': {'g': gg, 'seriler': [{'ad': 'Dolar karşılığı', 'birim': 'dolar', 'd': dolar}, {'ad': 'Gram altın karşılığı', 'birim': 'gram', 'd': altin}, {'ad': 'Euro karşılığı', 'birim': 'euro', 'd': euro}]},
        'yontem': ['Net asgari ücret ÇSGB duyurularındaki aylık net tutardır; her ücret zammında yürürlük tarihinden itibaren yeni tutar kullanılır (Ocak 2022: 5.500,35, Temmuz 2022: 6.471,55, Ocak 2023: 8.506,80, Temmuz 2023: 11.402,32, Ocak 2024: 17.002,12, Ocak 2025: 22.104,67, Ocak 2026: 28.075,50 TL).',
                   'Seri her haftanın son işlem günü kapanışıyla hesaplanır: net asgari ücret bölü o günkü dolar, euro ve gram altın kuru. Brent kartı güncel vadeli fiyat ve güncel dolar kuruyla hesaplanır.',
                   'Maaşın alım gücü, ücret zammı günü yükselir, kurlar arttıkça aşağı iner; bu yüzden seri testere dişi görünür.'],
        'kaynak': 'Kaynak: ÇSGB, TCMB ve piyasa verileri; Endeks24 hesaplaması'}


# ---------- Hedef fiyat potansiyeli ----------
def potansiyel(kok, borsa, onceki):
    oz = oku(f'{borsa}/borsa/ozet.json')
    if not oz:
        return None
    xu = {t['k'] for t in oz['tablo'] if 'XU100' in (t.get('e') or [])}
    satir = []
    for k in sorted(xu):
        h = oku(f'{borsa}/borsa/hisse/{k}.json')
        if not h or not h.get('son'):
            continue
        # Yalnızca son 90 günde yayımlanmış hedefler: eski raporlar bugünkü fiyatı yansıtmaz
        sinir = (datetime.date.fromisoformat(oz['tarih']) - datetime.timedelta(days=90)).isoformat()
        taze = [z['h'] for z in (h.get('hedef') or []) if z.get('h') and (z.get('t') or '') >= sinir]
        if len(taze) < 3:
            continue
        med_h = statistics.median(taze)
        satir.append({'k': k, 'ad': (h.get('ad') or k).split(' - ')[0], 'son': h['son'], 'hedef': round(med_h, 2), 'n': len(taze), 'p': round((med_h / h['son'] - 1) * 100, 1)})
    if len(satir) < 10:
        log('potansiyel: kapsam az', len(satir))
        return onceki
    pl = [x['p'] for x in satir]
    tarih = oz.get('tarih')
    med = round(statistics.median(pl), 1)
    ort = round(sum(pl) / len(pl), 1)
    seri = (onceki or {}).get('seri') or {'g': [], 'medyan': [], 'kapsam': []}
    if tarih in seri['g']:
        i = seri['g'].index(tarih)
        seri['medyan'][i], seri['kapsam'][i] = med, len(satir)
    else:
        seri['g'].append(tarih); seri['medyan'].append(med); seri['kapsam'].append(len(satir))
    sirali = sorted(satir, key=lambda x: -x['p'])
    return {
        'id': 'potansiyel', 'ad': 'Endeks24 Hedef Fiyat Potansiyeli', 'kisa': 'Hedef Fiyat Potansiyeli', 'tarih': tarih,
        'baslik': 'Aracı kurumlar BIST 100 hisselerinde ne kadar yükseliş potansiyeli görüyor?',
        'lead': 'BIST 100 hisselerinden son 90 günde en az üç aracı kurumun hedef fiyat verdiği hisselerde, hedef fiyat medyanının güncel fiyata göre farkı.',
        'kartlar': [{'k': 'Medyan potansiyel', 'd': ('%' + str(med).replace('.', ',')), 'a': f'{len(satir)} hisse, hedef fiyat medyanına göre'},
                    {'k': 'Ortalama potansiyel', 'd': ('%' + str(ort).replace('.', ',')), 'a': 'eşit ağırlıklı'},
                    {'k': 'Potansiyeli pozitif', 'd': f'{sum(1 for p in pl if p > 0)} / {len(satir)}', 'a': 'hedef fiyatı güncel fiyatın üstünde olan hisse'}],
        'cumleler': [f'{gun_adi(tarih)} itibarıyla son 90 günde en az üç aracı kurumun hedef fiyat verdiği {len(satir)} BIST 100 hissesinde hedef fiyat medyanı güncel fiyatın ortalama yüzde {str(med).replace(".", ",")} üzerinde.'],
        'seri': {'g': seri['g'], 'seriler': [{'ad': 'Medyan potansiyel', 'birim': '%', 'd': seri['medyan']}], 'kapsam': seri['kapsam']},
        'tablo': {'kolonlar': ['Hisse', 'Güncel fiyat (TL)', 'Hedef fiyat medyanı (TL)', 'Potansiyel (%)', 'Kurum sayısı'],
                  'basliklar': ['En yüksek potansiyel', 'En düşük potansiyel'],
                  'satirlar': [sirali[:8], sirali[-8:][::-1]]},
        'yontem': ['Evren BIST 100 hisseleridir. Hedef fiyat, aracı kurumların son 90 günde yayımladığı raporlardaki hedeflerin medyanıdır; yalnızca bu sürede en az 3 kurumun hedef verdiği hisseler alınır.',
                   'Potansiyel = hedef fiyat medyanı bölü son kapanış eksi 1. Raporların tarihleri farklıdır; son haftalarda fiyatlar sert hareket ettiyse hedefler eskimiş olabilir.',
                   'Seri bu göstergenin ilk hesaplandığı günden itibaren her işlem günü eklenerek oluşur; kapsamdaki hisse sayısı gün gün değişebilir.'],
        'kaynak': 'Kaynak: aracı kurum raporları (Fintables), Borsa İstanbul; Endeks24 hesaplaması'}


# ---------- Tavan taban dengesi ----------
def tavan_taban(kok, borsa, onceki):
    oz = oku(f'{borsa}/borsa/ozet.json')
    if not oz or not oz.get('n'):
        return onceki
    n = int(oz['n']); yuk = int(oz['yuk']); dus = int(oz['dus']); tavan = int(oz['tavan']); taban = int(oz['taban'])
    tarih = oz['tarih']
    seri = (onceki or {}).get('seri') or {'g': [], 'yuk': [], 'dus': [], 'tavan': [], 'taban': []}
    kay = {'yuk': yuk, 'dus': dus, 'tavan': tavan, 'taban': taban}
    if tarih in seri['g']:
        i = seri['g'].index(tarih)
        for k, v in kay.items():
            seri[k][i] = v
    else:
        seri['g'].append(tarih)
        for k, v in kay.items():
            seri[k].append(v)
    oran = round(yuk / n * 100, 1)
    return {
        'id': 'tavan-taban', 'ad': 'Endeks24 Tavan Taban Dengesi', 'kisa': 'Tavan Taban Dengesi', 'tarih': tarih,
        'baslik': 'Borsada kaç hisse yükseldi, kaç hisse düştü, kaç tavan, kaç taban?',
        'lead': 'Borsa İstanbul hisselerinde günlük yükselen, düşen, tavan ve taban sayıları. Bir günde piyasanın ne kadarının hangi yöne gittiğini gösterir.',
        'kartlar': [{'k': 'Yükselen hisse', 'd': str(yuk), 'a': f'{n} hisse içinde yüzde {str(oran).replace(".", ",")}'},
                    {'k': 'Düşen hisse', 'd': str(dus), 'a': f'yüzde {str(round(dus / n * 100, 1)).replace(".", ",")}'},
                    {'k': 'Tavan', 'd': str(tavan), 'a': 'günlük fiyat sınırının üstünde kapanış'},
                    {'k': 'Taban', 'd': str(taban), 'a': 'günlük fiyat sınırının altında kapanış'}],
        'cumleler': [f'{gun_adi(tarih)} kapanışında {n} hissenin {yuk} tanesi yükseldi, {dus} tanesi düştü; {tavan} hisse tavan, {taban} hisse taban oldu.'],
        'seri': {'g': seri['g'], 'yuk': seri['yuk'], 'dus': seri['dus'], 'tavan': seri['tavan'], 'taban': seri['taban'],
                 'seriler': [{'ad': 'Yükselen', 'birim': 'hisse', 'd': seri['yuk']}, {'ad': 'Düşen', 'birim': 'hisse', 'd': seri['dus']}]},
        'yontem': ['Yükselen ve düşen hisse sayısı, Borsa İstanbul\'da işlem gören hisselerde önceki kapanışa göre değişimin pozitif ya da negatif olmasıdır; değişmeyenler iki gruba da girmez.',
                   'Tavan ve taban, hissenin o gün günlük fiyat sınırının en üstünde ya da en altında kapanmasıdır. Seri her işlem günü akşamı eklenerek büyür.'],
        'kaynak': 'Kaynak: Borsa İstanbul; Endeks24 hesaplaması'}


# ---------- Bilanço sürprizi ----------
def surpriz(kok):
    b = oku(f'{kok}/analiz/bilanco-surpriz.json')
    if not b or not b.get('kayitlar'):
        return None
    kay = list(b['kayitlar'].values())
    son = max((x['yil'], x['ay']) for x in kay)
    d = [x for x in kay if (x['yil'], x['ay']) == son and x.get('gercek') is not None and x.get('tahmin_medyan') is not None]
    if not d:
        return None
    asan = [x for x in d if x['gercek'] > x['tahmin_medyan']]
    kacan = [x for x in d if x['gercek'] < x['tahmin_medyan']]
    ceyrek = {3: '1. çeyrek', 6: '2. çeyrek', 9: '3. çeyrek', 12: '4. çeyrek'}.get(son[1], f'{son[1]}. ay')
    donem = f'{son[0]} {ceyrek}'
    satir = sorted(d, key=lambda x: -(x['gercek'] - x['tahmin_medyan']) / (abs(x['tahmin_medyan']) or 1))
    tep = [x['tepki']['g1'] for x in d if x.get('tepki') and x['tepki'].get('g1') is not None]
    kart = [{'k': 'Beklentiyi aşan', 'd': f'{len(asan)} / {len(d)}', 'a': 'gerçek net kâr, aracı kurum medyanının üstünde'},
            {'k': 'Beklentinin altında', 'd': f'{len(kacan)} / {len(d)}', 'a': 'gerçek net kâr, medyanın altında'}]
    if tep:
        kart.append({'k': 'Yayın sonrası ilk gün', 'd': ('%' + str(round(statistics.median(tep), 1)).replace('.', ',')), 'a': 'hisse fiyatı medyan tepkisi'})
    return {
        'id': 'surpriz', 'ad': 'Endeks24 Bilanço Sürprizi', 'kisa': 'Bilanço Sürprizi', 'tarih': b.get('guncelleme'),
        'baslik': f'{donem} bilançolarında kim beklentiyi aştı, kim kaçırdı?',
        'lead': 'Şirketin açıkladığı çeyreklik net kârı, bilanço yayımından önceki aracı kurum tahmin medyanıyla karşılaştırılır.',
        'kartlar': kart,
        'cumleler': [f'{donem} döneminde bilançosunu açıklayan ve tahmini bulunan {len(d)} şirketin {len(asan)} tanesi net kârda aracı kurum beklentisini aştı, {len(kacan)} tanesi beklentinin altında kaldı.'],
        'tablo': {'kolonlar': ['Şirket', 'Tahmin medyanı (mn TL)', 'Gerçekleşen (mn TL)', 'Sürpriz (%)', 'Yayın sonrası ilk gün (%)'],
                  'satirlar': [[{'k': x['kod'], 'tah': round(x['tahmin_medyan'] / 1e6, 1), 'ger': round(x['gercek'] / 1e6, 1), 's': x.get('surpriz'),
                                 't': (x.get('tepki') or {}).get('g1'), 'n': x.get('kurum')} for x in satir]]},
        'yontem': ['Tahmin, aracı kurumların bilanço yayımından önce alınan son çeyreklik net kâr tahminlerinin medyanıdır; arşiv tarihli kopyalara dayanır ve 25 Ekim 2026\'dan itibaren tutulmaktadır.',
                   'Gerçekleşen, ana ortaklık payına düşen çeyreklik net kârdır. Sürpriz yüzdesi, tahmin sıfıra yakınsa ya da negatifse yanıltıcı olabilir; sıralama gerçekleşen ile tahmin farkının tahmin büyüklüğüne oranına göredir.',
                   'Küçük örneklemdir: bilanço sezonu ilerledikçe şirket sayısı artar.'],
        'kaynak': 'Kaynak: KAP bilançoları, aracı kurum tahminleri (Fintables); Endeks24 hesaplaması'}


# ---------- Elle derlenen göstergeler ----------
def girdi_simit(kok, usd_son=None):
    ad = {'id': 'simit-menemen', 'ad': 'Endeks24 Simit ve Menemen Endeksi', 'kisa': 'Simit ve Menemen Endeksi'}
    g = oku(f'{kok}/endeksler/girdi/simit-menemen.json')
    hazir = dict(ad, durum='hazirlaniyor', lead='Bir simit ile bir sade menemenden oluşan sepetin aylık bedeli. Aynı işletmelerden, her ay, kaynaklı derlemeyle. İlk derleme hazırlanıyor.')
    if not g or not g.get('donemler'):
        return hazir
    seri = []
    for d in sorted(g['donemler']):
        x = g['donemler'][d]
        simit = [i['fiyat'] for i in x.get('simit', [])]
        men = [i['fiyat'] for i in x.get('menemen', [])]
        if len(simit) < 3 or len(men) < 3:
            continue
        s, m = statistics.median(simit), statistics.median(men)
        seri.append({'d': d, 'tarih': x.get('tarih') or d + '-01', 'simit': s, 'menemen': m, 'sepet': s + m, 'x': x})
    if not seri:
        return hazir
    ilk, son = seri[0], seri[-1]
    maas = asgari(son['tarih'])
    aylik = son['sepet'] * 30
    dolar = usd_son
    satirlar = []
    for urun, anahtar in (('Simit', 'simit'), ('Sade menemen', 'menemen')):
        for i in sorted(son['x'].get(anahtar, []), key=lambda z: z['fiyat']):
            satirlar.append({'urun': urun, 'isletme': i['isletme'], 'fiyat': i['fiyat'], 'tarih': i.get('tarih'), 'url': i.get('kaynak')})
    kart = [{'k': 'Sepet (1 simit + 1 menemen)', 'd': tr(son['sepet']) + ' TL', 'a': f"simit {tr(son['simit'])} TL + menemen {tr(son['menemen'])} TL, medyan"},
            {'k': 'Net asgari ücrete oranı', 'd': '%' + tr(son['sepet'] / maas * 100, 1), 'a': 'tek bir sabahın sepeti'},
            {'k': 'Her sabah, 30 gün', 'd': tr(aylik) + ' TL', 'a': f"net asgari ücretin %{tr(aylik / maas * 100, 1)}'ü"}]
    if dolar:
        kart.append({'k': 'Dolar karşılığı', 'd': tr(son['sepet'] / dolar, 2) + ' dolar', 'a': f"aylık tutar {tr(aylik / dolar, 2)} dolar"})
    kart.append({'k': 'Maaşla alınabilecek', 'd': f"{int(maas // son['simit'])} simit", 'a': f"ya da {int(maas // son['menemen'])} sade menemen"})
    pahali = sum(max(i['fiyat'] for i in son['x'][k]) for k in ('simit', 'menemen'))
    ucuz = sum(min(i['fiyat'] for i in son['x'][k]) for k in ('simit', 'menemen'))
    fark = ''
    if len(seri) > 1:
        once = seri[-2]
        de = (son['sepet'] / once['sepet'] - 1) * 100
        fark = f" Sepet bir önceki derlemeye göre yüzde {tr(abs(de), 1)} {'arttı' if de > 0 else 'azaldı'}."
    else:
        fark = ' Bu ilk derleme olduğu için aylık değişim sonraki aylarda bu sayfada izlenecek.'
    cumle = [f"{gun_adi(son['tarih'])} derlemesine göre bir simit ile bir sade menemenden oluşan kahvaltı sepeti {tr(son['sepet'])} TL: simit {tr(son['simit'])} TL, menemen {tr(son['menemen'])} TL.{fark}",
             f"Bu sepeti 30 gün boyunca her sabah alan biri {tr(aylik)} TL öder; bu, {tr(maas, 2)} TL olan net asgari ücretin yüzde {tr(aylik / maas * 100, 1)}'ü demek. Aynı maaşla {int(maas // son['simit'])} simit ya da {int(maas // son['menemen'])} sade menemen alınabiliyor.",
             f"İşletmeler arasında fark büyük: en ucuz üç işletmeyle sepet {tr(ucuz)} TL (maaşın yüzde {tr(ucuz * 30 / maas * 100, 1)}'ü), en pahalı üç işletmeyle {tr(pahali)} TL (yüzde {tr(pahali * 30 / maas * 100, 1)}'ü) tutuyor. Fiyatlar restoran ve kafe menü fiyatlarıdır, paket servis fiyatları farklı olabilir."]
    out = dict(ad, tarih=son['tarih'], baslik='Bir simit ve bir menemen kaç lira? Her sabah alınırsa maaşın kaçı gider?',
               lead='Aynı sepetin, aynı üç işletmeden menü fiyatıyla hesabı. Net asgari ücrete oranı ve aylık tutarı.',
               kartlar=kart, cumleler=cumle, tablo={'kolonlar': ['Ürün', 'İşletme', 'Menü fiyatı (TL)', 'Menü tarihi', 'Kaynak'], 'satirlar': [satirlar]},
               yontem=g.get('yontem', []), kaynak=g.get('kaynak', 'Kaynak: işletme menü fiyatları; Endeks24 derlemesi'), durum='canli')
    if len(seri) > 1:
        out['seri'] = {'g': [x['tarih'] for x in seri], 'seriler': [{'ad': 'Sepet bedeli', 'birim': 'TL', 'd': [x['sepet'] for x in seri]},
                                                                   {'ad': 'Endeks (ilk ay = 100)', 'birim': '', 'd': [round(x['sepet'] / ilk['sepet'] * 100, 1) for x in seri]}]}
    return out


def girdi_maas(kok, alim):
    g = oku(f'{kok}/endeksler/girdi/maas-kac.json')
    adlar = {'id': 'maas-kac', 'ad': 'Endeks24 Maaş Karşılığı: kaç iPhone, kaç PS5', 'kisa': 'Maaş Karşılığı'}
    if not g or not g.get('urunler') or not alim:
        return dict(adlar, durum='hazirlaniyor', lead='Net asgari ücretle kaç iPhone ve kaç PlayStation 5 alınabildiği. Resmî TL fiyatları kaynaklı derleniyor; ilk derleme hazırlanıyor.')
    maas = None
    for k in alim['kartlar']:
        if k['k'] == 'Net asgari ücret':
            maas = asgari(alim['tarih'])
    satir = []
    for u in g['urunler']:
        satir.append({'ad': u['ad'], 'fiyat': u['fiyat'], 'maas': round(u['fiyat'] / maas, 2), 'tarih': u.get('tarih'), 'kaynak': u.get('kaynak')})
    return dict(adlar, tarih=g.get('tarih'), durum='canli', baslik='Asgari ücretle kaç iPhone alınır?', lead='Resmî TL fiyatının net asgari ücrete oranı.',
                tablo={'kolonlar': ['Ürün', 'Fiyat (TL)', 'Kaç asgari ücret', 'Fiyat tarihi', 'Kaynak'], 'satirlar': [satir]},
                yontem=g.get('yontem', []), kaynak=g.get('kaynak', 'Kaynak: üretici resmî Türkiye fiyatı; Endeks24 derlemesi'))


def main():
    kok = sys.argv[1]
    arg = lambda a: sys.argv[sys.argv.index(a) + 1] if a in sys.argv else None
    borsa, dunya = arg('--borsa'), arg('--dunya')
    onceki = oku(f'{kok}/endeksler/gostergeler.json', {}) or {}
    ob = {x['id']: x for x in onceki.get('gostergeler', [])}
    cikti = []
    alim = alim_gucu(kok, dunya)
    for ad, f in (('alim-gucu', lambda: alim), ('potansiyel', lambda: potansiyel(kok, borsa, ob.get('potansiyel')) if borsa else ob.get('potansiyel')),
                  ('tavan-taban', lambda: tavan_taban(kok, borsa, ob.get('tavan-taban')) if borsa else ob.get('tavan-taban')), ('surpriz', lambda: surpriz(kok)),
                  ('simit-menemen', lambda: girdi_simit(kok, (oku(f'{kok}/zaman-makinesi/seri.json') or {}).get('usd', [None])[-1])), ('maas-kac', lambda: girdi_maas(kok, alim))):
        try:
            x = f()
        except Exception as e:
            log('UYARI', ad, repr(e)[:120])
            x = ob.get(ad)
        if x:
            x.setdefault('durum', 'canli')
            x['uyari'] = UYARI
            x['sayfa'] = 'https://www.endeks24.com/endeks24-' + {'alim-gucu': 'alim-gucu', 'potansiyel': 'hedef-fiyat-potansiyeli', 'tavan-taban': 'tavan-taban-dengesi',
                                                                  'surpriz': 'bilanco-surpriz', 'simit-menemen': 'simit-ve-menemen-endeksi', 'maas-kac': 'maas-karsiligi'}[ad]
            cikti.append(x)
            log('tamam', ad, x.get('tarih'), x['durum'])
    if len(cikti) < 3:
        log('çok az gösterge, dosya yazılmadı')
        sys.exit(1)
    os.makedirs(f'{kok}/endeksler', exist_ok=True)
    json.dump({'guncelleme': datetime.datetime.now(TR).strftime('%Y-%m-%dT%H:%M+03:00'), 'gostergeler': cikti}, open(f'{kok}/endeksler/gostergeler.json', 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
