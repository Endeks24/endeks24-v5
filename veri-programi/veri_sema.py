"""e24-veri JSON şema doğrulayıcı (site/E24-VERI-SEMASI.md, sürüm 1; 17.10.2026: rakamlar bölümü, rakamlar.manset, rakam oranı, ucsey; AA: piyasa.hareket listeleri ve genişlik, kap.genel_kurul; AB: fiyat.tum).

Kullanım: from veri_sema import dogrula; hatalar = dogrula(veri)  # boş liste = geçerli
Doğrudan: python3 araclar/veri_sema.py veri.json
"""
import json, re, sys
from datetime import datetime

S, N, T, G, L = 'metin', 'sayi', 'tarih', 'gun', 'baglanti'  # alan türleri
# Panel bu ifadeleri güvenlik filtresiyle değiştiriyor; ayrıca HTML açısı kapatmamak için < > yasak
YASAK = re.compile(r'[<>]|exec\s*\(|eval\s*\(|javascript:|on\w+\s*=', re.I)


def tablo(satir=None, zorunlu_satir=(), **alanlar):
    """Tarihli tablo: tarih ve kaynak zorunlu. satir: satır alanları; alanlar: tablonun diğer alanları."""
    return {'tur': 'tablo', 'satir': satir, 'zorunlu_satir': zorunlu_satir, 'alanlar': alanlar}


SATIR_DEGISIM = {'kod': S, 'degisim': N}
SATIR_RAKAM = {'sayi': S, 'yon': ('up', 'dn', ''), 'aciklama': S, 'link': L, 'baslik': S, 'haber_tarihi': T, 'oran': N}  # oran: isteğe bağlı, 0-100 (kart çubuğu)
SATIR_MANSET = {'ad': S, 'deger': N, 'vurgu': bool}
SATIR_HAREKET = {'kod': S, 'fiyat': N, 'degisim': N, 'hacim_mn': N}  # AA: hacim milyon TL
SEMA = {
    'hisseler': {'tur': 'hisseler'},
    'kategoriler': {'tur': 'kategoriler'},
    'dosyalar': {'tur': 'dosyalar'},
    'halka_arz': {
        'takvim': tablo({'sirket': S, 'kod': S, 'talep_baslangic': G, 'ilk_islem': G, 'arz_fiyati': N,
                         'katilimci': N, 'araci': S, 'bugun_yuzde': N}, ('sirket',), **{'not': S}),
        'karne': tablo(None, (), ozet=S, kazandiranlar=[{'kod': S, 'yuzde': N}], kaybettirenler=[{'kod': S, 'yuzde': N}]),
        'spk_bekleyen': tablo({'sirket': S, 'detay': S}, ('sirket',), **{'not': S}),
    },
    'piyasa': {
        'seans': tablo(None, (), durum=('acik', 'kapali'), endeks=N, degisim=N, yorum=S, alt=[{'ad': S, 'deger': N, 'degisim': N}]),
        # AA: yukselenler (degisim > 0), dusenler (< 0), hacim (hacme göre); en çok 5 satır. gucluler/zayiflar eski biçim, okunmaya devam eder
        'hareket': tablo(None, (), gucluler=[SATIR_DEGISIM], zayiflar=[SATIR_DEGISIM], yukselenler=[SATIR_HAREKET], dusenler=[SATIR_HAREKET],
                         hacim=[SATIR_HAREKET], genislik={'yukselen': N, 'dusen': N, 'degismeyen': N}),
        'sektor_performans': tablo({'ad': S, 'degisim': N}, ('ad', 'degisim'), baslik=S, **{'not': S}),
    },
    'kap': {
        'temettu': tablo({'kod': S, 'hak_kullanim': G, 'brut': N, 'verim': N}, ('kod', 'hak_kullanim'), ay=S),
        'bilanco': tablo(None, (), ilk_tarih=G, aciklama=S, karne=S),
        'sermaye': tablo({'kod': S, 'detay': S, 'oran': S}, ('kod',)),
        # AA: genel kurul takvimi (sayfa önümüzdeki 30 günü gösterir); link KAP bildirimi
        'genel_kurul': tablo({'tarih': G, 'saat': S, 'kod': S, 'sirket': S, 'tur': ('olağan', 'olağanüstü'), 'link': L}, ('tarih', 'kod')),
    },
    'ekonomi': {
        'veri_takvimi': tablo({'tarih': G, 'saat': S, 'baslik': S, 'detay': S}, ('tarih', 'baslik')),
        'son_veriler': tablo({'ad': S, 'donem': S, 'son': (N, S), 'onceki': (N, S)}, ('ad', 'son')),
        'beklentiler': tablo({'deger': S, 'aciklama': S}, ('deger',)),
    },
    'doviz': {
        'kurlar': tablo({'ad': S, 'kod': ('USD', 'EUR', 'GBP', 'GA'), 'son': N, 'haftalik': N}, ('ad', 'son')),
        'rezerv': tablo(None, (), baslik=S, aciklama=S, link=L),
    },
    'kripto': {
        'varliklar': tablo({'ad': S, 'kod': S, 'dolar': N, 'degisim': N}, ('ad', 'dolar')),
        'dosya': {'tur': 'nesne', 'alanlar': {'baslik': S, 'aciklama': S, 'link': L}, 'zorunlu': ('baslik', 'link')},
    },
    'enerji': {
        'akaryakit': tablo({'sehir': S, 'benzin': N, 'motorin': N, 'lpg': N}, ('sehir',), **{'not': S}),
        'beklenen': tablo(None, (), tutar=S, yon=('zam', 'indirim'), yakit=S, aciklama=S),
        'brent': tablo(None, (), deger=N),
    },
    'sektorler': {'tur': 'sektorler'},
    # AB: bütün BIST hisseleri; haber şirket kutusu fiyatı buradan okur, kutuya yalnız buradaki kodlar girer (süre 96 saat)
    'fiyat': {
        # 18.10.2026: ad ve satır tarihi isteğe bağlı (widget sınırı); şirket adı sayfada KAP listesinden gelir. Tablonun tarih alanı işlem günüdür
        'tum': tablo({'kod': S, 'ad': S, 'kapanis': N, 'degisim': N, 'tarih': G}, ('kod', 'kapanis')),
    },
    # Z12: ana sayfa "Bugün bilmeniz gereken 3 şey" (24 saat geçerli; yoksa sayfa kendisi seçer)
    'ucsey': {'tur': 'ucsey'},
    # U4: haberlerdeki rakam işaretleri ve haftanın grafiği; Veri Masası toplar, tarayıcı haber okumaz
    'rakamlar': {
        'piyasa': tablo(SATIR_RAKAM, ('sayi', 'aciklama', 'link')),
        'gundem': tablo(SATIR_RAKAM, ('sayi', 'aciklama', 'link')),
        'ozel': tablo({'link': L, 'sayi': S, 'aciklama': S}, ('link', 'sayi')),
        # Y: manşet yan kutusu, manşet haberin adresiyle eşleşen kayıt; karşılaştırmalı çubuk grafik (en çok 5 satır)
        'manset': tablo({'link': L, 'baslik': S, 'alt_baslik': S, 'birim': S, 'kaynak': S, 'satirlar': [SATIR_MANSET]},
                        ('link', 'baslik', 'satirlar')),
        'grafik': tablo({'ad': S, 'deger': N, 'vurgu': bool}, ('ad', 'deger'),
                        tur=('cubuk', 'pay'), baslik=S, birim=S, deger=N, etiket=S, link=L),
    },
}


class Dogrulayici:
    def __init__(self):
        self.h = []

    def hata(self, yol, m):
        self.h.append(f'{yol}: {m}')

    def deger(self, yol, v, tur):
        if isinstance(tur, dict):
            return self.nesne(yol, v, tur, ())
        if tur in (dict, list, bool):
            if not isinstance(v, tur):
                self.hata(yol, {dict: 'nesne olmalı', list: 'liste olmalı', bool: 'true ya da false olmalı'}[tur])
            return
        if isinstance(tur, tuple) and all(isinstance(x, str) and x not in (S, N, T, G, L) for x in tur):
            if v not in tur:
                self.hata(yol, f'şunlardan biri olmalı: {", ".join(tur)}')
            return
        if isinstance(tur, tuple):
            if not any(self._uygun(v, t) for t in tur):
                self.hata(yol, 'sayı ya da metin olmalı')
            else:
                self.deger(yol, v, S if isinstance(v, str) else N)
            return
        if isinstance(tur, list):
            if not isinstance(v, list):
                return self.hata(yol, 'liste olmalı')
            for i, x in enumerate(v):
                self.nesne(f'{yol}[{i}]', x, tur[0], ())
            return
        if not self._uygun(v, tur):
            return self.hata(yol, {S: 'metin olmalı', N: 'sayı olmalı (tırnaksız)', T: 'ISO tarih-saat olmalı, ör. 2026-10-16T15:30:00+03:00',
                                   G: 'gün olmalı, ör. 2026-10-20', L: 'bağlantı / ya da https:// ile başlamalı'}[tur])
        if isinstance(v, str) and YASAK.search(v):
            self.hata(yol, 'izin verilmeyen karakter ya da ifade (< > exec( eval( javascript: on...=)')

    def _uygun(self, v, tur):
        if tur in (dict, list, bool):
            return isinstance(v, tur)
        if tur == N:
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        if tur in (S, L, T, G) and not isinstance(v, str):
            return False
        if tur == L:
            return v.startswith('/') or v.startswith('https://')
        if tur == T:
            try:
                return datetime.fromisoformat(v).tzinfo is not None
            except ValueError:
                return False
        if tur == G:
            try:
                datetime.fromisoformat(v[:10]); return len(v) == 10 or self._uygun(v, T)
            except ValueError:
                return False
        return True

    def nesne(self, yol, o, alanlar, zorunlu):
        if not isinstance(o, dict):
            return self.hata(yol, 'nesne olmalı')
        for k in o:
            if k not in alanlar:
                self.hata(f'{yol}.{k}', 'şemada olmayan alan')
        for k in zorunlu:
            if o.get(k) in (None, ''):
                self.hata(f'{yol}.{k}', 'zorunlu alan eksik')
        for k, t in alanlar.items():
            if k in o and o[k] is not None:
                self.deger(f'{yol}.{k}', o[k], t)

    def tablo(self, yol, o, sp):
        alanlar = dict(sp['alanlar'], tarih=T, kaynak=S)
        if sp['satir'] is not None:
            alanlar['satirlar'] = list
        self.nesne(yol, o, alanlar, ('tarih', 'kaynak'))
        if isinstance(o, dict) and 'yukselenler' in sp['alanlar']:  # AA: piyasa.hareket listeleri
            for ad, kosul, m in (('yukselenler', lambda d: d > 0, 'sıfırdan büyük olmalı'), ('dusenler', lambda d: d < 0, 'sıfırdan küçük olmalı'), ('hacim', None, '')):
                l = o.get(ad)
                if not isinstance(l, list):
                    continue
                if len(l) > 5:
                    self.hata(f'{yol}.{ad}', 'en çok 5 satır olmalı')
                for i, r in enumerate(l):
                    if not isinstance(r, dict):
                        continue
                    for k in ('kod', 'degisim'):
                        if r.get(k) in (None, ''):
                            self.hata(f'{yol}.{ad}[{i}].{k}', 'zorunlu alan eksik')
                    if kosul and self._uygun(r.get('degisim'), N) and not kosul(r['degisim']):
                        self.hata(f'{yol}.{ad}[{i}].degisim', m)
        if isinstance(o, dict) and sp['satir'] is not None and isinstance(o.get('satirlar'), list):
            for i, r in enumerate(o['satirlar']):
                self.nesne(f'{yol}.satirlar[{i}]', r, sp['satir'], sp['zorunlu_satir'])
                if sp['satir'] is SATIR_RAKAM and isinstance(r, dict) and isinstance(r.get('oran'), (int, float)) and not isinstance(r.get('oran'), bool) and not 0 <= r['oran'] <= 100:
                    self.hata(f'{yol}.satirlar[{i}].oran', '0 ile 100 arası olmalı')
                if sp['satir'].get('satirlar') == [SATIR_MANSET] and isinstance(r, dict) and isinstance(r.get('satirlar'), list):
                    if not r['satirlar']:
                        self.hata(f'{yol}.satirlar[{i}].satirlar', 'en az 1 satır olmalı')
                    if len(r['satirlar']) > 5:
                        self.hata(f'{yol}.satirlar[{i}].satirlar', 'en çok 5 satır olmalı')
                    for j, z in enumerate(r['satirlar']):
                        if isinstance(z, dict):
                            for k in ('ad', 'deger'):
                                if z.get(k) in (None, ''):
                                    self.hata(f'{yol}.satirlar[{i}].satirlar[{j}].{k}', 'zorunlu alan eksik')

    def bolum(self, yol, o, sp):
        tur = sp.get('tur') if isinstance(sp, dict) else None
        if tur == 'tablo':
            return self.tablo(yol, o, sp)
        if tur == 'nesne':
            return self.nesne(yol, o, sp['alanlar'], sp['zorunlu'])
        if tur == 'hisseler':
            self.nesne(yol, o, {'tarih': T, 'kaynak': S, 'liste': dict}, ('tarih', 'kaynak'))
            for kod, h in (o.get('liste') or {}).items() if isinstance(o, dict) and isinstance(o.get('liste'), dict) else []:
                if not re.fullmatch(r'[A-ZÇĞİÖŞÜ0-9]{3,6}', kod):
                    self.hata(f'{yol}.liste.{kod}', 'hisse kodu 3 ile 6 büyük harf olmalı')
                self.nesne(f'{yol}.liste.{kod}', h, {'ad': S, 'fiyat': N, 'degisim': N, 'kap': L}, ())
            return
        if tur == 'kategoriler':
            if not isinstance(o, dict):
                return self.hata(yol, 'nesne olmalı')
            for slug, k in o.items():
                y = f'{yol}.{slug}'
                if not re.fullmatch(r'[a-z0-9-]+', slug):
                    self.hata(y, 'anahtar kategori adresi olmalı, ör. halka-arz')
                self.nesne(y, k, {'aciklama': S, 'serit': dict, 'rehber': dict, 'kavramlar': list}, ())
                if isinstance(k, dict):
                    if 'serit' in k:
                        self.tablo(f'{y}.serit', k['serit'], tablo(None, (), ogeler=[{'deger': S, 'aciklama': S, 'yon': ('up', 'dn', '')}]))
                    if 'rehber' in k:
                        self.nesne(f'{y}.rehber', k['rehber'], {'baslik': S, 'aciklama': S, 'link': L}, ('baslik', 'link'))
                    for i, kv in enumerate(k.get('kavramlar') or []):
                        self.nesne(f'{y}.kavramlar[{i}]', kv, {'baslik': S, 'tanim': S, 'link': L}, ('baslik',))
            return
        if tur == 'dosyalar':
            if not isinstance(o, list):
                return self.hata(yol, 'liste olmalı')
            for i, d in enumerate(o):
                y = f'{yol}[{i}]'
                self.nesne(y, d, {'tarih': T, 'baslik': S, 'link': L, 'kategoriler': list, 'aciklama': S, 'sayilar': list, 'maddeler': list}, ('tarih', 'baslik'))
                if isinstance(d, dict):
                    for j, s in enumerate(d.get('kategoriler') or []):
                        self.deger(f'{y}.kategoriler[{j}]', s, S)
                    for j, s in enumerate(d.get('sayilar') or []):
                        self.nesne(f'{y}.sayilar[{j}]', s, {'deger': S, 'aciklama': S}, ('deger',))
                    for j, s in enumerate(d.get('maddeler') or []):
                        self.nesne(f'{y}.maddeler[{j}]', s, {'tarih': G, 'metin': S, 'link': L}, ('tarih', 'metin'))
            return
        if tur == 'ucsey':
            self.nesne(yol, o, {'tarih': T, 'kaynak': S, 'maddeler': list}, ('tarih', 'kaynak', 'maddeler'))
            if isinstance(o, dict) and isinstance(o.get('maddeler'), list):
                if len(o['maddeler']) != 3:
                    self.hata(f'{yol}.maddeler', 'tam 3 madde olmalı')
                for i, md in enumerate(o['maddeler']):
                    self.nesne(f'{yol}.maddeler[{i}]', md, {'baslik': S, 'link': L, 'kategori': S}, ('baslik', 'link', 'kategori'))
            return
        if tur == 'sektorler':
            if not isinstance(o, dict):
                return self.hata(yol, 'nesne olmalı')
            for slug, s in o.items():
                y = f'{yol}.{slug}'
                self.nesne(y, s, {'tarih': T, 'kaynak': S, 'kapanis': bool, 'islem_goren': N, 'yukselen': N, 'dusen': N, 'ortalama': N, 'hisseler': list},
                           ('tarih', 'kaynak', 'hisseler'))
                if isinstance(s, dict):
                    for i, h in enumerate(s.get('hisseler') or []):
                        self.nesne(f'{y}.hisseler[{i}]', h, {'kod': S, 'fiyat': N, 'degisim': N}, ('kod', 'degisim'))
            return
        # alt tablolardan oluşan bölüm (halka_arz, piyasa ...)
        if not isinstance(o, dict):
            return self.hata(yol, 'nesne olmalı')
        for k, v in o.items():
            if k not in sp:
                self.hata(f'{yol}.{k}', 'şemada olmayan tablo')
            else:
                self.bolum(f'{yol}.{k}', v, sp[k])

    def kok(self, v):
        if not isinstance(v, dict):
            return self.hata('kök', 'JSON nesnesi olmalı')
        if v.get('surum') != 1:
            self.hata('surum', '1 olmalı')
        for k, o in v.items():
            if k == 'surum':
                continue
            if k not in SEMA:
                self.hata(k, 'şemada olmayan bölüm')
            else:
                self.bolum(k, o, SEMA[k])


def dogrula(veri):
    d = Dogrulayici()
    d.kok(veri)
    return d.h


if __name__ == '__main__':
    v = json.load(open(sys.argv[1], encoding='utf-8'))
    h = dogrula(v)
    print('GEÇERLİ' if not h else 'GEÇERSİZ:\n  ' + '\n  '.join(h))
    sys.exit(1 if h else 0)
