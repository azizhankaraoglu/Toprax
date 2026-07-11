# KVKK Aydınlatma Metni (Taslak)

> **DİKKAT:** Bu metin bir **taslaktır** ve hukuki tavsiye niteliği
> taşımaz. Yürürlüğe koymadan önce mutlaka bir hukuk danışmanına
> onaylatılmalıdır (ROADMAP-URUNLESTIRME.md PR-15 "Sizin Yapmanız
> Gerekir"). [KURUM ADI], [ADRES], [İLETİŞİM] gibi köşeli parantezli
> alanlar kuruma özel bilgilerle doldurulmalıdır.

## 1. Veri Sorumlusu

[KURUM ADI] ("Kurum"), 6698 sayılı Kişisel Verilerin Korunması Kanunu
("KVKK") uyarınca veri sorumlusu sıfatıyla, TabSIS platformu üzerinden
işlediği kişisel verilerinize ilişkin olarak sizi bilgilendirmek ister.

## 2. İşlenen Kişisel Veri Kategorileri

- **Kimlik Bilgileri:** ad-soyad, T.C. kimlik numarası, üye numarası.
- **İletişim Bilgileri:** telefon, e-posta, adres.
- **Mesleki/Operasyonel Bilgiler:** parsel/arazi bilgileri, ürün/hasat
  verileri, sözleşme bilgileri, sulama/gübreleme kayıtları.
- **Finansal Bilgiler:** hakediş, avans, cari hesap hareketleri.
- **Konum Verileri:** parsel koordinatları, saha ziyaret konumları.
- **Görsel Veriler:** saha/hastalık tespiti fotoğrafları, uydu/drone
  görüntüleri (yalnızca arazi kapsıyorsa kişisel veri niteliği taşımaz;
  kişi görüntüsü içeriyorsa özel nitelikli olabilir — bu durumda ayrı
  değerlendirme gerekir).

## 3. İşleme Amaçları

- Tarımsal operasyonların yönetimi (üretim planlama, saha görevleri,
  hasat/verim takibi).
- Sözleşme ve hakediş/ödeme süreçlerinin yürütülmesi.
- Yasal yükümlülüklerin yerine getirilmesi (e-fatura, irsaliye).
- Kurum ile iletişim (bildirim, kampanya, destek talepleri).
- Eğitim ve gelişim faaliyetlerinin (LMS) yürütülmesi.

## 4. Hukuki Sebep

KVKK m.5/2 kapsamında: sözleşmenin kurulması/ifası, hukuki
yükümlülüğün yerine getirilmesi, veri sorumlusunun meşru menfaati.
Açık rıza gerektiren işlemler (örn. pazarlama amaçlı iletişim) için
ayrıca açık rıza alınır (bkz. Bölüm 6).

## 5. Kişisel Verilerin Aktarımı

Kişisel verileriniz; yasal yükümlülükler kapsamında yetkili kamu
kurumlarına, hizmet aldığımız tedarikçilere (SMS/e-posta sağlayıcı,
bulut barındırma — bkz. Ayarlar &gt; Entegrasyonlar'da tanımlı
sağlayıcılar), ve mevzuatın izin verdiği diğer taraflara aktarılabilir.
On-premise kurulumda veriler [KURUM ADI]'nın kendi sunucusunda/veri
merkezinde tutulur.

## 6. Açık Rıza Gerektiren İşlemler

Aşağıdaki işlemler için ayrıca açık rızanız alınır ve
`consent_records` koleksiyonunda (bkz. `backend/consent.py`) geri
alınabilir şekilde kayıt altına alınır:

- Pazarlama/promosyon amaçlı SMS/e-posta/WhatsApp gönderimi.
- [KURUM'A ÖZEL diğer açık rıza gerektiren işlemler]

## 7. Haklarınız (KVKK m.11)

Kişisel verilerinizin işlenip işlenmediğini öğrenme, işlenmişse buna
ilişkin bilgi talep etme, işlenme amacını öğrenme, yurt içi/yurt
dışında aktarıldığı üçüncü kişileri bilme, eksik/yanlış işlenmişse
düzeltilmesini isteme, silinmesini/yok edilmesini isteme, itiraz etme
ve zarara uğramanız hâlinde giderilmesini talep etme haklarına
sahipsiniz. Taleplerinizi [BAŞVURU KANALI/E-POSTA] üzerinden iletebilirsiniz.

## 8. Veri Saklama Süresi

Kişisel verileriniz, ilgili mevzuatta öngörülen süreler ve/veya işleme
amacının gerektirdiği süre boyunca saklanır; sürenin sona ermesi
hâlinde silinir, yok edilir veya anonim hâle getirilir. [KURUM'A ÖZEL
saklama süresi politikası buraya eklenmelidir.]
