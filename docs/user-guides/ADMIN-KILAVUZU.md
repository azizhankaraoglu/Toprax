# Toprax Kullanım Kılavuzu — Admin

> Hedef Kitle: Sistem Yöneticisi / Kurum Yöneticisi

## 1. Admin Rolü Ne İşe Yarar

Bu kılavuz, Toprax'in TEKNİK/SİSTEMSEL yönetimini yapan kişiler içindir: kullanıcı ve rol yönetimi, entegrasyon (SMS/e-posta/AI/uydu) yapılandırması, form/lookup tanımları, denetim izi ve platform ayarları. Günlük iş yönetimi (hakediş, onaylar, raporlar) için "Yönetici Kullanım Kılavuzu"na bakın.

> **NOT:** Toprax'te teknik olarak ayrı bir "Admin" rolü yoktur — bu yetkiler super_admin, kurum_yöneticisi, il_yöneticisi ve fabrika_müdürü rollerinin hepsinde birden vardır ("Admin Katmanı"). Bu kılavuz, kurumunuzda bu işleri fiilen kimin yaptığına göre size veya bir iş arkadaşınıza yöneliktir.

## 2. Kurulum Sonrası İlk Adımlar

1. Kurulum sihirbazını (/kurulum) tamamlayın — ayrıntılı adımlar için docs/KURULUM-KILAVUZU.md dosyasına bakın.
2. İlk platform admin hesabıyla giriş yapın.
3. Ayarlar > Kullanıcılar ekranından kurumunuzun personelini ekleyin ve rol atayın.
4. Ayarlar (Entegrasyonlar) ekranından SMS/e-posta/AI/uydu sağlayıcı bilgilerinizi girin.
5. Organizasyon Hiyerarşisi ekranından birim/pozisyon/kullanıcı atamalarını kurun — onay zincirlerinin doğru çalışması buna bağlıdır.

## 3. Kullanıcı ve Rol Yönetimi

Kullanıcılar ekranından (Sistem menüsü altında) personel hesabı açabilir, pasif hale getirebilir ve rol atayabilirsiniz.

| Rol | Kapsamı |
|---|---|
| Süper Admin / Kurum Yöneticisi | Tüm yetkiler — sistem genelinde tam erişim |
| İl / İlçe Yöneticisi, Fabrika Müdürü | İş yönetimi + sistem ayarlarına erişim (Admin katmanı) |
| Ziraat Mühendisi | Saha/teknik uzman yetkileri — sistem ayarlarına erişimi yoktur |
| Saha Personeli / Toprak Personeli / Kantar Personeli | Kendi görev alanıyla sınırlı, sadece görüntüleme + veri girişi |
| Çiftçi | Ayrı bir self-servis portal kullanır, bu ekranlara erişimi yoktur |

Bir role tam uymayan özel bir yetki seti gerekiyorsa, Özel Roller ekranından yetki kataloğundan seçerek kendi rolünüzü tanımlayabilirsiniz.

> **NOT:** Sistem menüsündeki bazı ekranlar ("adminTierOnly" işaretli) sadece yukarıdaki ilk iki satırdaki rollere görünür — Ziraat Mühendisi ve altındaki roller bu ekranları menüde hiç görmez.

## 4. Entegrasyonlar (Ayarlar Ekranı)

Sol menüdeki "Ayarlar" ekranından kurumunuzun kullanacağı dış servisleri (hepsi opsiyonel) yapılandırırsınız:

- **SMS:** Netgsm veya Twilio hesap bilgileriniz (kontör bazlı ücretli servisler).
- **E-posta:** Kurumunuzun SMTP sunucu bilgileri.
- **AI Servisi:** OpenAI / Google Gemini / Anthropic Claude API anahtarı (AI Copilot ve hastalık tespiti için).
- **Uydu Görüntüsü:** Sentinel Hub, NASA FIRMS veya UP42 API bilgileri (NDVI/yangın verisi için).

> **NOT:** Her entegrasyon türü için "Bağlantıyı Test Et" düğmesiyle gerçek bir bağlantı denemesi yapabilirsiniz — bilgiler kaydedildikten sonra mutlaka test edin.

## 5. Form ve Lookup Yönetimi

Form Yönetimi ekranından kurumunuzun ihtiyaç duyduğu dinamik alanları (örn. çiftçi/parsel kartına özel yeni bir bilgi alanı) kod yazmadan tanımlayabilirsiniz. Lookup Yönetimi ekranından ise açılır listelerde kullanılan sabit değer gruplarını (örn. ürün çeşitleri, bölge listesi) yönetirsiniz.

## 6. Destek Kataloğu ve Şablon Yönetimi

Destek Kataloğu, çiftçilere sunulan destek/hibe programlarının tanımlarını tutar. Şablon Yönetimi ekranından ise SMS/e-posta/WhatsApp bildirimlerinde kullanılan mesaj şablonlarını (değişken alanlarıyla birlikte) düzenlersiniz.

## 7. İletişim Politikaları (KVKK)

İletişim Politikaları ekranından, hangi iş olayında (örn. "Hakediş Oluştu") hangi kanaldan otomatik bildirim gideceğini tanımlarsınız. Aynı ekranın Kara Liste bölümünden, kendisine hiçbir mesaj/kampanya gönderilmemesi gereken kişileri (KVKK talebiyle) işaretlersiniz.

## 8. Organizasyon Hiyerarşisi ve Onay Zincirleri

Organizasyon Hiyerarşisi ekranından kurumunuzun birim/pozisyon/kullanıcı yapısını tanımlarsınız. Onay Zincirleri (bu yapıya bağlı olarak) hangi sürecin (destek talebi, kampanya, görev kapanışı, case atama) hangi adımlardan onay alacağını belirler.

## 9. Audit Log (Denetim İzi)

Audit Log ekranı, sistemdeki her önemli değişikliği (kim, ne zaman, neyi değiştirdi) kaydeder ve GERİYE DÖNÜK SİLİNEMEZ/DEĞİŞTİRİLEMEZ. Bir sorun araştırmasında ilk bakılacak yerdir.

## 10. Geliştirici Portalı

Dış sistemlerle (muhasebe programı, üçüncü parti bir uygulama vb.) entegrasyon gerekiyorsa Geliştirici Portalı ekranından API anahtarı oluşturabilir, hazır Postman/Insomnia koleksiyonunu indirebilir ve webhook ayarlarına ulaşabilirsiniz.

## 11. Platform Core (Özellik Bayrakları) ve Feature Flags

Platform Core ekranından kurumunuz için hangi modüllerin (örn. AI Copilot, LMS/Eğitim) açık olacağını siz belirlersiniz — kapatılan bir özelliğin menüsü kullanıcılardan otomatik gizlenir.

## 12. Platform Yönetimi (Sadece Platform Yöneticisi)

Eğer kurumunuz Toprax'i birden fazla kooperatif/kurum için merkezi olarak barındırıyorsa, yeni kurum (tenant) açma, lisans tanımlama ve kurum bazlı istatistikler /platform adresindeki Platform Admin panelinden yönetilir. Tek kurumluk (on-premise) kurulumlarda bu bölüm genelde kullanılmaz.

## 13. Yedekleme ve Güvenlik

Yedekleme, TLS/sertifika yönetimi ve sunucu gereksinimleri gibi altyapısal konular bu kılavuzun kapsamı dışındadır — ayrıntılı adımlar için docs/KURULUM-KILAVUZU.md dosyasına başvurun.

## 14. Sık Sorulan Sorular

**S: Bir kullanıcı işten ayrıldı, hesabını nasıl kapatırım?**
C: Kullanıcıyı SİLMEYİN — Kullanıcılar ekranından "Pasif" durumuna alın. Geçmiş kayıtları korunur, sadece giriş yapamaz hale gelir.

**S: Entegrasyon testinde hata alıyorum.**
C: Girdiğiniz API anahtarı/şifrenin doğru olduğundan ve sunucunuzun ilgili servise internet erişiminin (varsa güvenlik duvarı/proxy ayarları) açık olduğundan emin olun.

**S: Bir kullanıcının yetkileri rolüne uymuyor, ne yapmalıyım?**
C: Özel Roller ekranından o kullanıcıya özel ek yetki tanımlayabilir ya da bir yetkiyi kaldırabilirsiniz; built-in rolün kendisini değiştirmeniz gerekmez.

