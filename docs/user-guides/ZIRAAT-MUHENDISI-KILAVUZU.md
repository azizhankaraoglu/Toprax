# Toprax Kullanım Kılavuzu — Uzman

> Hedef Kitle: Ziraat Mühendisleri ve Teknik Uzmanlar

## 1. Uzman Rolü Ne İşe Yarar

Bu kılavuz saha/teknik uzmanlık gerektiren işleri yürüten kişiler (başta ziraat mühendisleri) içindir: parsel ve üretim sezonu takibi, saha ziyaretleri, hastalık tespiti, toprak/sulama reçeteleri ve bunlarla ilgili onaylar.

> **NOT:** Toprak/numune personeli, saha personeli ve kantar personeli gibi diğer teknik roller benzer ama daha dar kapsamlı ekranlar kullanır — bu kılavuz en geniş yetkiye sahip Ziraat Mühendisi rolünü esas alır.

## 2. Ana Görevleriniz

- Parsel ve üretim sezonu takibi (Operasyon menüsü)
- Saha ziyaretleri ve hastalık tespiti kayıtları
- Toprak/numune analiz sonuçlarının değerlendirilmesi
- Sulama/gübreleme reçetelerinin onaylanması
- Saha personelinin görev kapanışlarının onaylanması

## 3. Harita Paneli

Harita Paneli'nden parsel bazlı katmanları (uydu/NDVI, drone görüntüsü, IoT sensör verisi — kurulduysa) inceleyebilir, doğrudan harita üzerinden saha görevi oluşturabilirsiniz.

> **NOT:** AI Copilot ve AI Hastalık Tespiti menü öğeleri kurumunuzda bu özellik açık (feature flag "ai") ise görünür.

## 4. Parsel ve Üretim Sezonu Takibi

Parseller ekranından arazileri, üretim döngüsü (ekim/gelişim/hasat aşaması) bilgisiyle birlikte takip edebilir, gerektiğinde çizim araçlarıyla parsel sınırlarını düzenleyebilir veya böl/birleştir işlemi yapabilirsiniz.

## 5. Toprak ve Sulama Kayıtlarının Değerlendirilmesi

Toprak Analizleri raporundan çiftçilerin numune sonuçlarını inceler, Sulama & Kaynak ekranından girilen sulama kayıtlarına dayanarak reçete/öneri hazırlarsınız.

## 6. Saha Operasyonları

Görev Yönetimi (Saha Operasyonları) ekranından size veya ekibinize atanan görevleri görür, saha personelinin tamamladığı görevlerin fotoğraf/notlarını inceleyip onaylayabilirsiniz.

## 7. AI Copilot ve Hastalık Tespiti

AI Copilot, genel tarımsal sorularınızda yapay zeka destekli öneriler sunar. AI Hastalık ekranından ise çiftçi veya saha personeli tarafından yüklenen fotoğrafların yapay zeka değerlendirmesini görüp kendi uzman görüşünüzle onaylar/düzeltirsiniz.

## 8. Otomasyon Kuralları

Otomasyon Kuralları ekranından, belirli bir olay gerçekleştiğinde (örn. bir hastalık tespiti geldiğinde) otomatik olarak bir saha görevi oluşturulmasını sağlayan kurallar tanımlayabilirsiniz.

## 9. Onay Bekleyenlerim

Organizasyon hiyerarşinizde onayınızı gerektiren süreçler (örn. bir saha personelinin görev kapanışı) Onay Bekleyenlerim ekranında toplanır.

## 10. Raporlar

Raporlar menüsünden verimlilik, hastalık/risk dağılımı ve saha operasyon özeti raporlarına ulaşabilirsiniz.

## 11. Bize Ulaşın

Çiftçilerden gelen teknik nitelikli talepler (hastalık bildirimi, sulama problemi vb.) Bize Ulaşın ekranında size atanabilir; buradan çiftçiyle mesajlaşabilir, gerekirse bir saha görevi oluşturabilirsiniz.

## 12. Sık Sorulan Sorular

**S: AI hastalık tespiti sonucuna katılmıyorum.**
C: AI sonucu sadece bir ÖN değerlendirmedir — kendi uzman görüşünüzle onaylayabilir veya düzeltebilirsiniz, nihai karar sizindir.

**S: Harita panelinde uydu/NDVI katmanı görünmüyor.**
C: Bu özellik Ayarlar > Entegrasyonlar'dan bir admin tarafından yapılandırılmalıdır (Sentinel Hub/NASA FIRMS/UP42) — görünmüyorsa henüz kurulmamış olabilir.

**S: Bir saha görevini neden onaylayamıyorum?**
C: Görev size atanmamış olabilir ya da henüz "tamamlandı" durumuna alınmamıştır — Görev Yönetimi ekranından durumu kontrol edin.

