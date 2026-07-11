# TabSIS Kullanım Kılavuzu — Yönetici

> Hedef Kitle: İl/İlçe Yöneticisi, Fabrika Müdürü ve Muhasebe Personeli

## 1. Yönetici Rolü Ne İşe Yarar

Bu kılavuz, kurumunuzun günlük İŞ yönetimini yürüten kişiler içindir: hakediş/finans takibi, onay süreçleri, raporlama ve saha operasyonlarının genel görünümü. Sistem ayarları (kullanıcı/rol yönetimi, entegrasyonlar) için "Admin Kullanım Kılavuzu"na bakın — bu iki kılavuz aynı teknik yetki seviyesindeki (Admin Katmanı) kişilere hitap eder, ama farklı GÖREVLERİ anlatır.

## 2. Dashboard ve Genel Bakış

Giriş sonrası karşınıza çıkan Dashboard'da toplam çiftçi/parsel/alan/sözleşme sayıları, 5 yıllık üretim trendi, bölge bazlı performans ve çiftçi karne dağılımı özet olarak sunulur. Her kutucuk/grafik, ilgili detay ekranına tıklanabilir.

## 3. Çiftçi ve Parsel Yönetimi

Çiftçiler ve Parseller ekranlarından kurumunuza bağlı üreticileri ve arazilerini görüntüler, arama/filtreleme yapabilir, gerektiğinde yeni kayıt ekleyebilirsiniz. Harita Paneli'nden parsellerin coğrafi dağılımını ve (kuruluysa) uydu/NDVI katmanlarını inceleyebilirsiniz.

## 4. Sözleşme & Kota Yönetimi

Sözleşme & Kota ekranından üreticilerinizle yapılan sezonluk sözleşmeleri (kota, çeşit, avans bilgileri) yönetirsiniz.

## 5. Hakediş (Finans)

Hakediş ekranından üretim sezonu bazlı hakediş hesaplaması yapılır (kotalı/kotasız tonaj, kalite katsayısı dahil). Cari Hesap ekranından çiftçi bazlı bakiye takibi yapılır.

> **NOT:** Muhasebe kayıtları (ledger) ASLA silinmez — bir hata durumunda "Ters Kayıt" (reverse) ile düzeltilir, orijinal kayıt korunur. Bu, denetim izi bütünlüğü için kasıtlı bir tasarımdır.

## 6. Cari Hesap Mutabakatı

Mutabakat (Reconciliation) ekranından çiftçi cari hesaplarınızı dönemsel olarak karşılaştırıp uyuşmazlıkları tespit edebilirsiniz.

## 7. Onay Bekleyenlerim

Organizasyon hiyerarşinizde onayınızı gerektiren süreçler (örn. bir case ataması, kampanya onayı, görev kapanışı) Onay Bekleyenlerim ekranında toplanır. Buradan onaylayabilir veya reddedebilirsiniz.

> **NOT:** Hangi sürecin onay gerektireceğini Admin katmanındaki bir kullanıcı Ayarlar > Onay Zincirleri'nden tanımlar — bu ekranın kendisi sadece SİZE gelen bekleyen onayları gösterir.

## 8. Organizasyon Hiyerarşisi

Organizasyon Hiyerarşisi ekranından kurumunuzun birim/pozisyon yapısını ve kimin kime bağlı olduğunu görüntüleyebilirsiniz.

## 9. Kampanyalar

Kampanyalar ekranından çiftçi segmentlerine (örn. belirli bir bölgedeki üreticiler) yönelik SMS/e-posta/WhatsApp duyuru kampanyaları planlayabilir, onaya sunabilir ve sonuçlarını (iletildi/başarısız) takip edebilirsiniz.

## 10. Saha Operasyonları — Genel Bakış

Görev Yönetimi ekranından saha personeline atanan görevlerin durumunu (planlı/devam ediyor/tamamlandı) izleyebilirsiniz. Operasyon ekranından makine filosu ve işçi vardiya bilgilerine ulaşırsınız.

## 11. Raporlar

Raporlar menü grubu altında toplanan ekranlardan aşağıdaki analizlere ulaşırsınız:

| Ekran | İçerik |
|---|---|
| Toprak Analizleri | Numune sonuçlarının özeti |
| Saha Raporları | Tamamlanan saha görevlerinin özeti |
| Verimlilik | Sezon/bölge bazlı verim karşılaştırması |
| Çiftçi Karne | En yüksek/geliştirme bekleyen üretici listeleri |
| UFYD Dashboard | Üretici Finansal Yönetim Dashboard'u |

## 12. Bize Ulaşın (Case Yönetimi)

Bize Ulaşın ekranından çiftçilerden ve saha personelinden gelen tüm talepleri (destek, şikayet, öneri, hastalık bildirimi vb.) görür, personele atayabilir ve durumlarını (yeni → atandı → inceleniyor → çözüldü) takip edebilirsiniz.

> **NOT:** Giriş sayfasındaki "Hesabınız yok mu?" formundan gelen talepler de bu ekranda "Hesap / Giriş Talebi" kategorisiyle görünür.

## 13. Sık Sorulan Sorular

**S: Bir hakediş kaydında hata yaptım, nasıl düzeltirim?**
C: Kaydı silemezsiniz — ilgili kayıttan "Ters Kayıt" oluşturup ardından doğru kaydı girin. Böylece hem hata hem düzeltme denetim izinde görünür kalır.

**S: Onay Bekleyenlerim ekranında hiçbir şey görünmüyor.**
C: Ya bekleyen bir onay yoktur ya da kurumunuzda ilgili süreç için henüz bir onay zinciri tanımlanmamıştır (bu durumda işlemler doğrudan uygulanır, onaya düşmez).

**S: Kampanya gönderirken bazı kişilere ulaşmadı.**
C: Kara listede olan kişilere (KVKK) hiçbir kampanya gönderilmez — bu beklenen bir davranıştır, hata değildir.

