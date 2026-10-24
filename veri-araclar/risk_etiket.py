"""Masa aracı: haber metninden kelebek etkisi etiketlerini önerir ve gömülecek işaretlemeyi yazar.

Kullanım: python3 risk_etiket.py haber.txt   (ya da metni standart girdiden verin)
Çıktı: eşleşen etiketler (anahtar kelimeleriyle), o etiketlerde eşleşmesi olan şirketler ve habere eklenecek işaretleme.
Öneri yalnız anahtar kelime eşleşmesidir; hangi etiketlerin haberin gerçek konusu olduğuna masa karar verir (en çok 4).
Eşleşen şirket yoksa modül eklenmez.
"""
import os, sys, json, urllib.request

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEREL = f'{D}/site/risk-matrisi.json'
CANLI = 'https://raw.githubusercontent.com/Endeks24/endeks24-v5/main/risk.json'


def matris():
    """Depoda site/risk-matrisi.json varsa o, yoksa canlı risk.json (masalar aracı tek dosya olarak indirir)."""
    if os.path.exists(YEREL):
        return json.load(open(YEREL, encoding='utf-8'))
    return json.load(urllib.request.urlopen(CANLI, timeout=20))


def kucult(s):
    return s.replace('İ', 'i').replace('I', 'ı').lower()


def main():
    m = matris()
    metin = kucult(open(sys.argv[1], encoding='utf-8').read() if len(sys.argv) > 1 else sys.stdin.read())
    sonuc = []
    for i, v in m['etiketler'].items():
        bulunan = [k for k in v['anahtar'] if kucult(k) in metin]
        if bulunan:
            sonuc.append((len(bulunan), i, bulunan))
    sonuc.sort(key=lambda x: (-x[0], x[1]))
    if not sonuc:
        print('Eşleşen etiket yok: modül eklenmez.'); return
    sec = [i for _, i, _ in sonuc[:4]]
    for n, i, b in sonuc:
        sirk = [k for k, s in m['sirketler'].items() if any(e['id'] == i for e in s['etiketler'])]
        print(f"{'*' if i in sec else ' '} {i} ({m['etiketler'][i]['ad']}): {', '.join(b)} -> şirket: {', '.join(sirk) or 'yok'}")
    eslesen = {k for k, s in m['sirketler'].items() if any(e['id'] in sec for e in s['etiketler'])}
    if not eslesen:
        print('\nSeçilen etiketlerde eşleşen şirket yok: modül eklenmez.'); return
    print(f'\nEşleşen şirket ({len(eslesen)}): {", ".join(sorted(eslesen))}')
    print('\nHabere eklenecek işaretleme (etiketleri haberin gerçek konusuna göre azaltabilirsiniz):\n')
    ad = ', '.join(m['etiketler'][i]['ad'] for i in sec)
    print(f'<div class="e24-duyarli" data-etiket="{";".join(sec)}">\n<p class="e24-d-baslik">Bu gelişmeye duyarlı şirketler</p>\n'
          f'<p class="e24-d-ozet">Eşleşen risk alanları: {ad}.</p>\n</div>')


if __name__ == '__main__':
    main()
