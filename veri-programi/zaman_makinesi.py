"""Endeks24 Zaman makinesi veri üreticisi (26.10.2026). Salt okuma; yapay zeka çağrısı yoktur.
Kullanım: python3 zaman_makinesi.py tani <kök>   EVDS'te mevduat faizi serisini bulur (günlüğe yazar)
          python3 zaman_makinesi.py uret <kök>   <kök>/zaman-makinesi/seri.json yazar
Anahtarlar: FINTABLES (Fintables MCP), EVDS_API_KEY (TCMB EVDS)."""
import json, os, sys, urllib.request

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


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == 'tani':
        tani()
    else:
        sys.exit('uret henüz yok')
