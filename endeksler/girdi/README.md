# Elle ve kaynaklı derlenen girdiler

Bu klasördeki dosyalar Endeks24 Göstergelerinin elle derlenen verisidir. Her fiyatın kaynağı ve tarihi yazılır; kaynaksız fiyat girilmez.

- `simit-menemen.json`: Simit ve Menemen Endeksi. Her ay aynı tarihte, aynı işletmelerden, her ürün için en az 3 işletme.
  Biçim: {"yontem": ["..."], "kaynak": "...", "donemler": {"2026-11": {"simit": [{"isletme": "...", "fiyat": 30, "tarih": "2026-11-02", "kaynak": "adres ya da menü"}], "menemen": [...]}}}
- `maas-kac.json`: Maaş karşılığı. Biçim: {"tarih": "2026-11-02", "urunler": [{"ad": "iPhone 17 Pro 256 GB", "fiyat": 119999, "tarih": "2026-11-02", "kaynak": "apple.com/tr"}], "yontem": ["..."]}
