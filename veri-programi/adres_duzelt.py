#!/usr/bin/env python3
"""Adres düzeltme listesi (4.11.2026). İçerik sistemi yayından sonra haber adresini kısaltınca bazı liste ve kutular eski adrese bağlı kalır ve 404 verir.
Bu betik ana sayfa ve kategori sayfalarındaki haber bağlantılarını başlıklarıyla eşler: aynı başlık iki ayrı adresle geçiyor, biri 404 diğeri 200 veriyorsa
{"/yanlış": "/doğru"} yazar. Yapay zeka çağrısı yoktur. Çıktı: <cikti>/adres-duzelt.json. Kullanım: adres_duzelt.py cikti"""
import json, os, re, sys, html, urllib.request, urllib.error, datetime
KOK = 'https://www.endeks24.com'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; Endeks24-adres-kontrol)'}
SAYFALAR = ['', 'piyasalar', 'bist-100', 'kap', 'gundem', 'halka-arz', 'enerji', 'emlak', 'otomotiv', 'savunma', 'kripto', 'gorus', 'endeks24-ozel']


def al(yol, yontem='GET'):
    r = urllib.request.Request(KOK + yol, headers=UA, method=yontem)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, (x.read().decode('utf8', 'ignore') if yontem == 'GET' else '')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return 0, ''


def norm(t):
    return re.sub(r'\s+', ' ', html.unescape(t or '')).strip().lower()


def main():
    cikti = sys.argv[1]
    baslik = {}
    for s in SAYFALAR:
        kod, g = al('/' + s)
        if kod != 200:
            continue
        for m in re.finditer(r'<a\b[^>]*?href="(/[a-z0-9-]{12,})"[^>]*?title="([^"]{12,})"', g):
            baslik.setdefault(norm(m.group(2)), set()).add(m.group(1))
        for m in re.finditer(r'<a\b[^>]*?title="([^"]{12,})"[^>]*?href="(/[a-z0-9-]{12,})"', g):
            baslik.setdefault(norm(m.group(1)), set()).add(m.group(2))
    yol = os.path.join(cikti, 'adres-duzelt.json')
    onceki = {}
    try:
        onceki = json.load(open(yol)).get('harita', {})
    except Exception:
        pass
    durum = {}

    def dk(y):
        if y not in durum:
            durum[y] = al(y, 'HEAD')[0]
        return durum[y]
    harita = {}
    for t, h in baslik.items():
        if len(h) < 2:
            continue
        iyi = [y for y in h if dk(y) == 200]
        kotu = [y for y in h if dk(y) in (404, 410)]
        if iyi and kotu:
            for k in kotu:
                harita[k] = sorted(iyi)[0]
    # önceki kayıtlar yalnız hâlâ 404 ve hedefi 200 ise korunur
    for k, v in onceki.items():
        if k not in harita and dk(k) in (404, 410) and dk(v) == 200:
            harita[k] = v
    json.dump({'guncelleme': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime('%Y-%m-%dT%H:%M+03:00'), 'harita': harita}, open(yol, 'w'), ensure_ascii=False, indent=1)
    print('adres düzeltme:', len(harita), 'kayıt')


if __name__ == '__main__':
    main()
