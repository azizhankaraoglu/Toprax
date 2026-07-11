# TabSIS Kullanıcı Kılavuzu — Yönetici / Muhasebe

> Bu kılavuz Kurum/Fabrika Müdürü, Sistem Yöneticisi ve finans
> (hakediş/cari hesap) işlemlerini yürüten personel içindir -- TabSIS'te
> ayrı bir "Muhasebe" rolü tanımlı değildir, finans yetkileri Sistem
> Yöneticisi/Kurum Yöneticisi rolüne (veya Ayarlar &gt; Özel Roller'dan
> tanımlanacak özel bir role) bağlıdır.

## Kurulum Sonrası İlk Adımlar

1. Kurulum sihirbazını (`/kurulum`) tamamlayın (bkz.
   `docs/KURULUM-KILAVUZU.md`).
2. **Ayarlar &gt; Kullanıcılar**'dan personel ekleyin, rol atayın.
3. **Ayarlar &gt; Entegrasyonlar**'dan SMS/e-posta/uydu sağlayıcılarını
   yapılandırın.
4. **Organizasyon Hiyerarşisi**'ni kurun (birim/pozisyon/kullanıcı
   ataması) -- onay zincirlerinin doğru çalışması buna bağlıdır.

## Finans / Hakediş

- **Hakediş** ekranından üretim sezonu bazlı hakediş hesaplaması
  yapılır (kotalı/kotasız tonaj, kalite katsayısı).
- **Cari Hesap** ekranından çiftçi bazlı bakiye takibi yapılır.
- Muhasebe kayıtları (ledger) **asla silinmez** -- bir hata durumunda
  "Ters Kayıt" (reverse) ile düzeltilir, orijinal kayıt korunur (denetim
  izi bütünlüğü).

## Onay Zinciri Yönetimi

**Ayarlar &gt; Onay Zincirleri**'nden hangi sürecin (destek, kampanya,
görev kapanışı, case atama) hangi adımlardan onay alacağını
tanımlayabilirsiniz.

## Raporlar ve Dashboard

Ana Dashboard ve **Raporlar** menüsündeki her kutucuk/grafik, ilgili
detay ekranına tıklanabilir (örn. "Açık Destek Talepleri" kutusuna
tıklamak Destek Kataloğu'na yönlendirir).

## Platform Yönetimi (sadece Platform Yöneticisi)

Yeni kurum (tenant) açma, lisans tanımlama ve tenant bazlı istatistikler
**Platform Admin** panelinden (`/platform`) yönetilir -- bkz.
`scripts/provision-tenant.sh` (otomasyonlu tenant açma).

## Geliştirici Portalı

Dış sistemlerle entegrasyon (API key, Postman koleksiyonu, webhook)
gerekiyorsa **Geliştirici Portalı** ekranını kullanın.
