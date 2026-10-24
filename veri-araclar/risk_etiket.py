"""Masa aracı: haber metninden kelebek etkisi etiketlerini önerir ve gömülecek işaretlemeyi yazar.

Kullanım: python3 risk_etiket.py haber.txt [--etiket kizildeniz-rota;brent-petrol]   (ya da metni standart girdiden verin)
--etiket: masanın seçtiği etiketler (en çok 4); verilmezse en çok eşleşen 4 etiket alınır.
Çıktı: eşleşen etiketler (anahtar kelimeleriyle), o etiketlerde eşleşmesi olan şirketler ve habere eklenecek işaretleme.
Öneri yalnız anahtar kelime eşleşmesidir; hangi etiketlerin haberin gerçek konusu olduğuna masa karar verir (en çok 4).
Eşleşen şirket yoksa modül eklenmez.
"""
import os, sys, json, html, urllib.request

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEREL = f'{D}/site/risk-matrisi.json'
CANLI = 'https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/risk.json'


def matris():
    """Depoda site/risk-matrisi.json varsa o, yoksa canlı risk.json (masalar aracı tek dosya olarak indirir)."""
    if os.path.exists(YEREL):
        return json.load(open(YEREL, encoding='utf-8'))
    return json.load(urllib.request.urlopen(CANLI, timeout=20))


AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def tarih_tr(s):
    g = str(s or '').split('-')
    return f'{int(g[2])} {AY[int(g[1]) - 1]} {g[0]}' if len(g) == 3 and all(x.isdigit() for x in g) else str(s or '')


def kucult(s):
    return s.replace('İ', 'i').replace('I', 'ı').lower()


def main():
    m = matris()
    metin = kucult(open(sys.argv[1], encoding='utf-8').read() if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else sys.stdin.read())
    sonuc = []
    for i, v in m['etiketler'].items():
        bulunan = [k for k in v['anahtar'] if kucult(k) in metin]
        if bulunan:
            sonuc.append((len(bulunan), i, bulunan))
    sonuc.sort(key=lambda x: (-x[0], x[1]))
    if not sonuc:
        print('Eşleşen etiket yok: modül eklenmez.'); return
    sec = [i for _, i, _ in sonuc[:4]]
    if '--etiket' in sys.argv:
        sec = [x for x in sys.argv[sys.argv.index('--etiket') + 1].split(';') if x in m['etiketler']][:4]
    for n, i, b in sonuc:
        sirk = [k for k, s in m['sirketler'].items() if any(e['id'] == i for e in s['etiketler'])]
        print(f"{'*' if i in sec else ' '} {i} ({m['etiketler'][i]['ad']}): {', '.join(b)} -> şirket: {', '.join(sirk) or 'yok'}")
    eslesen = {k for k, s in m['sirketler'].items() if any(e['id'] in sec for e in s['etiketler'])}
    if not eslesen:
        print('\nSeçilen etiketlerde eşleşen şirket yok: modül eklenmez.'); return
    print(f'\nEşleşen şirket ({len(eslesen)}): {", ".join(sorted(eslesen))}')
    print('\nHabere eklenecek işaretleme (etiketleri haberin gerçek konusuna göre azaltabilirsiniz):\n')
    print(isaretleme(m, sec))


def isaretleme(m, sec):
    """Haber yayına girerken HTML içinde hazır bulunan statik modül: bot ham kaynakta şirketleri, kaynakları ve KAP bağlantılarını okur.
    Sitenin JS'i çalışınca aynı matristen modülü yeniden çizer (içeriği değiştirir); JS çalışmazsa bu metin kalır.
    Sıralama ve sınır (en çok 8 şirket, şirket başına en çok 2 not) sitedeki kodla aynıdır."""
    e = html.escape
    sat = []
    for kod, s in m['sirketler'].items():
        es = [x for x in s['etiketler'] if x['id'] in sec]
        if es:
            sat.append((kod, s, es))
    sat.sort(key=lambda t: (-len(t[2]), t[0]))
    sat = sat[:8]
    kul = {x['id'] for _, _, es in sat for x in es}
    sec = [i for i in sec if i in kul]
    ad = ', '.join(m['etiketler'][i]['ad'] for i in sec)
    out = [f'<div class="e24-duyarli" data-etiket="{";".join(sec)}">',
           '<h2 class="e24-d-baslik">Bu gelişmeye duyarlı şirketler</h2>',
           f'<p class="e24-d-ozet">Eşleşen risk alanları: {e(ad)}.</p>', '<ul class="e24-d-liste">']
    for kod, s, es in sat:
        notlar = []
        for x in es[:2]:
            k = x['kaynak']
            etk = e(', '.join(filter(None, [k.get('tur'), k.get('tarih')])))
            kap = str(k.get('kap_bildirim') or '')
            kaynak = (f'(<a href="https://www.kap.org.tr/tr/Bildirim/{kap}" target="_blank" rel="noopener">{etk}</a>)'
                      if kap.isdigit() else f'({etk})')
            notlar.append(f'<span class="e24-d-not1"><strong>{e(m["etiketler"][x["id"]]["ad"])}:</strong> {e(x["not"])} {kaynak}</span>')
        out.append(f'<li class="e24-d-item"><span class="e24-d-kod">{e(kod)}</span> <strong class="e24-d-sirket">{e(s["ad"])}</strong> ' + ''.join('<br>' + n for n in notlar) + '</li>')
    out += ['</ul>',
            f'<p class="e24-d-kaynak">Kaynak: şirketlerin faaliyet raporları ve KAP açıklamaları; eşleştirme Endeks24\'ündür ({e(tarih_tr(m.get("guncelleme", "")))}). '
            'Haberin şirkete etkisinin yönü ya da büyüklüğü hakkında yargı içermez, yatırım tavsiyesi değildir.</p>',
            '</div>']
    return '\n'.join(out)


if __name__ == '__main__':
    main()
