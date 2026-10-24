"""Masa aracı: KAP haberine "Geçmişte benzer kararlardan sonra" kutusunu üretir (fiyat hafızası, 24.10.2026).

Kullanım: python3 hafiza_etiket.py --tur bedelsiz --hisse VSNMD [--kap 1642442] [--dosya hafiza.json]
Türler: bedelsiz, temettu, bedelli. Kutu, haberin gövdesinin sonuna, kapanış </div> öncesine yapıştırılır.
Veri: canlı hafiza.json (endeks24-v5 main kökü, ayda bir otomatik yenilenir). Yeterli olay yoksa kutu eklenmez.
Kutu düz HTML'dir (Google ve yapay zeka botları JavaScript çalıştırmadan okur); sayıları elle değiştirmeyin.
"""
import html, json, sys, urllib.request

CANLI = 'https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/hafiza.json'
AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']
EN_AZ_HISSE = 5


def tr(x, n=1):
    return f'{abs(x):.{n}f}'.replace('.', ',')


def tarih(s):
    g = s.split('-')
    return f'{int(g[2])} {AY[int(g[1]) - 1]} {g[0]}'


def yon(x):
    return 'yükseldi' if x > 0 else ('düştü' if x < 0 else 'değişmedi')


def fark(x):
    if abs(x) < 0.05:
        return 'BIST 100 endeksiyle aynı düzeyde kaldı'
    return f'BIST 100 endeksinin yüzde {tr(x)} {"üzerinde" if x > 0 else "altında"} kaldı'


def cumle(o, ne, kapsam, pencere, gun, ozne='hisseler'):
    return (f'{tarih(pencere[0])} ile {tarih(pencere[1])} arasında {kapsam} açıklanan {o["n"]} {ne} sonrasındaki {gun} işlem gününde '
            f'{ozne} medyan yüzde {tr(o["medyan"])} {yon(o["medyan"])} ve {fark(o["fazla_medyan"])}. '
            f'Getirisi pozitif olan olayların oranı yüzde {o["pozitif"]}, endeksin üzerinde kalan olayların oranı yüzde {o["fazla_pozitif"]}.')


def kutu(h, tur, hisse, kap=None):
    t = h['tur'][tur]
    en_az = h.get('en_az', 10)
    gun = h['gun']
    bist = hisse in set(h.get('bist100', []))
    secim = None
    if bist and t['bist100'] and t['bist100']['n'] >= en_az:
        secim = (t['bist100'], 'bugünkü BIST 100 şirketlerinde')
    elif t['tum'] and t['tum']['n'] >= en_az:
        secim = (t['tum'], "Borsa İstanbul'da")
    if not secim:
        return None
    satirlar = [f'<p class="e24-h-ozet">{html.escape(cumle(secim[0], t["etiket"], secim[1], h["pencere"], gun), quote=False)}</p>']
    o = t['hisse'].get(hisse)
    if o and o['n'] >= EN_AZ_HISSE:
        satirlar.append(f'<p class="e24-h-hisse"><strong>{html.escape(hisse)}:</strong> '
                        f'{html.escape(cumle(o, t["etiket"], f"{hisse} için", h["pencere"], gun, "hisse"), quote=False)}</p>')
    satirlar.append('<p class="e24-h-not">Geçmiş fiyat hareketi gelecekteki getiriyi göstermez. Aynı gün açıklanan bilanço ya da başka gelişmeler etkiyi '
                    'karıştırabilir; kararın fiyata neden olduğu iddia edilmez. Yatırım tavsiyesi değildir.</p>')
    ol = h['olusturma'][:10].split('-')
    satirlar.append(f'<p class="e24-h-kaynak">Kaynak: KAP bildirimleri, Borsa İstanbul fiyatları; Endeks24 hesaplaması ({int(ol[2])} {AY[int(ol[1]) - 1]} {ol[0]}). '
                    f'Yöntem: karar yayınından sonraki ilk işlem gününden başlayarak {gun} işlem günü, bir önceki kapanışa göre getiri; medyan. '
                    f'Aynı şirketin 60 gün içindeki tekrar bildirimleri sayılmaz.</p>')
    ozel = f' data-hisse="{html.escape(hisse)}"' + (f' data-kap="{kap}"' if kap else '')
    return (f'<div class="e24-hafiza" data-tur="{tur}"{ozel}>\n<h2 class="e24-h-baslik">Geçmişte benzer kararlardan sonra ne oldu?</h2>\n'
            + '\n'.join(satirlar) + '\n</div>')


def main():
    a = sys.argv
    def arg(k, v=None):
        return a[a.index(k) + 1] if k in a else v
    tur, hisse = arg('--tur'), (arg('--hisse') or '').upper()
    if tur not in ('bedelsiz', 'temettu', 'bedelli') or not hisse:
        print(__doc__); sys.exit(1)
    d = arg('--dosya')
    h = json.load(open(d, encoding='utf-8')) if d else json.load(urllib.request.urlopen(CANLI, timeout=20))
    k = kutu(h, tur, hisse, arg('--kap'))
    print(k if k else 'Yeterli geçmiş olay yok: kutu eklenmez.')


if __name__ == '__main__':
    main()
