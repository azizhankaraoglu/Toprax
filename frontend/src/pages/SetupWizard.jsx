import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Wheat, CheckCircle2, Circle, Loader2, ShieldCheck, Building2,
  UserPlus, Mail, KeyRound, PartyPopper, ArrowRight, SkipForward,
} from "lucide-react";

// PR-02: Kurulum Sihirbazı — DİKKAT: bu sayfa yeni iş mantığı yazmaz,
// mevcut uçları (tenants.py, integrations.py, platform_core.py) sırayla
// çağıran bir orkestrasyon katmanıdır (bkz. backend/setup_wizard.py).
//
// Kasıtlı olarak paylaşılan api.js istemcisini (localStorage token
// interceptor'lı) KULLANMIYORUZ -- sihirbaz sırasında platform_admin ve
// yeni oluşturulan tenant admin'i arasında iki ayrı geçici token ile
// çalışıyoruz, bunlar mevcut oturumla (varsa) karışmamalı.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const raw = axios.create({ baseURL: API });

const STEPS = [
  { key: "login", label: "Platform Girişi", icon: ShieldCheck },
  { key: "tenant", label: "Kurum Oluştur", icon: Building2 },
  { key: "admin", label: "Süper Admin", icon: UserPlus },
  { key: "integration", label: "E-Posta (SMTP)", icon: Mail },
  { key: "license", label: "Lisans", icon: KeyRound },
  { key: "finish", label: "Bitir", icon: PartyPopper },
];

function StepDots({ stepIndex }) {
  return (
    <div className="flex items-center gap-2 mb-8 flex-wrap">
      {STEPS.map((s, i) => {
        const Icon = s.icon;
        const done = i < stepIndex;
        const active = i === stepIndex;
        return (
          <div key={s.key} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
                active ? "bg-[var(--primary)] text-[#052e16] border-[var(--primary)]"
                : done ? "bg-[var(--primary)]/15 text-[var(--primary)] border-[var(--primary)]/30"
                : "bg-transparent text-[var(--text-dim)] border-[var(--border)]"
              }`}
            >
              {done ? <CheckCircle2 size={14} /> : <Icon size={14} />}
              {s.label}
            </div>
            {i < STEPS.length - 1 && <div className="w-4 h-px bg-[var(--border)]" />}
          </div>
        );
      })}
    </div>
  );
}

export default function SetupWizard() {
  const nav = useNavigate();
  const [checking, setChecking] = useState(true);
  const [alreadyDone, setAlreadyDone] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [platformToken, setPlatformToken] = useState("");
  const [platformLogin, setPlatformLogin] = useState({ email: "", password: "" });

  const [tenantForm, setTenantForm] = useState({ name: "", contact_email: "", contact_phone: "", plan: "standard" });
  const [tenantId, setTenantId] = useState("");

  const [adminForm, setAdminForm] = useState({ admin_email: "", admin_password: "", admin_full_name: "" });
  const [tenantToken, setTenantToken] = useState("");

  const [smtp, setSmtp] = useState({ host: "", port: "587", username: "", password: "", from_address: "" });
  const [smtpTestResult, setSmtpTestResult] = useState(null);

  const [license, setLicense] = useState({ plan: "standard", expires_at: "" });

  useEffect(() => {
    raw.get("/setup/status")
      .then(({ data }) => setAlreadyDone(!!data.completed))
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);

  function authHeader(token) {
    return { headers: { Authorization: `Bearer ${token}` } };
  }

  async function doPlatformLogin(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const { data } = await raw.post("/auth/login", platformLogin);
      if (data.user.role !== "platform_admin") {
        setError("Bu hesap platform yöneticisi değil. .env dosyasındaki PLATFORM_ADMIN_EMAIL/PASSWORD ile giriş yapın.");
        return;
      }
      setPlatformToken(data.token);
      setStepIndex(1);
    } catch (err) {
      setError(err.response?.data?.detail || "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  }

  async function doCreateTenant(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const { data } = await raw.post("/platform/tenants", tenantForm, authHeader(platformToken));
      setTenantId(data.id);
      setAdminForm((f) => ({ ...f, admin_email: tenantForm.contact_email }));
      setStepIndex(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Kurum oluşturulamadı");
    } finally {
      setLoading(false);
    }
  }

  async function doCreateAdmin(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await raw.post(`/platform/tenants/${tenantId}/bootstrap-admin`, adminForm, authHeader(platformToken));
      // yeni admin ile giriş yap (SMTP adımı için tenant'ın kendi token'ı gerekir)
      const { data: loginData } = await raw.post("/auth/login", {
        email: adminForm.admin_email, password: adminForm.admin_password,
      });
      setTenantToken(loginData.token);
      setStepIndex(3);
    } catch (err) {
      setError(err.response?.data?.detail || "Süper admin oluşturulamadı");
    } finally {
      setLoading(false);
    }
  }

  async function doSaveSmtp(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    setSmtpTestResult(null);
    try {
      await raw.put("/integrations/email", {
        provider: "smtp",
        config: smtp,
        enabled: true,
      }, authHeader(tenantToken));
      const { data } = await raw.post("/integrations/email/test", {}, authHeader(tenantToken));
      setSmtpTestResult(data);
      setStepIndex(4);
    } catch (err) {
      setError(err.response?.data?.detail || "E-posta ayarı kaydedilemedi");
    } finally {
      setLoading(false);
    }
  }

  function skipSmtp() {
    setError(""); setStepIndex(4);
  }

  async function doCreateLicense(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await raw.post("/licenses", {
        scope_type: "tenant",
        scope_value: tenantId,
        plan: license.plan,
        expires_at: license.expires_at || null,
        note: "Kurulum sihirbazı ile oluşturuldu",
      }, authHeader(platformToken));
      setStepIndex(5);
    } catch (err) {
      setError(err.response?.data?.detail || "Lisans oluşturulamadı");
    } finally {
      setLoading(false);
    }
  }

  async function doFinish() {
    setError(""); setLoading(true);
    try {
      await raw.post("/setup/complete", { tenant_id: tenantId }, authHeader(platformToken));
      // Sihirbazın kendi geçici token'larını temizle, gerçek oturum
      // /login üzerinden başlasın.
      setTimeout(() => nav("/login"), 1500);
    } catch (err) {
      setError(err.response?.data?.detail || "Sihirbaz tamamlanamadı");
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)]">
        <Loader2 className="animate-spin text-[var(--primary)]" size={28} />
      </div>
    );
  }

  if (alreadyDone) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] px-4">
        <div className="max-w-md text-center">
          <ShieldCheck className="mx-auto mb-4 text-[var(--primary)]" size={40} />
          <h1 className="font-display text-2xl text-white mb-2">Kurulum zaten tamamlanmış</h1>
          <p className="text-[var(--text-dim)] mb-6">
            Bu sihirbaz bir kez çalıştırılabilir (güvenlik). Sisteme giriş yapmak için devam edin.
          </p>
          <button
            onClick={() => nav("/login")}
            className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2"
          >
            Giriş sayfasına git <ArrowRight size={16} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] grain px-4 py-10 flex justify-center">
      <div className="w-full max-w-2xl">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-[var(--primary)] flex items-center justify-center">
            <Wheat size={22} className="text-[#052e16]" />
          </div>
          <div>
            <div className="font-display text-xl text-white">Toprax Kurulum Sihirbazı</div>
            <div className="text-xs text-[var(--text-dim)]">İlk kurulum — bu adımlar bir kez yapılır</div>
          </div>
        </div>

        <StepDots stepIndex={stepIndex} />

        {error && (
          <div className="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          {stepIndex === 0 && (
            <form onSubmit={doPlatformLogin} className="space-y-4">
              <h2 className="text-white font-medium mb-1">1) Platform Yöneticisi Girişi</h2>
              <p className="text-xs text-[var(--text-dim)] mb-3">
                .env dosyanızdaki PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD ile giriş yapın.
              </p>
              <input required type="email" placeholder="platform@toprax.local" value={platformLogin.email}
                onChange={(e) => setPlatformLogin((f) => ({ ...f, email: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input required type="password" placeholder="Şifre" value={platformLogin.password}
                onChange={(e) => setPlatformLogin((f) => ({ ...f, password: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <button disabled={loading} className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowRight size={16} />} Devam Et
              </button>
            </form>
          )}

          {stepIndex === 1 && (
            <form onSubmit={doCreateTenant} className="space-y-4">
              <h2 className="text-white font-medium mb-1">2) İlk Kurumunuzu (Tenant) Oluşturun</h2>
              <input required placeholder="Kurum adı (örn. Konya Şeker Kooperatifi)" value={tenantForm.name}
                onChange={(e) => setTenantForm((f) => ({ ...f, name: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input required type="email" placeholder="İletişim e-postası" value={tenantForm.contact_email}
                onChange={(e) => setTenantForm((f) => ({ ...f, contact_email: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input placeholder="Telefon (opsiyonel)" value={tenantForm.contact_phone}
                onChange={(e) => setTenantForm((f) => ({ ...f, contact_phone: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <select value={tenantForm.plan} onChange={(e) => setTenantForm((f) => ({ ...f, plan: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white">
                <option value="standard">Standart</option>
                <option value="kurumsal">Kurumsal</option>
                <option value="deneme">Deneme</option>
              </select>
              <button disabled={loading} className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowRight size={16} />} Kurumu Oluştur
              </button>
            </form>
          )}

          {stepIndex === 2 && (
            <form onSubmit={doCreateAdmin} className="space-y-4">
              <h2 className="text-white font-medium mb-1">3) İlk Süper Admin Kullanıcısı</h2>
              <input required type="email" placeholder="E-posta" value={adminForm.admin_email}
                onChange={(e) => setAdminForm((f) => ({ ...f, admin_email: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input required placeholder="Ad Soyad" value={adminForm.admin_full_name}
                onChange={(e) => setAdminForm((f) => ({ ...f, admin_full_name: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input required type="password" placeholder="Şifre (güçlü bir şifre seçin)" value={adminForm.admin_password}
                onChange={(e) => setAdminForm((f) => ({ ...f, admin_password: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <button disabled={loading} className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowRight size={16} />} Oluştur ve Devam Et
              </button>
            </form>
          )}

          {stepIndex === 3 && (
            <form onSubmit={doSaveSmtp} className="space-y-4">
              <h2 className="text-white font-medium mb-1">4) E-Posta (SMTP) Ayarı — opsiyonel</h2>
              <p className="text-xs text-[var(--text-dim)] mb-3">
                Bildirim/rapor e-postaları için. Şimdi atlayıp Ayarlar &gt; Entegrasyonlar'dan sonra da yapılandırabilirsiniz.
              </p>
              <input placeholder="SMTP sunucusu (örn. smtp.office365.com)" value={smtp.host}
                onChange={(e) => setSmtp((f) => ({ ...f, host: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <div className="grid grid-cols-2 gap-3">
                <input placeholder="Port" value={smtp.port}
                  onChange={(e) => setSmtp((f) => ({ ...f, port: e.target.value }))}
                  className="px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
                <input placeholder="Gönderen adresi" value={smtp.from_address}
                  onChange={(e) => setSmtp((f) => ({ ...f, from_address: e.target.value }))}
                  className="px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              </div>
              <input placeholder="Kullanıcı adı" value={smtp.username}
                onChange={(e) => setSmtp((f) => ({ ...f, username: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <input type="password" placeholder="Şifre / uygulama parolası" value={smtp.password}
                onChange={(e) => setSmtp((f) => ({ ...f, password: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              {smtpTestResult && (
                <div className="text-xs px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-[var(--text-dim)]">
                  Test sonucu: {JSON.stringify(smtpTestResult)}
                </div>
              )}
              <div className="flex gap-3">
                <button disabled={loading} className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                  {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowRight size={16} />} Kaydet, Test Et ve Devam Et
                </button>
                <button type="button" onClick={skipSmtp} className="px-5 py-2.5 rounded-lg border border-[var(--border)] text-[var(--text-dim)] inline-flex items-center gap-2">
                  <SkipForward size={16} /> Şimdilik Atla
                </button>
              </div>
            </form>
          )}

          {stepIndex === 4 && (
            <form onSubmit={doCreateLicense} className="space-y-4">
              <h2 className="text-white font-medium mb-1">5) Lisans</h2>
              <select value={license.plan} onChange={(e) => setLicense((f) => ({ ...f, plan: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white">
                <option value="trial">Deneme (trial)</option>
                <option value="standard">Standart</option>
                <option value="premium">Premium</option>
              </select>
              <input type="date" value={license.expires_at}
                onChange={(e) => setLicense((f) => ({ ...f, expires_at: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
              <button disabled={loading} className="px-5 py-2.5 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <ArrowRight size={16} />} Lisansı Oluştur
              </button>
            </form>
          )}

          {stepIndex === 5 && (
            <div className="text-center py-6">
              <PartyPopper className="mx-auto mb-4 text-[var(--primary)]" size={40} />
              <h2 className="text-white font-medium mb-2">Kurulum tamamlanmak üzere</h2>
              <p className="text-[var(--text-dim)] text-sm mb-6">
                "Bitir" butonuna bastığınızda sihirbaz kilitlenir ve bir daha çalıştırılamaz.
              </p>
              <button onClick={doFinish} disabled={loading} className="px-6 py-3 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />} Kurulumu Bitir
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
