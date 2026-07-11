/**
 * MVP TAMAMLAMA — Ek Sayfalar
 * 
 * Bu dosya şu sayfaları içerir:
 * - AyarlarEntegrasyon: SMS/Email API key yönetimi
 * - HastalıkTespiti: AI Gemini Vision ile foto analiz
 * - EFaturalar, İrsaliyeler, Kantar: Resmi belge listeleri
 * - AuditLog: Sistem aktivite kayıtları
 * - UyduGorunutu: NDVI/uydu mock görselleştirme
 * - SahaPWA: Mobil saha mühendisi ziyaret raporu
 */

import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import {
  Settings, Key, MessageSquare, Mail, Wifi, Save, Upload, Camera, Loader2,
  Brain, Receipt, FileSpreadsheet, Scale, Activity, Satellite, MapPin, CheckCircle2,
  Radio, Plane
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { QuickAddPanel } from "@/components/QuickAdd";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

// =====================================================================
// AYARLAR — SMS/Email API key girişi
// =====================================================================
export function AyarlarEntegrasyon() {
  const [integrations, setIntegrations] = useState(null);
  const [forms, setForms] = useState({});          // itype -> {provider, config, enabled}
  const [testing, setTesting] = useState({});      // itype -> bool
  const [testResult, setTestResult] = useState({});// itype -> {ok, message}
  const [saving, setSaving] = useState({});        // itype -> bool
  const [saved, setSaved] = useState({});          // itype -> bool
  const [testInputs, setTestInputs] = useState({ sms_phone: "", email_to: "" });

  const load = () => api.get("/integrations").then((r) => {
    const byType = {};
    r.data.integrations.forEach((it) => { byType[it.type] = it; });
    setIntegrations(byType);
    // formları mevcut kayıtlı değerlerle doldur (secret alanlar maskeli gelir,
    // kullanıcı değiştirmezse PUT sırasında olduğu gibi korunur)
    const initialForms = {};
    r.data.integrations.forEach((it) => {
      initialForms[it.type] = { provider: it.provider || "", config: { ...it.config }, enabled: it.enabled };
    });
    setForms(initialForms);
  });
  useEffect(load, []);

  function setField(itype, key, value) {
    setForms((f) => ({ ...f, [itype]: { ...f[itype], config: { ...f[itype]?.config, [key]: value } } }));
  }
  function setProvider(itype, provider) {
    setForms((f) => ({ ...f, [itype]: { ...f[itype], provider } }));
  }

  async function save(itype) {
    setSaving((s) => ({ ...s, [itype]: true }));
    try {
      const f = forms[itype];
      await api.put(`/integrations/${itype}`, { provider: f.provider, config: f.config, enabled: true });
      setSaved((s) => ({ ...s, [itype]: true }));
      setTimeout(() => setSaved((s) => ({ ...s, [itype]: false })), 2500);
      load();
    } finally {
      setSaving((s) => ({ ...s, [itype]: false }));
    }
  }

  async function test(itype, extraBody = {}) {
    setTesting((t) => ({ ...t, [itype]: true }));
    setTestResult((r) => ({ ...r, [itype]: null }));
    try {
      const r = await api.post(`/integrations/${itype}/test`, extraBody);
      setTestResult((tr) => ({ ...tr, [itype]: { ok: true, message: r.data.message } }));
    } catch (e) {
      setTestResult((tr) => ({ ...tr, [itype]: { ok: false, message: e.response?.data?.detail || "Bağlantı testi başarısız oldu." } }));
    } finally {
      setTesting((t) => ({ ...t, [itype]: false }));
    }
  }

  if (!integrations) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const TestBadge = ({ itype }) => {
    const r = testResult[itype];
    if (!r) return null;
    return (
      <div className={`text-xs mt-2 flex items-start gap-2 ${r.ok ? "text-[var(--primary)]" : "text-red-400"}`}>
        {r.ok ? <CheckCircle2 size={14} className="mt-0.5 shrink-0"/> : <Wifi size={14} className="mt-0.5 shrink-0"/>}
        <span>{r.message}</span>
      </div>
    );
  };

  return (
    <div className="p-8 max-w-[1200px]" data-testid="ayarlar-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM AYARLARI</div>
        <h1 className="font-display text-4xl">Entegrasyonlar</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Kullanıcı adı/şifre veya API key gerektiren tüm dış servisler burada yönetilir.
          Sadece yönetici katmanı erişebilir.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ============ SMS ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400"><MessageSquare size={20}/></div>
            <div>
              <h3 className="font-display text-lg">SMS Servisi</h3>
              <p className="text-xs text-[var(--text-dim)]">Netgsm / Twilio / Özel Webhook</p>
            </div>
          </div>

          <label className="text-xs text-[var(--text-dim)] mb-1.5 block">SAĞLAYICI</label>
          <select className="input mb-3" value={forms.sms?.provider || ""}
                  onChange={(e) => setProvider("sms", e.target.value)}>
            <option value="">Seçiniz…</option>
            <option value="netgsm">Netgsm</option>
            <option value="twilio">Twilio</option>
            <option value="custom_webhook">Özel Webhook</option>
          </select>

          {forms.sms?.provider === "netgsm" && (
            <div className="space-y-3">
              <input className="input" placeholder="Kullanıcı Kodu (usercode)"
                     value={forms.sms?.config?.netgsm_usercode || ""}
                     onChange={(e) => setField("sms", "netgsm_usercode", e.target.value)} />
              <input className="input" type="password" placeholder="Şifre"
                     value={forms.sms?.config?.netgsm_password || ""}
                     onChange={(e) => setField("sms", "netgsm_password", e.target.value)} data-testid="sms-key-input"/>
              <input className="input" placeholder="Mesaj Başlığı (msgheader)"
                     value={forms.sms?.config?.netgsm_header || ""}
                     onChange={(e) => setField("sms", "netgsm_header", e.target.value)} />
            </div>
          )}
          {forms.sms?.provider === "twilio" && (
            <div className="space-y-3">
              <input className="input" placeholder="Account SID"
                     value={forms.sms?.config?.twilio_account_sid || ""}
                     onChange={(e) => setField("sms", "twilio_account_sid", e.target.value)} />
              <input className="input" type="password" placeholder="Auth Token"
                     value={forms.sms?.config?.twilio_auth_token || ""}
                     onChange={(e) => setField("sms", "twilio_auth_token", e.target.value)} data-testid="sms-key-input"/>
              <input className="input" placeholder="Gönderen Numara (+90...)"
                     value={forms.sms?.config?.twilio_from_number || ""}
                     onChange={(e) => setField("sms", "twilio_from_number", e.target.value)} />
            </div>
          )}
          {forms.sms?.provider === "custom_webhook" && (
            <div className="space-y-3">
              <input className="input" placeholder="Webhook URL"
                     value={forms.sms?.config?.webhook_url || ""}
                     onChange={(e) => setField("sms", "webhook_url", e.target.value)} />
              <input className="input" type="password" placeholder="Authorization Header (opsiyonel)"
                     value={forms.sms?.config?.webhook_auth_header || ""}
                     onChange={(e) => setField("sms", "webhook_auth_header", e.target.value)} />
            </div>
          )}

          {forms.sms?.provider && (
            <>
              <input className="input mt-3" placeholder="Test için telefon numarası (05xx...)"
                     value={testInputs.sms_phone}
                     onChange={(e) => setTestInputs((t) => ({ ...t, sms_phone: e.target.value }))} />
              <div className="flex gap-2 mt-3">
                <button onClick={() => save("sms")} disabled={saving.sms} className="btn btn-ghost" data-testid="save-settings-btn">
                  <Save size={14}/> {saving.sms ? "Kaydediliyor…" : "Kaydet"}
                </button>
                <button onClick={() => test("sms", { phone: testInputs.sms_phone })}
                        disabled={testing.sms || !testInputs.sms_phone}
                        className="btn btn-primary">
                  {testing.sms ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
                  {testing.sms ? "Test ediliyor…" : "Bağlantıyı Test Et"}
                </button>
              </div>
              {saved.sms && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
              <TestBadge itype="sms"/>
            </>
          )}
        </div>

        {/* ============ EMAIL ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-400"><Mail size={20}/></div>
            <div>
              <h3 className="font-display text-lg">E-Posta Servisi (SMTP)</h3>
              <p className="text-xs text-[var(--text-dim)]">Herhangi bir SMTP sağlayıcı (Gmail, Outlook, kurumsal sunucu vb.)</p>
            </div>
          </div>
          <div className="space-y-3">
            <input className="input" placeholder="SMTP Sunucu (örn. smtp.gmail.com)"
                   value={forms.email?.config?.host || ""}
                   onChange={(e) => setField("email", "host", e.target.value)} />
            <div className="grid grid-cols-2 gap-3">
              <input className="input" placeholder="Port (örn. 587)"
                     value={forms.email?.config?.port || ""}
                     onChange={(e) => setField("email", "port", e.target.value)} />
              <select className="input" value={forms.email?.config?.use_tls ?? true}
                      onChange={(e) => setField("email", "use_tls", e.target.value === "true")}>
                <option value="true">TLS (STARTTLS)</option>
                <option value="false">SSL</option>
              </select>
            </div>
            <input className="input" placeholder="Kullanıcı Adı / E-posta"
                   value={forms.email?.config?.username || ""}
                   onChange={(e) => setField("email", "username", e.target.value)} />
            <input className="input" type="password" placeholder="Şifre / Uygulama Şifresi"
                   value={forms.email?.config?.password || ""}
                   onChange={(e) => setField("email", "password", e.target.value)} data-testid="email-key-input"/>
            <input className="input" placeholder="Gönderen Adresi (opsiyonel, boşsa kullanıcı adı kullanılır)"
                   value={forms.email?.config?.from_address || ""}
                   onChange={(e) => setField("email", "from_address", e.target.value)} />
            <input className="input" placeholder="Test için alıcı e-posta adresi"
                   value={testInputs.email_to}
                   onChange={(e) => setTestInputs((t) => ({ ...t, email_to: e.target.value }))} />
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("email")} disabled={saving.email} className="btn btn-ghost">
              <Save size={14}/> {saving.email ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("email", { to_email: testInputs.email_to })}
                    disabled={testing.email || !testInputs.email_to}
                    className="btn btn-primary">
              {testing.email ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.email ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.email && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="email"/>
        </div>

        {/* ============ AI SERVİSİ ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400"><Brain size={20}/></div>
            <div>
              <h3 className="font-display text-lg">AI Servisi</h3>
              <p className="text-xs text-[var(--text-dim)]">Hastalık tespiti ve öneriler için vision-AI sağlayıcısı</p>
            </div>
          </div>
          <label className="text-xs text-[var(--text-dim)] mb-1.5 block">SAĞLAYICI</label>
          <select className="input mb-3" value={forms.ai_service?.provider || ""}
                  onChange={(e) => setProvider("ai_service", e.target.value)}>
            <option value="">Seçiniz…</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Google Gemini</option>
            <option value="anthropic">Anthropic Claude</option>
          </select>
          {forms.ai_service?.provider && (
            <div className="space-y-3">
              <input className="input" type="password" placeholder="API Key"
                     value={forms.ai_service?.config?.api_key || ""}
                     onChange={(e) => setField("ai_service", "api_key", e.target.value)} />
              <input className="input" placeholder="Model (opsiyonel, örn. gpt-4o-mini)"
                     value={forms.ai_service?.config?.model || ""}
                     onChange={(e) => setField("ai_service", "model", e.target.value)} />
            </div>
          )}
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("ai_service")} disabled={saving.ai_service} className="btn btn-ghost">
              <Save size={14}/> {saving.ai_service ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("ai_service")} disabled={testing.ai_service} className="btn btn-primary">
              {testing.ai_service ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.ai_service ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.ai_service && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="ai_service"/>
        </div>

        {/* ============ PLANET LABS ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center text-cyan-400"><Satellite size={20}/></div>
            <div>
              <h3 className="font-display text-lg">Planet Labs (Uydu Görüntüsü)</h3>
              <p className="text-xs text-[var(--text-dim)]">Gerçek key girilene kadar mock modda çalışır</p>
            </div>
          </div>
          <div className="space-y-3">
            <input className="input" type="password" placeholder="API Key"
                   value={forms.planet_labs?.config?.api_key || ""}
                   onChange={(e) => setField("planet_labs", "api_key", e.target.value)} />
            <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <input type="checkbox"
                     checked={forms.planet_labs?.config?.mock_mode ?? true}
                     onChange={(e) => setField("planet_labs", "mock_mode", e.target.checked)} />
              Mock mod (gerçek hesap gelene kadar açık bırakın)
            </label>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("planet_labs")} disabled={saving.planet_labs} className="btn btn-ghost">
              <Save size={14}/> {saving.planet_labs ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("planet_labs")} disabled={testing.planet_labs} className="btn btn-primary">
              {testing.planet_labs ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.planet_labs ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.planet_labs && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="planet_labs"/>
        </div>

        {/* ============ SENTINEL HUB (2026-07-11 — Uydu Ekosistemi Araştırması) ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 flex items-center justify-center text-sky-400"><Satellite size={20}/></div>
            <div>
              <h3 className="font-display text-lg">Sentinel Hub (Copernicus)</h3>
              <p className="text-xs text-[var(--text-dim)]">Varsayılan NDVI sağlayıcısı — gerçek key girilene kadar mock modda çalışır</p>
            </div>
          </div>
          <div className="space-y-3">
            <input className="input" placeholder="Client ID"
                   value={forms.sentinel_hub?.config?.client_id || ""}
                   onChange={(e) => setField("sentinel_hub", "client_id", e.target.value)} />
            <input className="input" type="password" placeholder="Client Secret"
                   value={forms.sentinel_hub?.config?.client_secret || ""}
                   onChange={(e) => setField("sentinel_hub", "client_secret", e.target.value)} data-testid="sentinel-hub-key-input"/>
            <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <input type="checkbox"
                     checked={forms.sentinel_hub?.config?.mock_mode ?? true}
                     onChange={(e) => setField("sentinel_hub", "mock_mode", e.target.checked)} />
              Mock mod (gerçek hesap gelene kadar açık bırakın)
            </label>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("sentinel_hub")} disabled={saving.sentinel_hub} className="btn btn-ghost">
              <Save size={14}/> {saving.sentinel_hub ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("sentinel_hub")} disabled={testing.sentinel_hub} className="btn btn-primary">
              {testing.sentinel_hub ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.sentinel_hub ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.sentinel_hub && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="sentinel_hub"/>
        </div>

        {/* ============ NASA FIRMS (yangın izleme, ücretsiz) ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center text-orange-400"><Radio size={20}/></div>
            <div>
              <h3 className="font-display text-lg">NASA FIRMS (Yangın İzleme)</h3>
              <p className="text-xs text-[var(--text-dim)]">Ücretsiz, gerçek-zamanlı yangın/sıcak nokta tespiti</p>
            </div>
          </div>
          <div className="space-y-3">
            <input className="input" type="password" placeholder="MAP_KEY"
                   value={forms.nasa_firms?.config?.map_key || ""}
                   onChange={(e) => setField("nasa_firms", "map_key", e.target.value)} data-testid="nasa-firms-key-input"/>
            <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <input type="checkbox"
                     checked={forms.nasa_firms?.config?.mock_mode ?? true}
                     onChange={(e) => setField("nasa_firms", "mock_mode", e.target.checked)} />
              Mock mod (gerçek MAP_KEY gelene kadar açık bırakın)
            </label>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("nasa_firms")} disabled={saving.nasa_firms} className="btn btn-ghost">
              <Save size={14}/> {saving.nasa_firms ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("nasa_firms")} disabled={testing.nasa_firms} className="btn btn-primary">
              {testing.nasa_firms ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.nasa_firms ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.nasa_firms && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="nasa_firms"/>
        </div>

        {/* ============ UP42 (VHR tasking pazaryeri) ============ */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center text-violet-400"><Plane size={20}/></div>
            <div>
              <h3 className="font-display text-lg">UP42 (Yüksek Çözünürlük Tasking)</h3>
              <p className="text-xs text-[var(--text-dim)]">Airbus/SkySat/ICEYE/Capella'ya tek noktadan erişim — nokta doğrulama görüntüsü talebi</p>
            </div>
          </div>
          <div className="space-y-3">
            <input className="input" placeholder="Client ID"
                   value={forms.up42?.config?.client_id || ""}
                   onChange={(e) => setField("up42", "client_id", e.target.value)} />
            <input className="input" type="password" placeholder="Client Secret"
                   value={forms.up42?.config?.client_secret || ""}
                   onChange={(e) => setField("up42", "client_secret", e.target.value)} data-testid="up42-key-input"/>
            <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <input type="checkbox"
                     checked={forms.up42?.config?.mock_mode ?? true}
                     onChange={(e) => setField("up42", "mock_mode", e.target.checked)} />
              Mock mod (gerçek sipariş oluşturmadan önce açık bırakın)
            </label>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => save("up42")} disabled={saving.up42} className="btn btn-ghost">
              <Save size={14}/> {saving.up42 ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button onClick={() => test("up42")} disabled={testing.up42} className="btn btn-primary">
              {testing.up42 ? <Loader2 size={14} className="animate-spin"/> : <Wifi size={14}/>}
              {testing.up42 ? "Test ediliyor…" : "Bağlantıyı Test Et"}
            </button>
          </div>
          {saved.up42 && <div className="text-xs text-[var(--primary)] mt-2 flex items-center gap-2"><CheckCircle2 size={14}/> Kaydedildi</div>}
          <TestBadge itype="up42"/>
        </div>

      </div>
    </div>
  );
}

// =====================================================================
// AI HASTALIK TESPİTİ — Foto yükle + Gemini Vision analiz
// =====================================================================
export function HastalikTespiti() {
  const [photo, setPhoto] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const fileRef = useRef();

  const loadHistory = () => api.get("/ai/disease-history").then((r) => setHistory(r.data));
  useEffect(loadHistory, []);

  function onSelect(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => setPhoto(ev.target.result);
    reader.readAsDataURL(f);
  }

  async function analyze() {
    if (!photo) return;
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post("/ai/disease-detect", { image_base64: photo });
      setResult(data);
      loadHistory();
    } catch (err) {
      alert("AI hatası: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  }

  // AI'dan dönen JSON cevabı parse et
  let parsed = null;
  if (result?.result) {
    try {
      const m = result.result.match(/\{[\s\S]*\}/);
      if (m) parsed = JSON.parse(m[0]);
    } catch {}
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="hastalik-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">AI · GEMINI VISION</div>
        <h1 className="font-display text-4xl">Bitki Hastalık Tespiti</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Tarladan çektiğiniz fotoğrafı yükleyin, yapay zekâ analiz etsin</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-6">
          <h3 className="font-display text-lg mb-4">Fotoğraf Yükle</h3>
          {!photo ? (
            <div onClick={() => fileRef.current?.click()} className="border-2 border-dashed border-[var(--border)] rounded-xl p-12 text-center cursor-pointer hover:border-[var(--primary)] transition-colors">
              <Upload size={32} className="mx-auto text-[var(--text-dim)] mb-3"/>
              <div className="text-sm">Fotoğraf seçmek için tıklayın</div>
              <div className="text-xs text-[var(--text-dim)] mt-1">JPG, PNG, WEBP — en az 200x200px</div>
            </div>
          ) : (
            <div>
              <img src={photo} alt="" className="w-full rounded-xl mb-3 max-h-[300px] object-contain bg-[var(--surface-2)]"/>
              <div className="flex gap-2">
                <button onClick={() => { setPhoto(null); setResult(null); }} className="btn btn-ghost flex-1 justify-center">Değiştir</button>
                <button onClick={analyze} disabled={loading} className="btn btn-primary flex-1 justify-center" data-testid="analyze-btn">
                  {loading ? <><Loader2 size={14} className="animate-spin"/> Analiz ediliyor…</> : <><Brain size={14}/> Analiz Et</>}
                </button>
              </div>
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" onChange={onSelect} className="hidden" data-testid="photo-input"/>
        </div>

        <div className="card p-6">
          <h3 className="font-display text-lg mb-4">AI Analiz Sonucu</h3>
          {!result && !loading && <div className="text-sm text-[var(--text-dim)] py-12 text-center">Henüz analiz yok</div>}
          {loading && <div className="text-sm text-[var(--text-dim)] py-12 text-center"><Loader2 size={24} className="animate-spin mx-auto mb-3"/>AI fotoğrafı inceliyor…</div>}
          {parsed && (
            <div className="space-y-3 fade-in">
              <div className="flex items-center justify-between p-3 bg-[var(--surface-2)] rounded-lg">
                <span className="text-xs text-[var(--text-dim)] uppercase">Bitki</span>
                <span className="font-medium">{parsed.plant || "—"}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-[var(--surface-2)] rounded-lg">
                <span className="text-xs text-[var(--text-dim)] uppercase">Hastalık</span>
                <span className="font-medium text-amber-400">{parsed.disease || "Tespit yok"}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-[var(--surface-2)] rounded-lg">
                <span className="text-xs text-[var(--text-dim)] uppercase">Şiddet</span>
                <span className={`badge ${parsed.severity === "yüksek" ? "badge-d" : parsed.severity === "orta" ? "badge-c" : "badge-a"}`}>{parsed.severity || "—"}</span>
              </div>
              <div className="p-3 bg-[var(--primary)]/10 border border-[var(--primary)]/30 rounded-lg">
                <div className="text-xs text-[var(--primary)] uppercase mb-1">Önerilen Aksiyon</div>
                <div className="text-sm">{parsed.action || "—"}</div>
              </div>
              <div className="text-xs text-[var(--text-dim)]">Aciliyet: {parsed.urgency || "—"}</div>
            </div>
          )}
          {result && !parsed && (
            <div className="text-sm whitespace-pre-wrap bg-[var(--surface-2)] p-4 rounded-lg">{result.result}</div>
          )}
        </div>
      </div>

      {history.length > 0 && (
        <div className="card mt-6 overflow-hidden">
          <div className="p-4 border-b border-[var(--border)]">
            <h3 className="font-display text-lg">Geçmiş Tespitler ({history.length})</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto scrollbar">
            {history.map((h) => (
              <div key={h.id} className="p-4 border-b border-[var(--border)] text-sm">
                <div className="text-xs text-[var(--text-dim)]">{new Date(h.created_at).toLocaleString("tr-TR")}</div>
                <div className="mt-1 line-clamp-2">{h.result?.substring(0, 200)}…</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// =====================================================================
// E-BELGE: Faturalar, İrsaliyeler, Kantar Kayıtları
// =====================================================================
export function EFaturalar() {
  const [docs, setDocs] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const load = () => api.get("/e-belge/invoices").then((r) => setDocs(r.data));
  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
  }, []);
  const total = docs.reduce((s, d) => s + (d.total || 0), 0);
  return (
    <div className="p-8 max-w-[1600px]" data-testid="efatura-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">E-BELGE</div>
        <h1 className="font-display text-4xl">E-Faturalar</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">{docs.length} fatura · Toplam: {fmt(total)} ₺ (KDV dahil)</p>
      </header>

      <QuickAddPanel
        title="Yeni Fatura"
        testId="einvoice-add"
        fields={[
          { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
            options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
          { name: "type", label: "Tip", type: "select", required: true,
            options: [{ value: "tohum", label: "Tohum" }, { value: "gübre", label: "Gübre" }, { value: "ilaç", label: "İlaç" }, { value: "kombine", label: "Kombine" }] },
          { name: "net_amount", label: "Net Tutar (₺)", type: "number", step: "0.01", required: true },
          { name: "date", label: "Tarih", type: "date" },
        ]}
        onSubmit={async (v) => {
          await api.post("/e-belge/invoices", { ...v, net_amount: Number(v.net_amount), date: v.date || null });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Fatura No</th><th className="p-4">Tarih</th><th className="p-4">Tip</th>
            <th className="p-4">Çiftçi</th><th className="p-4 text-right">Net</th>
            <th className="p-4 text-right">KDV</th><th className="p-4 text-right">Toplam</th>
            <th className="p-4">GİB</th>
          </tr></thead>
          <tbody>
            {docs.slice(0, 50).map((d) => (
              <tr key={d.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 font-mono text-xs">{d.invoice_no}</td>
                <td className="p-4 text-[var(--text-dim)]">{d.date}</td>
                <td className="p-4 capitalize">{d.type}</td>
                <td className="p-4">{d.farmer_name} <span className="text-xs text-[var(--text-dim)]">({d.member_no})</span></td>
                <td className="p-4 text-right font-mono">{fmt(d.net_amount)} ₺</td>
                <td className="p-4 text-right font-mono text-[var(--text-dim)]">{fmt(d.kdv)} ₺</td>
                <td className="p-4 text-right font-mono font-medium">{fmt(d.total)} ₺</td>
                <td className="p-4"><span className={`badge ${d.gib_status === "gönderildi" ? "badge-a" : "badge-c"}`}>{d.gib_status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Irsaliyeler() {
  const [docs, setDocs] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const load = () => api.get("/e-belge/irsaliyeler").then((r) => setDocs(r.data));
  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
  }, []);
  return (
    <div className="p-8 max-w-[1600px]" data-testid="irsaliye-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">E-BELGE</div>
        <h1 className="font-display text-4xl">E-İrsaliyeler</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">{docs.length} sevkiyat</p>
      </header>

      <QuickAddPanel
        title="Yeni İrsaliye"
        testId="irsaliye-add"
        fields={[
          { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
            options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
          { name: "product", label: "Ürün", required: true },
          { name: "quantity", label: "Miktar", type: "number", step: "0.1", required: true },
          { name: "unit", label: "Birim", type: "select", default: "kg",
            options: [{ value: "kg", label: "kg" }, { value: "lt", label: "lt" }, { value: "çuval", label: "çuval" }] },
          { name: "truck_plate", label: "Plaka" },
        ]}
        onSubmit={async (v) => { await api.post("/e-belge/irsaliyeler", { ...v, quantity: Number(v.quantity) }); load(); }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">İrsaliye No</th><th className="p-4">Tarih</th>
            <th className="p-4">Ürün</th><th className="p-4">Miktar</th>
            <th className="p-4">Çiftçi</th><th className="p-4">Plaka</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {docs.slice(0, 50).map((d) => (
              <tr key={d.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 font-mono text-xs">{d.irsaliye_no}</td>
                <td className="p-4 text-[var(--text-dim)]">{d.date}</td>
                <td className="p-4">{d.product}</td>
                <td className="p-4">{d.quantity} {d.unit}</td>
                <td className="p-4">{d.farmer_name}</td>
                <td className="p-4 font-mono">{d.truck_plate}</td>
                <td className="p-4"><span className={`badge ${d.status === "teslim edildi" ? "badge-a" : "badge-c"}`}>{d.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KantarKayitlari() {
  const [docs, setDocs] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const load = () => api.get("/kantar/records").then((r) => setDocs(r.data));
  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
  }, []);
  const totalNet = docs.reduce((s, d) => s + (d.net_ton || 0), 0);
  const avgPolar = docs.length ? (docs.reduce((s, d) => s + (d.polar_oran || 0), 0) / docs.length).toFixed(2) : 0;
  return (
    <div className="p-8 max-w-[1600px]" data-testid="kantar-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FABRİKA · KANTAR</div>
        <h1 className="font-display text-4xl">Kantar Kayıtları</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">{docs.length} tartı · {fmt(totalNet)} ton net · ortalama polar %{avgPolar}</p>
      </header>

      <QuickAddPanel
        title="Yeni Tartı Kaydı"
        testId="kantar-add"
        fields={[
          { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
            options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
          { name: "truck_plate", label: "Plaka", required: true },
          { name: "brut_ton", label: "Brüt (ton)", type: "number", step: "0.01", required: true },
          { name: "dara_ton", label: "Dara (ton)", type: "number", step: "0.01", required: true },
          { name: "polar_oran", label: "Polar Oranı (%)", type: "number", step: "0.01" },
          { name: "fire_pct", label: "Fire (%)", type: "number", step: "0.01" },
          { name: "kalite", label: "Kalite", type: "select", default: "B",
            options: [{ value: "A", label: "A" }, { value: "B", label: "B" }, { value: "C", label: "C" }] },
          { name: "kantar_no", label: "Kantar No", default: "K-1" },
        ]}
        onSubmit={async (v) => {
          if (Number(v.dara_ton) >= Number(v.brut_ton)) {
            throw { response: { data: { detail: "Dara, brüt ağırlıktan küçük olmalı" } } };
          }
          await api.post("/kantar/records", {
            ...v,
            brut_ton: Number(v.brut_ton), dara_ton: Number(v.dara_ton),
            polar_oran: v.polar_oran ? Number(v.polar_oran) : null,
            fire_pct: v.fire_pct ? Number(v.fire_pct) : 0,
          });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Fiş No</th><th className="p-4">Tartı Saati</th>
            <th className="p-4">Çiftçi</th><th className="p-4">Plaka</th>
            <th className="p-4 text-right">Brüt</th><th className="p-4 text-right">Dara</th>
            <th className="p-4 text-right">Net</th><th className="p-4 text-right">Polar</th>
            <th className="p-4">Kalite</th>
          </tr></thead>
          <tbody>
            {docs.slice(0, 50).map((d) => (
              <tr key={d.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 font-mono text-xs">{d.fis_no}</td>
                <td className="p-4 text-[var(--text-dim)] text-xs">{new Date(d.weighing_at).toLocaleString("tr-TR")}</td>
                <td className="p-4">{d.farmer_name}</td>
                <td className="p-4 font-mono text-xs">{d.truck_plate}</td>
                <td className="p-4 text-right">{d.brut_ton} t</td>
                <td className="p-4 text-right text-[var(--text-dim)]">{d.dara_ton} t</td>
                <td className="p-4 text-right font-medium text-[var(--primary)]">{d.net_ton} t</td>
                <td className="p-4 text-right">%{d.polar_oran}</td>
                <td className="p-4"><span className={`badge ${d.kalite === "A" ? "badge-a" : d.kalite === "B" ? "badge-b" : "badge-c"}`}>{d.kalite}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =====================================================================
// AUDIT LOG — Sistem aktiviteleri
// =====================================================================
export function AuditLog() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/audit/logs?limit=200").then((r) => setLogs(r.data.logs || [])); }, []);
  return (
    <div className="p-8 max-w-[1400px]" data-testid="audit-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">GÜVENLİK</div>
        <h1 className="font-display text-4xl">Audit Log</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">{logs.length} kayıt · Tüm sistem aktiviteleri</p>
      </header>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Tarih</th><th className="p-4">Aksiyon</th>
            <th className="p-4">Kullanıcı</th><th className="p-4">Rol</th>
            <th className="p-4">IP</th>
          </tr></thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 text-xs text-[var(--text-dim)]">{new Date(l.created_at).toLocaleString("tr-TR")}</td>
                <td className="p-4"><span className="badge badge-b">{l.action}</span></td>
                <td className="p-4 text-xs">{l.user_email}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{l.user_role}</td>
                <td className="p-4 font-mono text-xs text-[var(--text-dim)]">{l.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =====================================================================
// UYDU NDVI — Parsel için zaman serisi grafiği
// =====================================================================
export function UyduGorunutu() {
  const [parcels, setParcels] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [data, setData] = useState(null);
  const [regional, setRegional] = useState([]);
  const [iotSummary, setIotSummary] = useState(null);
  const [droneSummary, setDroneSummary] = useState(null);
  const [droneMissions, setDroneMissions] = useState([]);

  const loadIotDrone = () => {
    api.get("/iot/summary").then((r) => setIotSummary(r.data));
    api.get("/drone/summary").then((r) => setDroneSummary(r.data));
    api.get("/drone/missions").then((r) => setDroneMissions(r.data.slice(0, 8)));
  };

  useEffect(() => {
    api.get("/parcels?limit=100").then((r) => {
      setParcels(r.data);
      if (r.data.length > 0) setSelectedId(r.data[0].id);
    });
    api.get("/satellite/regional-overview").then((r) => setRegional(r.data));
    loadIotDrone();
  }, []);

  useEffect(() => {
    if (selectedId) api.get(`/satellite/ndvi/${selectedId}`).then((r) => setData(r.data));
  }, [selectedId]);

  return (
    <div className="p-8 max-w-[1600px]" data-testid="uydu-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SENTINEL HUB · NDVI</div>
        <h1 className="font-display text-4xl">Uydu Görüntüleri</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Parsel sağlığını uydu NDVI verisiyle takip et — <span className="text-amber-400">DEMO MOD</span></p>
      </header>

      {/* IoT & Drone özet — Sprint 2 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="card p-4">
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]"><Radio size={13} className="text-violet-400"/> AKTİF SENSÖR</div>
          <div className="font-display text-2xl mt-1">{iotSummary ? `${iotSummary.active_sensors} / ${iotSummary.total_sensors}` : "…"}</div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]"><Radio size={13} className="text-amber-400"/> DÜŞÜK PİL</div>
          <div className="font-display text-2xl mt-1">{iotSummary ? iotSummary.low_battery_sensors : "…"}</div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]"><Plane size={13} className="text-indigo-400"/> TOPLAM DRONE GÖREVİ</div>
          <div className="font-display text-2xl mt-1">{droneSummary ? droneSummary.total_missions : "…"}</div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]"><Plane size={13} className="text-red-400"/> BULGULU GÖREV</div>
          <div className="font-display text-2xl mt-1">{droneSummary ? droneSummary.missions_with_findings : "…"}</div>
        </div>
      </div>

      {droneMissions.length > 0 && (
        <div className="card p-4 mb-6">
          <h3 className="font-display text-lg mb-3">Son Drone Görevleri</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {droneMissions.map((m) => (
              <div key={m.id} className="flex items-center justify-between text-sm p-2.5 rounded-lg bg-[var(--surface-2)]">
                <div>
                  <span className="font-mono text-xs text-[var(--text-dim)] mr-2">{m.mission_code}</span>
                  <span className="text-xs">{m.parcel_code}</span>
                </div>
                <span className={`badge ${m.finding_type === "genel_tarama" ? "badge-a" : m.severity === "yüksek" ? "badge-d" : "badge-c"}`}>
                  {m.finding_type.replace("_", " ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <QuickAddPanel
          title="IoT Sensör Kaydet"
          testId="iot-sensor-add"
          fields={[
            { name: "parcel_id", label: "Parsel", type: "select", required: true,
              options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
            { name: "type", label: "Tip", type: "select", default: "nem_sicaklik",
              options: [
                { value: "nem_sicaklik", label: "Nem/Sıcaklık" },
                { value: "toprak_nemi", label: "Toprak Nemi" },
                { value: "hava_istasyonu", label: "Hava İstasyonu" },
              ] },
            { name: "sensor_code", label: "Sensör Kodu (opsiyonel, boşsa otomatik)" },
          ]}
          onSubmit={async (v) => {
            await api.post("/iot/sensors", { ...v, sensor_code: v.sensor_code || null });
            loadIotDrone();
          }}
        />
        <QuickAddPanel
          title="Drone Görevi Kaydet"
          testId="drone-mission-add"
          fields={[
            { name: "parcel_id", label: "Parsel", type: "select", required: true,
              options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
            { name: "flight_date", label: "Uçuş Tarihi", type: "date", required: true },
            { name: "pilot", label: "Pilot", required: true },
            { name: "altitude_m", label: "İrtifa (m)", type: "number", default: 80 },
            { name: "finding_type", label: "Bulgu Tipi", type: "select", required: true,
              options: [
                { value: "hastalık_tespiti", label: "Hastalık Tespiti" },
                { value: "yabancı_ot", label: "Yabancı Ot" },
                { value: "su_stresi", label: "Su Stresi" },
                { value: "genel_tarama", label: "Genel Tarama" },
              ] },
            { name: "severity", label: "Şiddet", type: "select", default: "yok",
              options: [{ value: "yok", label: "Yok" }, { value: "düşük", label: "Düşük" }, { value: "orta", label: "Orta" }, { value: "yüksek", label: "Yüksek" }] },
            { name: "notes", label: "Notlar (boş bırakılırsa otomatik doldurulur)", type: "textarea", span2: true },
          ]}
          onSubmit={async (v) => {
            await api.post("/drone/missions", { ...v, altitude_m: Number(v.altitude_m) || 80, notes: v.notes || null });
            loadIotDrone();
          }}
        />
      </div>

      {/* Bölge özeti */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {regional.slice(0, 4).map((r) => (
          <div key={r.region_id} className="card p-4">
            <div className="text-xs text-[var(--text-dim)]">{r.region_name}</div>
            <div className="font-display text-2xl mt-1" style={{ color: r.avg_ndvi > 0.65 ? "#4ade80" : r.avg_ndvi > 0.5 ? "#fbbf24" : "#ef4444" }}>
              {r.avg_ndvi}
            </div>
            <div className="text-xs text-[var(--text-dim)]">{r.scanned_parcels} parsel · {r.anomaly_count} anomali</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-4 max-h-[500px] overflow-y-auto scrollbar">
          <h3 className="font-display text-lg mb-3">Parsel Seç</h3>
          {parcels.map((p) => (
            <button key={p.id} onClick={() => setSelectedId(p.id)}
                    className={`w-full text-left p-3 rounded-lg mb-2 border transition-colors ${selectedId === p.id ? "border-[var(--primary)] bg-[var(--primary)]/5" : "border-[var(--border)] hover:border-[var(--primary)]/40"}`}>
              <div className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</div>
              <div className="text-sm mt-1">{p.name}</div>
            </button>
          ))}
        </div>

        <div className="card p-5 lg:col-span-2">
          {data ? (
            <>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="font-mono text-xs text-[var(--text-dim)]">{data.parcel_code}</div>
                  <h3 className="font-display text-lg mt-1">{data.area_dekar} dekar</h3>
                </div>
                <div className="text-right">
                  <div className="text-xs text-[var(--text-dim)] uppercase">Son NDVI</div>
                  <div className="font-display text-3xl" style={{ color: data.health.color }}>{data.latest_ndvi}</div>
                  <div className="text-xs" style={{ color: data.health.color }}>{data.health.label}</div>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.time_series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
                  <XAxis dataKey="date" stroke="#97a8a0" style={{ fontSize: 11 }}/>
                  <YAxis stroke="#97a8a0" domain={[0, 1]}/>
                  <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
                  <Line type="monotone" dataKey="ndvi" stroke={data.health.color} strokeWidth={3} dot={{ r: 4 }}/>
                </LineChart>
              </ResponsiveContainer>
              {data.anomalies.length > 0 && (
                <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-amber-400">
                  ⚠️ {data.anomalies.length} anomali tespit edildi: {data.anomalies[0].type} ({data.anomalies[0].date})
                </div>
              )}
              <div className="text-[10px] text-[var(--text-dim)] mt-3">{data.data_source}</div>
            </>
          ) : <div className="text-[var(--text-dim)] text-center py-12">Parsel seçin</div>}
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// SAHA PWA — Mobil saha ziyaret raporu (ziraat mühendisi)
// =====================================================================
const OFFLINE_QUEUE_KEY = "tabsis_offline_visits";

function readQueue() {
  try { return JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY) || "[]"); } catch { return []; }
}
function writeQueue(q) { localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(q)); }

export function SahaPWA() {
  const [parcels, setParcels] = useState([]);
  const [visits, setVisits] = useState([]);
  const [form, setForm] = useState({ parcel_id: "", farmer_id: "", notes: "", observation_type: "genel" });
  const [photo, setPhoto] = useState(null);
  const [analyzeWithAi, setAnalyzeWithAi] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [gps, setGps] = useState(null);
  const [lastAiResult, setLastAiResult] = useState(null);
  const [queueCount, setQueueCount] = useState(readQueue().length);
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const fileRef = useRef();

  const loadVisits = () => api.get("/field/visits").then((r) => setVisits(r.data));

  async function flushQueue() {
    const queue = readQueue();
    if (queue.length === 0) return;
    const remaining = [];
    for (const item of queue) {
      try {
        await api.post("/field/visits", item);
      } catch {
        remaining.push(item);          // hâlâ gönderilemedi, kuyrukta kalsın
      }
    }
    writeQueue(remaining);
    setQueueCount(remaining.length);
    if (remaining.length < queue.length) loadVisits();
  }

  useEffect(() => {
    api.get("/parcels?limit=200").then((r) => setParcels(r.data));
    loadVisits();
    // GPS al
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => setGps({ lat: 39.5, lng: 33.5 })  // fallback Türkiye merkezi
      );
    }
    // Bağlantı geri gelince kuyruğu otomatik gönder (offline-first PWA davranışı)
    const onOnline = () => { setIsOnline(true); flushQueue(); };
    const onOffline = () => setIsOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    flushQueue();  // sayfa açılışında da dene
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onParcelChange(parcel_id) {
    const p = parcels.find((x) => x.id === parcel_id);
    setForm({ ...form, parcel_id, farmer_id: p?.farmer_id || "" });
  }

  function onPhotoSelect(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => setPhoto(ev.target.result);
    reader.readAsDataURL(f);
  }

  async function submit(e) {
    e.preventDefault();
    if (!gps) { alert("GPS bekleniyor..."); return; }
    setSubmitting(true);
    setLastAiResult(null);
    const payload = {
      ...form,
      gps_lat: gps.lat,
      gps_lng: gps.lng,
      photo_base64: photo,
      analyze_with_ai: !!(photo && analyzeWithAi),
      client_id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      client_created_at: new Date().toISOString(),
    };
    try {
      const r = await api.post("/field/visits", payload);
      if (r.data.ai_analysis) setLastAiResult(r.data.ai_analysis);
      await loadVisits();
      setForm({ parcel_id: "", farmer_id: "", notes: "", observation_type: "genel" });
      setPhoto(null);
      setAnalyzeWithAi(false);
    } catch (err) {
      // Ağ hatası (offline) → kuyruğa al, kaybolmasın. Backend zaten
      // client_id ile dedup yapıyor, bağlantı gelince güvenle tekrar denenir.
      const isNetworkError = !err.response;
      if (isNetworkError) {
        const q = readQueue();
        q.push(payload);
        writeQueue(q);
        setQueueCount(q.length);
        setForm({ parcel_id: "", farmer_id: "", notes: "", observation_type: "genel" });
        setPhoto(null);
        setAnalyzeWithAi(false);
        alert("Bağlantı yok — rapor cihazda kuyruğa alındı, bağlantı gelince otomatik gönderilecek.");
      } else {
        alert("Hata: " + (err.response?.data?.detail || err.message));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const URGENCY_COLORS = { yüksek: "#ef4444", orta: "#fb923c", düşük: "#4ade80" };

  return (
    <div className="p-4 md:p-8 max-w-[1200px]" data-testid="saha-page">
      <header className="mb-4">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M07 · SAHA MOBİL</div>
        <h1 className="font-display text-3xl md:text-4xl">Saha Ziyaret Raporu</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1 flex items-center gap-3 flex-wrap">
          {gps ? <span className="text-[var(--primary)]">📍 GPS: {gps.lat.toFixed(4)}, {gps.lng.toFixed(4)}</span> : "📍 GPS alınıyor..."}
          <span className={isOnline ? "text-[var(--text-dim)]" : "text-amber-400"}>
            {isOnline ? "🟢 Çevrimiçi" : "🟠 Çevrimdışı"}
          </span>
          {queueCount > 0 && (
            <span className="text-amber-400">📤 {queueCount} rapor gönderim bekliyor</span>
          )}
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <form onSubmit={submit} className="card p-5 space-y-3">
          <h3 className="font-display text-lg mb-2">Yeni Ziyaret</h3>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">PARSEL</label>
            <select className="input" value={form.parcel_id} onChange={(e) => onParcelChange(e.target.value)} required data-testid="saha-parcel">
              <option value="">Seç...</option>
              {parcels.slice(0, 100).map((p) => <option key={p.id} value={p.id}>{p.parcel_code} — {p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">GÖZLEM TİPİ</label>
            <select className="input" value={form.observation_type} onChange={(e) => setForm({...form, observation_type: e.target.value})}>
              <option value="genel">Genel kontrol</option>
              <option value="hastalık">Hastalık şüphesi</option>
              <option value="sulama">Sulama sorunu</option>
              <option value="zararlı">Zararlı / haşere</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">NOTLAR</label>
            <textarea className="input" rows="4" value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})}
                      placeholder="Tarlada gözlemlediklerinizi yazın..." required data-testid="saha-notes"/>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">FOTOĞRAF (opsiyonel)</label>
            {photo ? (
              <div>
                <img src={photo} alt="" className="w-full rounded-lg max-h-[200px] object-cover mb-2"/>
                <button type="button" onClick={() => { setPhoto(null); setAnalyzeWithAi(false); }} className="btn btn-ghost text-xs">Kaldır</button>
              </div>
            ) : (
              <button type="button" onClick={() => fileRef.current?.click()} className="btn btn-ghost w-full justify-center">
                <Camera size={14}/> Fotoğraf çek/seç
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*" capture="environment" onChange={onPhotoSelect} className="hidden"/>
          </div>
          {photo && (
            <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <input type="checkbox" checked={analyzeWithAi} onChange={(e) => setAnalyzeWithAi(e.target.checked)} data-testid="saha-ai-toggle"/>
              <Brain size={14} className="text-purple-400"/> Fotoğrafı AI ile analiz et (hastalık/zararlı tespiti)
            </label>
          )}
          <button type="submit" disabled={submitting || !gps} className="btn btn-primary w-full justify-center" data-testid="saha-submit">
            {submitting ? (analyzeWithAi ? "AI analiz ediyor…" : "Kaydediliyor...") : "📝 Raporu Kaydet"}
          </button>

          {lastAiResult && !lastAiResult.error && (
            <div className="p-3 rounded-lg border" style={{
              borderColor: `${URGENCY_COLORS[lastAiResult.urgency] || "#97a8a0"}44`,
              background: `${URGENCY_COLORS[lastAiResult.urgency] || "#97a8a0"}11`,
            }}>
              <div className="text-xs font-medium mb-1 flex items-center gap-1.5">
                <Brain size={13}/> AI Analiz Sonucu
              </div>
              <div className="text-xs space-y-0.5 text-[var(--text-dim)]">
                <div>Bitki: <span className="text-[var(--text)]">{lastAiResult.plant}</span></div>
                <div>Tespit: <span className="text-[var(--text)]">{lastAiResult.disease}</span></div>
                <div>Şiddet: <span className="text-[var(--text)]">{lastAiResult.severity}</span></div>
                <div>Önerilen aksiyon: <span className="text-[var(--text)]">{lastAiResult.action}</span></div>
              </div>
            </div>
          )}
          {lastAiResult?.error && (
            <div className="text-xs text-amber-400 p-2">⚠️ {lastAiResult.error}</div>
          )}
        </form>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-3">Son Ziyaretler ({visits.length})</h3>
          <div className="space-y-3 max-h-[500px] overflow-y-auto scrollbar">
            {visits.map((v) => (
              <div key={v.id} className="p-3 bg-[var(--surface-2)] rounded-lg">
                <div className="flex items-start justify-between mb-1">
                  <span className={`badge ${v.observation_type === "hastalık" ? "badge-d" : v.observation_type === "zararlı" ? "badge-c" : "badge-a"}`}>{v.observation_type}</span>
                  <span className="text-xs text-[var(--text-dim)]">{new Date(v.created_at).toLocaleDateString("tr-TR")}</span>
                </div>
                <div className="text-sm mt-1">{v.notes}</div>
                <div className="text-xs text-[var(--text-dim)] mt-1 flex items-center gap-1">
                  <MapPin size={10}/> {v.gps_lat?.toFixed(3)}, {v.gps_lng?.toFixed(3)}
                </div>
                {v.ai_analysis && !v.ai_analysis.error && (
                  <div className="text-xs mt-2 pt-2 border-t border-[var(--border)] flex items-center gap-1.5 text-purple-400">
                    <Brain size={11}/> {v.ai_analysis.disease} · {v.ai_analysis.severity}
                  </div>
                )}
              </div>
            ))}
            {visits.length === 0 && <div className="text-center text-[var(--text-dim)] py-8 text-sm">Henüz ziyaret yok</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// AI COPILOT — Doğal dil ile parsel sorgusu
// =====================================================================
const RISK_COLORS_COPILOT = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };
const COPILOT_SUGGESTIONS = [
  "Çumra'daki en riskli 20 parseli göster",
  "Hasadı yaklaşan pancarları listele",
  "Konya'daki sağlıklı parseller",
  "En yüksek verimli 10 parsel",
];

export function AICopilot() {
  const navFn = useNavigate();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);

  async function ask(q) {
    const text = (q ?? query).trim();
    if (!text) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await api.post("/ai/copilot", { query: text });
      setResult(r.data);
      setHistory((h) => [{ query: text, summary: r.data.summary, count: r.data.result_count }, ...h].slice(0, 8));
      setQuery("");
    } catch (e) {
      setError(e.response?.data?.detail || "Sorgu işlenemedi, lütfen tekrar deneyin.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-[1200px]" data-testid="copilot-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">TABSIS AI</div>
        <h1 className="font-display text-4xl">AI Copilot</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Parsel verinizi doğal dille sorgulayın — AI sadece filtre üretir, sonuçlar her zaman gerçek veritabanından gelir.
        </p>
      </header>

      <div className="card p-5 mb-4">
        <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="Örn. Çumra'daki en riskli 20 parseli göster"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="copilot-input"
          />
          <button type="submit" disabled={loading || !query.trim()} className="btn btn-primary" data-testid="copilot-ask-btn">
            {loading ? <Loader2 size={16} className="animate-spin"/> : <Brain size={16}/>}
            {loading ? "Düşünüyor…" : "Sor"}
          </button>
        </form>
        <div className="flex flex-wrap gap-2 mt-3">
          {COPILOT_SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={loading}
                    className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-dim)] hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors">
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="card p-4 mb-4 border border-red-500/30 bg-red-500/5 text-sm text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className="card p-5 mb-4">
          <div className="mb-4">
            <div className="text-sm">{result.summary}</div>
            <div className="text-xs text-[var(--text-dim)] mt-1">
              {result.result_count} sonuç · {result.ai_powered ? "AI tarafından yorumlandı" : "Anahtar kelime eşleştirmesi (AI servisi yapılandırılmamış)"}
            </div>
          </div>

          <div className="space-y-2 max-h-[420px] overflow-y-auto scrollbar">
            {result.parcels.map((p) => {
              const color = RISK_COLORS_COPILOT[p.risk_level] || "#97a8a0";
              return (
                <div key={p.id} onClick={() => navFn(`/parseller/${p.id}`)}
                     className="flex items-center justify-between p-3 rounded-lg bg-[var(--surface-2)] cursor-pointer hover:opacity-80 transition-opacity">
                  <div>
                    <div className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</div>
                    <div className="text-sm mt-0.5">{p.name}</div>
                    <div className="text-xs text-[var(--text-dim)] mt-0.5">{p.village} · {p.area_dekar} da</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs px-2 py-0.5 rounded font-medium inline-block" style={{ background: `${color}22`, color }}>
                      {p.risk_label || p.risk_level}
                    </div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">NDVI {p.ndvi_latest}</div>
                  </div>
                </div>
              );
            })}
            {result.parcels.length === 0 && (
              <div className="text-center text-[var(--text-dim)] py-8">Bu sorguya uyan parsel bulunamadı.</div>
            )}
          </div>
        </div>
      )}

      {history.length > 1 && (
        <div className="card p-4">
          <h3 className="font-display text-base mb-2 text-[var(--text-dim)]">Önceki Sorgular</h3>
          <div className="space-y-1">
            {history.slice(1).map((h, i) => (
              <button key={i} onClick={() => ask(h.query)} className="w-full text-left text-xs text-[var(--text-dim)] hover:text-[var(--primary)] py-1">
                "{h.query}" → {h.count} sonuç
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
