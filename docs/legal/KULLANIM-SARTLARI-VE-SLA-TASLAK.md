# Kullanım Şartları / Gizlilik Politikası / SLA (Taslak)

> **DİKKAT:** Taslaktır, hukuki tavsiye değildir. Yürürlüğe koymadan önce
> hukuk danışmanına onaylatılmalı; SLA'daki rakamlar (uptime %, destek
> süresi) bir ticari karardır ve kullanıcı tarafından belirlenmelidir
> (ROADMAP-URUNLESTIRME.md PR-16 "Sizin Yapmanız Gerekir").

## Bölüm A — Kullanım Şartları (ToS) Taslağı

1. **Taraflar:** [SATICI FİRMA ADI] ("Sağlayıcı") ile TabSIS'i kullanan
   kurum ("Müşteri") arasındaki ilişkiyi düzenler.
2. **Lisans Kapsamı:** Müşteri'ye, satın aldığı plan (bkz. platform_core.py
   `licenses` koleksiyonu — trial/standard/premium) kapsamında, on-premise
   kurulum için devredilemez, münhasır olmayan bir kullanım hakkı verilir.
3. **Müşteri Yükümlülükleri:** Sunucu altyapısının (bkz. docs/KURULUM-KILAVUZU.md
   Bölüm 2) sağlanması, erişim güvenliğinin (şifreler, TLS sertifikaları)
   korunması, yasal veri işleme yükümlülüklerine (KVKK) uyum.
4. **Fikri Mülkiyet:** Yazılımın kaynak kodu ve tüm fikri mülkiyet hakları
   Sağlayıcı'ya aittir; Müşteri sadece kullanım hakkına sahiptir.
5. **Sorumluluk Sınırlaması:** [KURUM'A ÖZEL — genelde dolaylı zararların
   hariç tutulması ve toplam sorumluluğun ödenen lisans bedeliyle
   sınırlandırılması standart bir madde olur, hukuk danışmanı onayı gerekir.]
6. **Fesih:** [KURUM'A ÖZEL — bildirim süresi, veri iadesi koşulları.]

## Bölüm B — Gizlilik Politikası Taslağı

TabSIS on-premise bir kurulum olduğu için veriler Müşteri'nin kendi
sunucusunda/veri merkezinde tutulur — Sağlayıcı bu verilere doğrudan
erişmez (destek amaçlı erişim ayrı bir yetkilendirme gerektirir). Detaylı
işlenen veri kategorileri için bkz. `KVKK-AYDINLATMA-METNI.md`.

## Bölüm C — SLA (Hizmet Seviyesi Anlaşması) Taslağı

| Madde | Öneri (ORNEK — onaylayın/değiştirin) |
|---|---|
| Uptime taahhüdü | %99,5 (aylık ~3.6 saat kesinti payı) |
| Kritik hata müdahale süresi | 4 iş saati |
| Yüksek öncelik müdahale süresi | 1 iş günü |
| Standart destek müdahale süresi | 3 iş günü |
| Destek kanalı | [E-POSTA/TELEFON/DESTEK PORTALI] |
| Bakım penceresi | [ÖRN. Pazar 02:00-04:00] |
| Yedekleme sıklığı | Günlük (bkz. `scripts/backup.sh`, PR-11) |

Yukarıdaki rakamlar bir ticari karardır — nihai değerleri siz belirleyip
onaylamalısınız.
