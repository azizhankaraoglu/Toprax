# VHR (Yüksek Çözünürlüklü Uydu) Fizibilite Raporu — Kök Sayımı

**Tarih:** 2026-08-19
**Soru:** "Ekilen her tarlada kaç adet kök ekildiğini uydudan sayabilir miyiz?"
**Kısa cevap:** Hayır — tek pancar bitkisi hiçbir ticari uydudan sayılamaz.
Uydu, sıra yapısını ve boşlukları görebilir; bitkiyi sayamaz.

---

## 1. Fiziksel sınır: çözünürlük vs bitki boyutu

| Kaynak | Çözünürlük (pankromatik) | Çok bantlı | 1 piksel ≈ |
|---|---|---|---|
| NASA HLS (bugün kullandığımız) | 30 m | 30 m | 900 m² |
| Sentinel-2 | 10 m | 10-20 m | 100 m² |
| PlanetScope | 3 m | 3 m | 9 m² |
| SkySat (Planet) | 50 cm | 2 m | 0,25 m² |
| Pléiades Neo | 30 cm | 1,2 m | 0,09 m² |
| Maxar WorldView-3 | 31 cm | 1,24 m | 0,10 m² |
| **Drone (RGB, 100 m irtifa)** | **1-3 cm** | — | **0,0004 m²** |

Şeker pancarı bitkisi:
- **Çıkış (BBCH 10-12):** 2-5 cm çap — sayımın yapılması gereken evre budur.
- **Olgunluk:** ~30-40 cm kanopi, ama bu evrede sıralar kapandığı için
  bitkiler birbirine değer ve tek tek ayrışmaz.

**Sonuç:** 31 cm çözünürlükte, çıkıştaki bir pancar fidesi **tek pikselin
onda biri** kadardır. Nesne tespiti için literatürdeki asgari kural, hedefin
en az 3-5 piksele yayılmasıdır. Bu, çıkış evresinde **≤1 cm** çözünürlük
demektir — yani yalnızca drone.

Karşılaştırma: 30 cm VHR ile **ağaç sayımı** (zeytin, narenciye, ceviz)
rutin olarak yapılır, çünkü ağaç tacı 3-5 m'dir (10-16 piksel).

## 2. VHR ile ölçülebilecekler (kök sayımı yerine)

30-50 cm çözünürlükte pancar tarlasında **gerçekten** ölçülebilenler:

1. **Sıra yapısı ve sıra arası mesafe** — ekim makinesi ayarının doğrulanması.
2. **Boşluk lekeleri (gap detection)** — 1 m² üzeri çıkış olmayan alanlar.
   Bu, "kaç bitki eksik" sorusuna dolaylı ama kullanışlı bir cevaptır.
3. **Kanopi kapalılık oranı** — dekar başına yeşil alan yüzdesi; bitki
   sıklığıyla korelasyonu yüksektir (kalibrasyon gerekir).
4. **Tarla içi düzgünsüzlük haritası** — VRA (değişken oranlı uygulama)
   reçetesi için doğrudan girdi.

## 3. Maliyet ve asgari sipariş gerçeği

| Kalem | Arşiv görüntü | Yeni çekim (tasking) |
|---|---|---|
| Fiyat aralığı | ~10-25 USD/km² | ~25-45 USD/km² |
| Asgari sipariş alanı | 5-25 km² | 25-100 km² |
| Teslim süresi | saatler-günler | 1-3 hafta (buluta bağlı) |

**Kritik nokta:** Demo köylerimizin ortalama parseli ~200 dekar = **0,2 km²**.
Asgari sipariş 25 km² ise, tek parsel için ödenen bedel gerçekte 125 parselin
bedelidir. **Parsel bazlı VHR ekonomik değildir; köy/ova bazlı mantıklıdır.**

5 köyümüzün toplam kapladığı alan kabaca 60-80 km² — yani **tek bir tasking
siparişi 5 köyü birden kapsayabilir**. Bu ölçekte maliyet dekar başına
makul seviyeye iner.

## 4. Drone karşılaştırması

| | VHR uydu (30 cm) | Drone (2 cm) |
|---|---|---|
| Kök sayımı | **Yapılamaz** | Yapılır (%92-97 doğruluk, literatür) |
| Boşluk tespiti | Yapılır (>1 m²) | Yapılır (tek bitki) |
| Alan/gün | Sınırsız (uydu geçişi) | 300-800 dekar |
| Maliyet | Alan bazlı, sabit | Uçuş başına (operatör + zaman) |
| Bulut bağımlılığı | Var | Yok |
| İzin/mevzuat | Yok | SHGM uçuş izni gerekir |

TOPRAX'ta `drone_missions` modülü zaten mevcut — kök sayımı için doğru
altyapı budur.

## 5. Öneri

**Üç katmanlı yaklaşım (bu turda 1. ve 3. katman uygulandı):**

1. **Agronomik hesap (uygulandı — `backend/crop_stand.py`):**
   sıra arası × sıra üzeri × alan × çimlenme oranı. Pancarda 45×19 cm ile
   ~11.000 bitki/dekar. Ekim makinesi ayarından doğrudan türetilir, maliyeti
   sıfırdır ve tarımda standart yöntemdir.
2. **VHR ile boşluk/sıra analizi (ertelendi):** köy ölçeğinde tek sipariş.
   `satellite_provider.py` içindeki UP42 tasking iskeleti hazır bekliyor;
   kimlik bilgisi girildiğinde çalışır. Karar: **fiyat teklifi alındıktan
   sonra**.
3. **Drone ile kesin sayım (mevcut modül):** şüpheli/itirazlı parsellerde.

**Bir sonraki adım:** UP42 üzerinden 5 köyü kapsayan bir arşiv sorgusu
(fiyat + mevcut görüntü tarihleri) çıkarılması. Bu, ticari bir teklif
sürecidir ve kod değişikliği gerektirmez.
