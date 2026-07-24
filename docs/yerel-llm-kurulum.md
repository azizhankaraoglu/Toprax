# Yerel LLM (Ollama) Kurulum Kılavuzu

**Denetim Faz 4 (2026-07-24)** — AI token kullanımını (OpenAI/Gemini/Anthropic
maliyetini) azaltmak için Llama-3.1 (sohbet) ve LLaVA (görüntü) kuantize
modellerini yerelde/kendi sunucunuzda çalıştırıp, sadece güven skoru düştüğünde
dış API'ye otomatik geçiş yapma altyapısı.

## 1. Ollama'yı Kurun

**Seçenek A — Docker (önerilen, ana docker-compose ile birlikte):**
```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama
```
Bu, `docker-compose.ollama.yml`'de tanımlı `toprax-ollama` konteynerini
mevcut `toprax-net` ağına ekler — backend konteynerinden `http://ollama:11434`
adresiyle erişilir. Sadece `127.0.0.1:11434` host'a açılır (dışarıya kapalı).

**Seçenek B — Doğrudan kurulum (Windows/macOS/Linux):**
[ollama.com/download](https://ollama.com/download) adresinden indirip kurun.
Kurulum sonrası `ollama serve` arka planda otomatik çalışır
(varsayılan: `http://localhost:11434`).

## 2. Modelleri İndirin

```powershell
# Windows
.\scripts\ollama-modelleri-indir.ps1
```
```bash
# Linux/macOS
./scripts/ollama-modelleri-indir.sh
```
Docker Seçenek A kullandıysanız `-Container` / `--container` bayrağını ekleyin.

Varsayılan modeller: **llama3.1:8b** (metin/sohbet) ve **llava:7b** (görüntü —
hastalık tespiti için). Farklı bir model istiyorsanız script'teki
`TextModel`/`VisionModel` değişkenlerini değiştirip tekrar çalıştırın, sonra
Ayarlar ekranındaki model adlarını da güncelleyin.

### Donanım notu
- **GPU (NVIDIA) varsa:** çok daha hızlı çalışır; `docker-compose.ollama.yml`
  içindeki `deploy.resources` bloğunun yorumunu kaldırın
  (`nvidia-container-toolkit` kurulu olmalı).
- **Sadece CPU:** 8B modeller ~8-16 GB RAM ister, yanıt süresi birkaç saniye
  ile birkaç dakika arasında değişebilir. Düşük donanımda `strategy` =
  "Sadece Dış" (external_only) güvenli varsayılandır.

## 3. TOPRAX'ta Etkinleştirin

**Ayarlar > Entegrasyonlar > AI Servisi** ekranında "Yerel LLM (Ollama)"
bölümünü açın:

| Alan | Açıklama |
|---|---|
| Ollama URL | Docker: `http://ollama:11434` · Yerel: `http://localhost:11434` |
| Metin modeli | `llama3.1:8b` (veya indirdiğiniz başka bir model) |
| Görüntü modeli | `llava:7b` |
| Strateji | aşağıya bakın |
| Güven Eşiği | sadece "Hibrit" seçiliyken görünür, 0-1 arası |

"Bağlantıyı Test Et" Ollama'nın `/api/tags` ucuna erişip yüklü modelleri
listeler (üretim yapmaz, yıkıcı değildir).

## 4. Strateji Seçimi

- **Sadece Yerel** (`local_only`) — Tüm istekler Ollama'ya gider, dış API'ye
  ASLA düşmez. En düşük maliyet, en yüksek gizlilik (veri hiç dışarı çıkmaz).
  Yerel model kapasitesi/kalitesi sınırlıysa yanıt kalitesi düşebilir.
- **Sadece Dış** (`external_only`, **varsayılan**) — Mevcut davranış, hiçbir
  şey değişmez. Yerel LLM hiç devreye girmez.
- **Hibrit** (`hybrid_confidence`, **önerilen**) — Her istek önce Ollama'ya
  gider; model kendi ürettiği bir güven puanını (0-1) bildirir. Puan sizin
  belirlediğiniz eşiğin (varsayılan 0.6) ALTINDAYSA istek otomatik olarak
  dış API'ye (Gemini/OpenAI/Anthropic — Ayarlar'da yapılandırılmış olan)
  yönlendirilir. Ollama'ya hiç ulaşılamazsa (kapalı/çökmüş) da aynı şekilde
  dış API'ye düşülür — kesintisiz çalışma.

Sistemdeki HER AI çağrısı (AI Copilot, Hastalık Tespiti, Ekim Planlama AI
anlatımı) bu tek stratejiyi kullanır — modül bazında ayrı ayarlama yoktur.

## 5. İzleme

God Mode > İstatistikler ekranındaki AI kullanım sayaçları artık her
isteğin `routed: local | external | escalated` etiketiyle işaretlendiğini
gösterir (`ai_usage_logs` koleksiyonu) — hibrit modda kaç isteğin yerelde
kaldığını, kaçının dışa eskale edildiğini buradan takip edebilirsiniz.

## Sorun Giderme

| Belirti | Çözüm |
|---|---|
| "Yerel LLM (Ollama) yapılandırılmamış" hatası | Ayarlar'da checkbox işaretli mi, URL doğru mu kontrol edin |
| Bağlantı testi başarısız | `docker ps` ile `toprax-ollama` çalışıyor mu bakın; Docker dışı kurulumda `ollama list` komutuyla servisin ayakta olduğunu doğrulayın |
| Yanıtlar çok yavaş | CPU-only ortamda normal; GPU ekleyin veya daha küçük bir model (`llama3.1:8b` yerine bir kuantize varyant) deneyin |
| Hibrit modda hep dışa gidiyor | Güven eşiğini düşürün (ör. 0.6 → 0.4) veya modelin ürettiği `GUVEN:` satırını loglardan kontrol edin |
