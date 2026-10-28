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
                                f"AND kalem IN ('Satış Gelirleri','FAVÖK','Ana Ortaklık Payları','Grubun Karı (Zararı)') AND yil >= 2024 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            alan = {'Satış Gelirleri': 'satis', 'FAVÖK': 'favok', 'Ana Ortaklık Payları': 'net', 'Grubun Karı (Zararı)': 'net2'}[x['kalem']]
            o['ceyrek'].setdefault(d, {})[alan] = sayi(x['try_ceyreklik'])
            o['ttm'].setdefault(d, {})[alan] = sayi(x['try_ttm'])
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, kalem, try_donemsel FROM hisse_finansal_tablolari_bilanco_kalemleri WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND kalem IN ('Ana Ortaklığa Ait Özkaynaklar','Net Borç','ÖZKAYNAKLAR') AND yil >= 2025 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            if x['kalem'] == 'Net Borç':
                o.setdefault('_nb', {})[d] = sayi(x['try_donemsel'])
            elif x['kalem'] == 'ÖZKAYNAKLAR':
                o.setdefault('_oz2', {})[d] = sayi(x['try_donemsel'])   # banka, sigorta, faktoring, leasing, varlık yönetimi: toplam özkaynak
            else:
                o.setdefault('_oz', {})[d] = sayi(x['try_donemsel'])
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, oran, deger FROM hisse_finansal_tablolari_finansal_oranlari WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND oran IN ('Özkaynak Karlılığı','Net Kar Marjı','FAVÖK Marjı','Brüt Kar Marjı','Hisse Başına Kar','Cari Oran','Net Kar (Yıllıklandırılmış)','Net Kar (Çeyreklik)','Aktif Karlılık','Kredi Mevduat Oranı','Çeyreklik Kredi Değişimi','Çeyreklik Mevduat Değişimi','Konservasyon Oranı','Tazminat Tediye Oranı','Hasar Prim Oranı','Alınan Primler / Özkaynaklar') AND yil >= 2025 ORDER BY hisse_senedi_kodu, yil, ay"):
            o = out[x['hisse_senedi_kodu']]
            d = (int(x['yil']), int(x['ay']))
            o.setdefault('_oran', {}).setdefault(d, {})[x['oran']] = sayi(x['deger'])
        log('  finans', min(i + 40, len(kodlar)), '/', len(kodlar))
    son = {}
    for k, o in out.items():
        for tur in ('ceyrek', 'ttm'):
            for d, v in o[tur].items():
                if v.get('net') is None and v.get('net2') is not None:
                    v['net'] = v['net2']      # Ana ortaklık payı yoksa grubun kârı (banka, varlık yönetimi)
        cey = sorted(o['ceyrek'].items(), key=lambda z: donem_sirasi(z[0]))[-8:]
        r = {'ceyrek': [{'d': f'{d[0]}/{d[1]}', 's': v.get('satis'), 'f': v.get('favok'), 'n': v.get('net')} for d, v in cey]}
        if o['ttm']:
            d = max(o['ttm'], key=donem_sirasi); t = o['ttm'][d]
            r['donem'] = f'{d[0]}/{d[1]}'; r['ttm'] = {'satis': t.get('satis'), 'favok': t.get('favok'), 'net': t.get('net')}
        if o.get('_oz'):
            r['oz'] = o['_oz'][max(o['_oz'], key=donem_sirasi)]
        elif o.get('_oz2'):
            r['oz'] = o['_oz2'][max(o['_oz2'], key=donem_sirasi)]   # finansal şirket: toplam özkaynak (azınlık payı küçüktür)
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


def banka_ekleri(ft, kodlar):
    """Banka şablonu: {kod: {'tip':'bank', 'nfg_ttm', 'ucret_ttm', 'kredi', 'mevduat', 'aktif', 'nf_ceyrek':[{d, v}]}}. Satış ve FAVÖK bankalarda yoktur; yerine net faiz geliri ve net ücret/komisyon gelirleri gösterilir."""
    out = {}
    try:
        bank = {x['hisse_senedi_kodu'] for x in fg.sayfala(ft, "SELECT DISTINCT hisse_senedi_kodu FROM hisse_finansal_tablolari WHERE yil >= 2025 AND finansal_tablo_sablonu = 'bank'")}
    except Exception as e:
        log('  banka listesi atlandı', str(e)[:80])
        return out
    kodlar = [k for k in kodlar if k in bank]
    if not kodlar:
        return out
    l = ', '.join(f"'{k}'" for k in kodlar)
    try:
        nf, uc = {}, {}
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, kalem, try_ceyreklik, try_ttm FROM hisse_finansal_tablolari_gelir_tablosu_kalemleri WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND kalem IN ('NET FAİZ GELİRİ VEYA GİDERİ','NET ÜCRET VE KOMİSYON GELİRLERİ VEYA GİDERLERİ') AND yil >= 2024 ORDER BY hisse_senedi_kodu, yil, ay"):
            d = (int(x['yil']), int(x['ay']))
            (nf if x['kalem'].startswith('NET FAİZ') else uc).setdefault(x['hisse_senedi_kodu'], {})[d] = (sayi(x['try_ceyreklik']), sayi(x['try_ttm']))
        bil = {}
        for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, kalem, try_donemsel FROM hisse_finansal_tablolari_bilanco_kalemleri WHERE hisse_senedi_kodu IN ({l}) "
                                f"AND kalem IN ('VARLIKLAR TOPLAMI','KREDİLER (Net)','Mevduat') AND yil >= 2025 ORDER BY hisse_senedi_kodu, yil, ay"):
            bil.setdefault(x['hisse_senedi_kodu'], {}).setdefault(x['kalem'], {})[(int(x['yil']), int(x['ay']))] = sayi(x['try_donemsel'])
        for k in kodlar:
            o = {'tip': 'bank'}
            if nf.get(k):
                d = max(nf[k], key=donem_sirasi)
                o['nfg_ttm'] = nf[k][d][1]
                o['nf_ceyrek'] = [{'d': f'{a[0]}/{a[1]}', 'v': v[0]} for a, v in sorted(nf[k].items(), key=lambda z: donem_sirasi(z[0]))[-8:]]
            if uc.get(k):
                o['ucret_ttm'] = uc[k][max(uc[k], key=donem_sirasi)][1]
            for kalem, ad in (('VARLIKLAR TOPLAMI', 'aktif'), ('KREDİLER (Net)', 'kredi'), ('Mevduat', 'mevduat')):
                v = bil.get(k, {}).get(kalem)
                if v:
                    o[ad] = v[max(v, key=donem_sirasi)]
            out[k] = o
    except Exception as e:
        log('  banka ekleri atlandı', str(e)[:80])
    log('  banka', len(out))
    return out


def halka_arz_ve_temettu(ft, kodlar):
    """{kod: {'ha': {fiyat, duz, tarih, araci}, 'tmt': {ttm, donem}}}. Halka arz: halka_arzlar; temettü: nakit akış tablosundaki 'Ödenen Temettüler' (son 12 ay, TL, pozitif)."""
    out = {k: {} for k in kodlar}
    for i in range(0, len(kodlar), 100):
        g = kodlar[i:i + 100]
        l = ', '.join(f"'{k}'" for k in g)
        try:
            for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, ilk_islem_tarihi_europe_istanbul, halka_arz_fiyati, duzeltilmis_halka_arz_fiyati, araci_kurum FROM halka_arzlar WHERE hisse_senedi_kodu IN ({l}) AND halka_arz_fiyati IS NOT NULL ORDER BY hisse_senedi_kodu, ilk_islem_tarihi_europe_istanbul"):
                out[x['hisse_senedi_kodu']]['ha'] = {'fiyat': sayi(x['halka_arz_fiyati']), 'duz': sayi(x.get('duzeltilmis_halka_arz_fiyati')),
                                                     'tarih': str(x.get('ilk_islem_tarihi_europe_istanbul') or '')[:10] or None, 'araci': x.get('araci_kurum')}
        except Exception as e:
            log('  halka arz atlandı', str(e)[:80])
        try:
            son = {}
            for x in fg.sayfala(ft, f"SELECT hisse_senedi_kodu, yil, ay, try_ttm FROM hisse_finansal_tablolari_nakit_akis_tablosu_kalemleri WHERE hisse_senedi_kodu IN ({l}) AND kalem = 'Ödenen Temettüler' AND yil >= 2025 AND try_ttm IS NOT NULL ORDER BY hisse_senedi_kodu, yil, ay"):
                son[x['hisse_senedi_kodu']] = (int(x['yil']), int(x['ay']), sayi(x['try_ttm']))
            for k, (y, a_, v) in son.items():
                if v is not None:
                    out[k]['tmt'] = {'ttm': round(abs(v)), 'donem': f'{y}/{a_}'}
        except Exception as e:
            log('  temettü atlandı', str(e)[:80])
    log('  halka arz', sum(1 for v in out.values() if 'ha' in v), 'temettü', sum(1 for v in out.values() if 'tmt' in v))
    return out


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
    for k, v in banka_ekleri(ft, kodlar).items():
        F.setdefault(k, {})['bk'] = v
    HT = halka_arz_ve_temettu(ft, kodlar)
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
        o.update(HT.get(k, {}))
        json.dump(o, open(os.path.join(kok, 'profil', k + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        n += 1
    log('yazıldı: profil', n, 'kart', len(kartlar))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
