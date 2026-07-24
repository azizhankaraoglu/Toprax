# Kantar Tartım Cihazı (RS232/USB) Entegrasyon Kılavuzu

**Denetim A12 (2026-07-24)** — Hasat döneminde kantar operatörünün ağırlığı
elle yazması yerine, tartım indikatöründen (Baykon, Esit, Tem, Dini Argeo vb.)
gelen değerin otomatik olarak TOPRAX "Hızlı Giriş" formuna düşmesi için yerel
köprü (bridge) kurulum kılavuzu.

## Mimari: Keyboard-Wedge Yaklaşımı

```
[Tartım İndikatörü] --RS232/USB--> [Kantar PC'sindeki köprü programı] --sanal klavye--> [Tarayıcıdaki TOPRAX formu]
```

Köprü, seri porttan okuduğu ağırlığı **sanki klavyeden yazılmış gibi** aktif
imlecin olduğu alana yazar. TOPRAX tarafında HİÇBİR değişiklik gerekmez —
operatör imleci "Brüt (ton)" alanına getirir (Hızlı Giriş formunda Enter ile
alan alan ilerlenir), indikatördeki "Print/Send" tuşuna basar, değer forma düşer.

### Seçenek 1 — Hazır yazılım (önerilen, kurulum ~10 dk)

Çoğu indikatör üreticisinin kendi "scale to keyboard" aracı vardır; genel
çözümler de mevcuttur:
- **232key** (ücretsiz sürümü yeterli) — COM port + baud rate seçilir,
  gelen veriden sayıyı ayıklayıp aktif pencereye yazar.
- İndikatör üreticinizin kendi PC yazılımı (ör. Baykon BX-Tools).

Ayarlar (indikatörün etiketinde/manualinde yazar, tipik değerler):
- Baud rate: 9600, Data bits: 8, Parity: None, Stop bits: 1
- Protokol: "Continuous output" KAPALI, "Print on demand" AÇIK olmalı
  (yoksa değer sürekli akar, forma çöp yazar).

### Seçenek 2 — Python köprüsü (30 satır, tam kontrol)

Kantar PC'sine Python + iki paket kurun:

```
pip install pyserial keyboard
```

`kantar_koprusu.py`:

```python
"""RS232 tartım indikatöründen ağırlık okuyup aktif pencereye yazar.
İndikatörün 'Print' tuşuna basıldığında bir satır veri gönderdiği
'print on demand' modunda çalışır. Ağırlık ton cinsine çevrilir."""
import re
import serial       # pyserial
import keyboard     # keyboard

PORT = "COM3"       # Aygıt Yöneticisi > Bağlantı Noktaları'ndan bakın
BAUD = 9600
BIRIM_KG = True     # İndikatör kg gönderiyorsa True (ton'a çevrilir)

ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Dinleniyor: {PORT} @ {BAUD} — indikatörde Print tuşuna basın (Ctrl+C ile çık)")
while True:
    line = ser.readline().decode("ascii", errors="ignore").strip()
    if not line:
        continue
    # Tipik çıktı örnekleri: "ST,GS,+00012340kg" / "  12340 kg" / "+012.340"
    m = re.search(r"[-+]?\d+[.,]?\d*", line)
    if not m:
        continue
    deger = float(m.group(0).replace(",", "."))
    if BIRIM_KG:
        deger = deger / 1000.0          # kg -> ton
    metin = f"{deger:.3f}".rstrip("0").rstrip(".")
    keyboard.write(metin)               # aktif imlecin olduğu alana yazar
    print(f"Yazıldı: {metin} t  (ham: {line!r})")
```

Çalıştırma: `python kantar_koprusu.py` (yönetici olarak — `keyboard`
paketi Windows'ta yönetici ister). Programı başlangıçta otomatik başlatmak
için bir kısayolunu `shell:startup` klasörüne koyun.

## Operatör Akışı (köprü + Hızlı Giriş)

1. TOPRAX > Kantar Kayıtları > **Hızlı Giriş** formu açık, imleç "Üye No"da.
2. Üye no yaz → Enter → plaka yaz → Enter (imleç "Brüt"te).
3. Kamyon dolu tartılır → indikatörde **Print** → değer forma düşer → Enter.
4. Kamyon boşaltıp döner, dara tartılır → **Print** → Enter.
5. Polar/kalite girilir → **Ctrl+Enter** → kayıt tamam, imleç başa döner.

Fare hiç kullanılmaz; kayıt başına ~10 saniye.

## Sorun Giderme

| Belirti | Muhtemel sebep |
|---|---|
| Hiç veri gelmiyor | Yanlış COM portu; kablo null-modem olmalı olabilir (2-3 pinleri çapraz) |
| Anlamsız karakterler | Baud rate/parity uyuşmuyor — indikatör menüsünden kontrol edin |
| Değer sürekli akıyor | İndikatör "continuous" modda — "print on demand"e alın |
| Değer 1000 kat büyük/küçük | `BIRIM_KG` ayarını ve indikatörün birimini kontrol edin |
