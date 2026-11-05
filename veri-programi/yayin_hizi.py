#!/usr/bin/env python3
"""Yayın hızı ölçümü (5.11.2026): haber yayın saatiyle haber sitemap'ine ve RSS'e düştüğü ilk görülme saati arasındaki süreyi ve sitemap adresinin 200 verip vermediğini kaydeder.
15 dakikada bir çalışır, bu yüzden ölçüm çözünürlüğü yaklaşık 15 dakikadır. Çıktı: <cikti>/yayin-hizi.json. Yapay zeka çağrısı yoktur."""
import json, os, re, sys, datetime, urllib.request, urllib.error, statistics
KOK = 'https://www.endeks24.com'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; Endeks24-yayin-hizi)'}
TZ = datetime.timezone(datetime.timedelta(hours=3))


def al(yol, yontem='GET'):
    r = urllib.request.Request(KOK + yol, headers=UA, method=yontem)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, (x.read().decode('utf8', 'ignore') if yontem == 'GET' else '')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return 0, ''


def main():
    cikti = sys.argv[1]
    simdi = datetime.datetime.now(TZ)
    yol = os.path.join(cikti, 'yayin-hizi.json')
    try:
        d = json.load(open(yol))
    except Exception:
        d = {'kayit': {}}
    kayit = d['kayit']
    kod, sm = al('/sitemap-news.xml')
    haber = {}
    if kod == 200:
        for u in re.finditer(r'<url>(.*?)</url>', sm, re.S):
            b = u.group(1)
            l = re.search(r'<loc>([^<]+)</loc>', b)
            p = re.search(r'<news:publication_date>([^<]+)</news:publication_date>', b)
            if l and p:
                haber[l.group(1).replace(KOK, '')] = p.group(1)
    kod2, rss = al('/rss')
    rssli = set(re.findall(r'<link>https://www\.endeks24\.com([^<]+)</link>', rss)) if kod2 == 200 else set()
    for y, yt in haber.items():
        try:
            yay = datetime.datetime.fromisoformat(yt)
        except Exception:
            continue
        if y not in kayit:
            if (simdi - yay).total_seconds() > 3 * 3600:
                continue  # ilk çalışmada eski haberler ölçüme girmez
            kayit[y] = {'yayin': yt, 'sitemap_gorulen': simdi.isoformat(timespec='minutes'),
                        'sitemap_dk': round((simdi - yay).total_seconds() / 60), 'durum': al(y, 'HEAD')[0]}
        k = kayit[y]
        if 'rss_gorulen' not in k and y in rssli:
            k['rss_gorulen'] = simdi.isoformat(timespec='minutes')
            k['rss_dk'] = round((simdi - yay).total_seconds() / 60)
        if k.get('durum') != 200:
            k['durum'] = al(y, 'HEAD')[0]
    sinir = (simdi - datetime.timedelta(days=7)).isoformat()
    d['kayit'] = {y: k for y, k in kayit.items() if k['yayin'] >= sinir}
    sd = [k['sitemap_dk'] for k in d['kayit'].values() if k['sitemap_dk'] >= 0]
    rd = [k['rss_dk'] for k in d['kayit'].values() if k.get('rss_dk', -1) >= 0]
    d['ozet'] = {'haber': len(d['kayit']), 'sitemap_medyan_dk': statistics.median(sd) if sd else None, 'sitemap_en_uzun_dk': max(sd) if sd else None,
                 'rss_medyan_dk': statistics.median(rd) if rd else None, 'adresi_404_olan': [y for y, k in d['kayit'].items() if k.get('durum') in (404, 410)],
                 'guncelleme': simdi.isoformat(timespec='minutes')}
    json.dump(d, open(yol, 'w'), ensure_ascii=False, indent=1)
    print('yayın hızı:', d['ozet'])


if __name__ == '__main__':
    main()
