"""Endeks24 hisse sayfası profil verisi (26.10.2026). Salt okuma; yapay zeka çağrısı yoktur.
Her hisse için <kök>/profil/<KOD>.json: künye (kurumsal bilgi kartı), ortaklık yapısı, yönetim, iştirakler, finansal özet (son 8 çeyrek ve TTM) ve çarpan girdileri.
Kullanım: python3 hisse_profil.py <kök_klasör> [--sinir N] [--kod A,B]    Anahtar FINTABLES ortam değişkeninde."""
import datetime, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fiyat_gecmisi as fg
import hafiza_hesapla as hh

TR = fg.TR


def log(*a):
    print(*a, flush=True)


def sayi(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def oran_tr(s):
    """'74,2' ya da '25.78' -> float"""
    s = (s or '').strip().replace('%', '')
    if not s or s == '-':
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def ayristir(md):
    """Kurumsal bilgi kartı metni -> {'kv': {anahtar: değer}, 'tablolar': {başlık: [satır sözlükleri]}}"""
    kv, tab, baslik, bolum = {}, {}, '', ''
    sat = md.split('\n')
    i = 0
    while i < len(sat):
        s = sat[i].strip()
        if s.startswith('## '):
            bolum = s[3:].strip(); baslik = bolum
        elif re.match(r'^\*\*[^*]+\*\*$', s):
            baslik = s.strip('*').strip()
        m = re.match(r'^- \*\*([^*]+):\*\*\s*(.*)$', s)
        if m:
            kv[m.group(1).strip()] = m.group(2).strip()
        if s.startswith('|') and i + 1 < len(sat) and re.match(r'^\|\s*-', sat[i + 1].strip()):
            bas = [h.strip() for h in s.strip('|').split('|')]
            satirlar = []
            i += 2
            while i < len(sat) and sat[i].strip().startswith('|'):
                h = [x.strip() for x in sat[i].strip().strip('|').split('|')]
                if len(h) == len(bas):
                    satirlar.append(dict(zip(bas, h)))
                i += 1
            tab.setdefault(baslik, satirlar)
            continue
        i += 1
    return {'kv': kv, 'tablolar': tab}


def il_bul(adres):
    """Adresin sonundan il: virgül ve eğik çizgiyle bölünür, rakamsız ve 3 harften uzun son sözcük (İstanbul, ANKARA gibi) alınır."""
    p = [x.strip() for x in re.split(r'[,/]', adres or '') if x.strip()]
    for x in reversed(p):
        if re.match(r'^[A-Za-zÇĞİÖŞÜçğıöşü\s]{3,}$', x) and not re.search(r'(?i)mah|cad|sok|bulvar|no\b|blok|kat\b|plaza|merkez|iş\s*merkezi', x):
            return x.title().replace('İ', 'İ').replace('I', 'I')
    return ''


def kart(md):
    d = ayristir(md)
    kv, tb = d['kv'], d['tablolar']
    ort = []
    for r in tb.get('Sermayede doğrudan pay sahipleri', []):
        ad, o = r.get('Pay sahibi', ''), oran_tr(r.get('Sermaye oranı'))
        if ad and o is not None and ad.upper() not in ('TOPLAM',):
            ort.append({'ad': ad, 'o': o})
    yk = [{'ad': r.get('Ad Soyad', ''), 'u': r.get('Unvan', ''), 'b': 'Değil' not in (r.get('Bağımsızlık') or '')} for r in tb.get('Yönetim kurulu üyeleri', []) if r.get('Ad Soyad') and r.get('Ad Soyad') != '-']
    gm = ''
    for r in tb.get('Üst yönetim (yönetimde söz sahibi kişiler)', []):
        if (r.get('Görev') or '').upper().startswith('GENEL MÜDÜR') and 'YARDIMCI' not in (r.get('Görev') or '').upper():
            gm = r.get('Ad Soyad', ''); break
    ist = []
    for r in tb.get('İştirakler ve Bağlı Ortaklıklar', []):
        ist.append({'ad': r.get('Şirket', ''), 'i': r.get('İlişki', ''), 'o': oran_tr(r.get('Sermaye payı (%)')), 'f': (r.get('Faaliyet') or '')[:140]})
    ist.sort(key=lambda z: -(z['o'] or 0))
    ilk = ''
    for r in tb.get('Diğer borsa/piyasa kayıtları', []):
        t = (r.get('İlk işlem tarihi') or '')[:10]
        if t and (not ilk or t < ilk):
            ilk = t
    return {'sektor': kv.get('Sektör', ''), 'denetci': kv.get('Bağımsız denetim kuruluşu', ''), 'pazar': kv.get('İşlem gördüğü pazar', ''), 'endeks': [x.strip() for x in (kv.get('Dahil olduğu endeksler') or '').split(',') if x.strip()],
            'web': kv.get('Web sitesi', ''), 'il': il_bul(kv.get('Merkez adresi', '')), 'tescil': (kv.get('Tescil tarihi') or '')[:10], 'ilk_islem': ilk,
            'ortaklar': ort[:8], 'yk': yk[:12], 'gm': gm, 'istirakler': ist[:15], 'istirak_n': len(ist), 'faaliyet': (re.search(r'\*\*Faaliyet konusu\*\*\s*\n\s*\n(.*?)\n\n##', md, re.S) or [0, ''])[1].strip()[:600]}


def kartlari_al(ft, kodlar):
    """{kod: kart metni}; 50'şerli aramalarla belge kimlikleri, 10'arlı gruplarla metinler."""
    idler = {}
    for i in range(0, len(kodlar), 40):
        g = kodlar[i:i + 40]
        liste = ', '.join(f'"{k}"' for k in g)
        r = ft.arac('dokumanlarda_ara', {'query': '', 'filter': f'dokuman_tipi = "kurumsal_bilgi_karti" AND iliskili_semboller IN [{liste}]', 'sayfa': 1, 'sayfa_basi': 50})
        for x in r.get('sonuclar', []):
            for s in x.get('iliskili_semboller', []):
                if s in g:
                    idler[s] = str(x['id'])
        log('  kart kimlikleri', len(idler))
    ters = {v: k for k, v in idler.items()}
    out = {}
    ids = list(ters)
    for i in range(0, len(ids), 8):
        g = ids[i:i + 8]
        try:
            for c in ft.arac('dokuman_chunk_yukle', {'ids': g}):
                out[ters[str(c['id'])]] = c.get('content', '')
        except Exception as e:
            log('  kart metin grubu atlandı', str(e)[:80])
        time.sleep(0.3)
        if (i // 8) % 10 == 0:
            log('  kart metni', len(out), '/', len(ids))
    return out


def donem_sirasi(d):
    return d[0] * 12 + d[1]


def finans(ft, kodlar):
    """{kod: {'ceyrek': [{d:'2026/6', satis, favok, net}], 'ttm': {...}, 'oz': özkaynak, 'nb': net borç, 'oran': {...}}}"""
    out = {k: {'ceyrek': {}, 'ttm': {}, 'oz': None, 'nb': None, 'oran': {}} for k in kodlar}
    for i in range(0, len(kodlar), 40):
        g = kodlar[i:i + 40]
        l = ', '.join(f"'{k}'" for k in g)
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, kalem, try_ceyreklik, try_ttm FROM hisse_finansal_tablolari_gelir_tablosu_kalemleri WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND kalem IN ('Satış Gelirleri','FAVÖK','Ana Ortaklık Payları') AND yil >= 2024 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            alan = {'Satış Gelirleri': 'satis', 'FAVÖK': 'favok', 'Ana Ortaklık Payları': 'net'}[x['kalem']]
            o['ceyrek'].setdefault(d, {})[alan] = sayi(x['try_ceyreklik'])
            o['ttm'].setdefault(d, {})[alan] = sayi(x['try_ttm'])
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, kalem, try_donemsel FROM hisse_finansal_tablolari_bilanco_kalemleri WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND kalem IN ('Ana Ortaklığa Ait Özkaynaklar','Net Borç') AND yil >= 2025 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            if x['kalem'] == 'Net Borç':
                o.setdefault('_nb', {})[d] = sayi(x['try_donemsel'])
            else:
                o.setdefault('_oz', {})[d] = sayi(x['try_donemsel'])
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, oran, deger FROM hisse_finansal_tablolari_finansal_oranlari WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND oran IN ('Özkaynak Karlılığı','Net Kar Marjı','FAVÖK Marjı','Brüt Kar Marjı','Hisse Başına Kar','Cari Oran','Net Kar (Yıllıklandırılmış)','Net Kar (Çeyreklik)','Aktif Karlılık') AND yil >= 2025 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            o.setdefault('_oran', {}).setdefault(d, {})[x['oran']] = sayi(x['deger'])
        log('  finans', min(i + 40, len(kodlar)), '/', len(kodlar))
    son = {}
    for k, o in out.items():
        cey = sorted(o['ceyrek'].items(), key=lambda z: donem_sirasi(z[0]))[-8:]
        r = {'ceyrek': [{'d': f'{d[0]}/{d[1]}', 's': v.get('satis'), 'f': v.get('favok'), 'n': v.get('net')} for d, v in cey]}
        if o['ttm']:
            d = max(o['ttm'], key=donem_sirasi); t = o['ttm'][d]
            r['donem'] = f'{d[0]}/{d[1]}'; r['ttm'] = {'satis': t.get('satis'), 'favok': t.get('favok'), 'net': t.get('net')}
        if o.get('_oz'):
            r['oz'] = o['_oz'][max(o['_oz'], key=donem_sirasi)]
        if o.get('_nb'):
            r['nb'] = o['_nb'][max(o['_nb'], key=donem_sirasi)]
        if o.get('_oran'):
            d = max(o['_oran'], key=donem_sirasi); r['oran'] = o['_oran'][d]; r.setdefault('donem', f'{d[0]}/{d[1]}')
            if not r.get('ttm') or r['ttm'].get('net') is None:
                n = o['_oran'][d].get('Net Kar (Yıllıklandırılmış)')
                if n is not None:
                    r.setdefault('ttm', {})['net'] = n
        son[k] = r
    return son


def main(kok):
    ft = hh.baglan()
    sinir = int(sys.argv[sys.argv.index('--sinir') + 1]) if '--sinir' in sys.argv else None
    sec = sys.argv[sys.argv.index('--kod') + 1].split(',') if '--kod' in sys.argv else None
    H = {}
    for s in fg.sayfala(ft, "SELECT hisse_senedi_kodu, unvan, aciklama, endeksler, odenmis_sermaye, fiili_dolasim_orani, piyasa_degeri, sektor_id FROM hisse_senetleri ORDER BY hisse_senedi_kodu"):
        H[s['hisse_senedi_kodu']] = s
    kodlar = sorted(sec or H)
    if sinir:
        kodlar = kodlar[:sinir]
    log('hisse', len(kodlar))
    kartlar = kartlari_al(ft, kodlar)
    F = finans(ft, kodlar)
    os.makedirs(os.path.join(kok, 'profil'), exist_ok=True)
    n = 0
    for k in kodlar:
        h = H[k]
        o = {'kod': k, 'ad': h['unvan'], 'tanim': h.get('aciklama') or '', 'sermaye': sayi(h.get('odenmis_sermaye')), 'dolasim': sayi(h.get('fiili_dolasim_orani')), 'pd': sayi(h.get('piyasa_degeri')),
             'guncelleme': datetime.datetime.now(TR).isoformat(timespec='minutes')}
        if k in kartlar:
            try:
                o.update(kart(kartlar[k]))
            except Exception as e:
                log('  kart çözülemedi', k, str(e)[:80])
        o['fin'] = F.get(k, {})
        json.dump(o, open(os.path.join(kok, 'profil', k + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        n += 1
    log('yazıldı: profil', n, 'kart', len(kartlar))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
