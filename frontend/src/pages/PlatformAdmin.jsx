import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import Drawer from "@/components/Drawer";
import {
  Building2, LogOut, Users, Sprout, LayoutGrid, BarChart3, HeartPulse,
  LogIn, Trash2, Puzzle, KeyRound, AlertTriangle, CheckCircle2,
} from "lucide-react";

const TABS = [
  { id: "tenants", label: "Tenantlar", icon: LayoutGrid },
  { id: "stats", label: "İstatistikler", icon: BarChart3 },
  { id: "health", label: "Sistem Sağlığı", icon: HeartPulse },
];

const MODULE_ORDER = ["farmer", "parcel", "production", "factory", "ufyd", "communication", "lms", "gis", "ai"];

const LICENSE_FIELDS = [
  { key: "user_limit", label: "Kullanıcı Limiti" },
  { key: "parcel_limit", label: "Parsel Limiti" },
  { key: "storage_limit_mb", label: "Depolama Limiti (MB)" },
  { key: "ai_limit", label: "AI İsteği Limiti (aylık)" },
  { key: "sms_limit", label: "SMS Limiti (aylık)" },
  { key: "whatsapp_limit", label: "WhatsApp Limiti (aylık)" },
];

function KPI({ label, value, accent }) {
  return (
    <div className="card p-4">
      <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase mb-1">{label}</div>
      <div className={`font-display text-2xl ${accent || ""}`}>{value ?? "—"}</div>
    </div>
  );
}

export default function PlatformAdmin() {
  const [view, setView] = useState("tenants");
  const [tenants, setTenants] = useState(null);
  const [error, setError] = useState("");
  const [bootstrapFor, setBootstrapFor] = useState(null);
  const [bootstrapResult, setBootstrapResult] = useState(null);

  const [moduleTenant, setModuleTenant] = useState(null);
  const [modules, setModules] = useState([]);

  const [licenseTenant, setLicenseTenant] = useState(null);
  const [licenseData, setLicenseData] = useState(null);
  const [licenseForm, setLicenseForm] = useState({});

  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [apiStats, setApiStats] = useState(null);

  const load = () => api.get("/god-mode/tenants")
    .then((r) => setTenants(r.data))
    .catch((e) => setError(e.response?.data?.detail || "Yüklenemedi"));

  useEffect(load, []);

  useEffect(() => {
    if (view === "stats") api.get("/god-mode/stats").then((r) => setStats(r.data));
    if (view === "health") {
      api.get("/god-mode/system-health").then((r) => setHealth(r.data));
      api.get("/god-mode/api-stats").then((r) => setApiStats(r.data));
    }
  }, [view]);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    window.location.href = "/login";
  }

  async function updateStatus(id, status) {
    await api.put(`/platform/tenants/${id}/status`, { status });
    load();
  }

  async function deleteTenant(t) {
    if (!window.confirm(`"${t.name}" kalıcı olarak silinsin mi? Bu geri alınamaz (veri arşivde kalır, listede görünmez olur).`)) return;
    await api.delete(`/god-mode/tenants/${t.id}`);
    load();
  }

  async function enterTenant(t) {
    try {
      const { data } = await api.post(`/god-mode/tenants/${t.id}/enter`);
      localStorage.setItem("token", data.token);
      localStorage.setItem("refresh_token", "");
      localStorage.setItem("user", JSON.stringify(data.user));
      // Client-side nav() DEĞİL — kimlik/tenant tamamen değiştiği için
      // TAM sayfa yenileme (map_snapshots.py'nin "?snapshot=" linkinde
      // kullandığı AYNI karar): tüm component state'i, feature-flag
      // önbelleği vb. sıfırdan, doğru kimlikle yüklenir.
      window.location.href = "/";
    } catch (e) {
      alert(e.response?.data?.detail || "Girilemedi");
    }
  }

  async function openModules(t) {
    setModuleTenant(t);
    const { data } = await api.get(`/god-mode/tenants/${t.id}/modules`);
    setModules(data);
  }

  async function toggleModule(key, enabled) {
    await api.put(`/god-mode/tenants/${moduleTenant.id}/modules/${key}`, { enabled });
    setModules((list) => list.map((m) => (m.key === key ? { ...m, enabled } : m)));
  }

  async function openLicense(t) {
    setLicenseTenant(t);
    const { data } = await api.get(`/god-mode/tenants/${t.id}/license`);
    setLicenseData(data);
    setLicenseForm(data?.license ? { ...data.license } : { plan: "standard" });
  }

  async function saveLicense() {
    const body = { ...licenseForm };
    LICENSE_FIELDS.forEach((f) => {
      if (body[f.key] === "" || body[f.key] === undefined) body[f.key] = null;
      else body[f.key] = Number(body[f.key]);
    });
    delete body.id;
    delete body.scope_type;
    delete body.scope_value;
    delete body.tenant_id;
    delete body.is_active;
    delete body.created_at;
    if (licenseData?.license) {
      await api.put(`/god-mode/tenants/${licenseTenant.id}/license`, body);
    } else {
      await api.post(`/god-mode/tenants/${licenseTenant.id}/license`, body);
    }
    openLicense(licenseTenant);
    load();
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] text-center">
        <div>
          <p className="text-red-400 mb-3">{error}</p>
          <button onClick={logout} className="btn btn-ghost">Çıkış yap</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] p-8 max-w-[1400px] mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">TOPRAX PLATFORM — GOD MODE</div>
          <h1 className="font-display text-4xl">Platform Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Her kooperatif ayrı bir tenant — verileri birbirinden tamamen izole.
          </p>
        </div>
        <button onClick={logout} className="btn btn-ghost text-xs"><LogOut size={14}/> Çıkış</button>
      </header>

      <div className="flex gap-1 mb-6 border-b border-[var(--border)]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setView(t.id)}
            data-testid={`godmode-tab-${t.id}`}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm ${
              view === t.id ? "text-[var(--primary)] border-b-2 border-[var(--primary)]" : "text-[var(--text-dim)]"
            }`}
          >
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {view === "tenants" && (
        <>
          <QuickAddPanel
            title="Yeni Tenant (Kooperatif) Oluştur"
            testId="tenant-add"
            fields={[
              { name: "name", label: "Kurum Adı", required: true },
              { name: "slug", label: "Slug (opsiyonel, boşsa otomatik)" },
              { name: "contact_email", label: "İletişim E-posta", required: true },
              { name: "contact_phone", label: "İletişim Telefon" },
              { name: "plan", label: "Plan", type: "select", default: "standard",
                options: [{ value: "deneme", label: "Deneme" }, { value: "standard", label: "Standart" }, { value: "kurumsal", label: "Kurumsal" }] },
            ]}
            onSubmit={async (v) => { await api.post("/platform/tenants", { ...v, slug: v.slug || null }); load(); }}
          />

          {!tenants ? (
            <div className="text-[var(--text-dim)]">Yükleniyor…</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {tenants.map((t) => (
                <div key={t.id} className="card p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Building2 size={16} className="text-[var(--primary)]"/>
                        <h3 className="font-display text-lg">{t.name}</h3>
                        {t.is_healthy ? (
                          <CheckCircle2 size={14} className="text-[var(--primary)]" title="Son 30 gün içinde aktif" />
                        ) : (
                          <AlertTriangle size={14} className="text-amber-400" title="30 günden uzun süredir giriş yok" />
                        )}
                      </div>
                      <div className="text-xs text-[var(--text-dim)] font-mono mt-0.5">{t.slug}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`badge ${t.status === "aktif" ? "badge-a" : t.status === "askida" ? "badge-c" : "badge-d"}`}>
                        {t.status}
                      </span>
                      {t.license_expiring_soon && <span className="badge badge-c text-[9px]">LİSANS YAKINDA BİTİYOR</span>}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 mb-3 text-sm">
                    <div className="flex items-center gap-2 text-[var(--text-dim)]">
                      <Users size={13}/> {t.user_count} kullanıcı ({t.active_user_count} aktif)
                    </div>
                    <div className="flex items-center gap-2 text-[var(--text-dim)]">
                      <Sprout size={13}/> {t.farmer_count} çiftçi · {t.parcel_count} parsel
                    </div>
                  </div>

                  <div className="text-xs text-[var(--text-dim)] mb-1">{t.contact_email}</div>
                  <div className="text-[10px] text-[var(--text-dim)] mb-3">
                    Son aktivite: {t.last_active_at ? new Date(t.last_active_at).toLocaleString("tr-TR") : "hiç giriş yapılmadı"}
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    {t.user_count > 0 && (
                      <button onClick={() => enterTenant(t)} data-testid={`enter-tenant-${t.id}`} className="btn btn-primary text-xs">
                        <LogIn size={13}/> Bu Kooperatif Olarak Gir
                      </button>
                    )}
                    <button onClick={() => openModules(t)} className="btn btn-ghost text-xs"><Puzzle size={13}/> Modüller</button>
                    <button onClick={() => openLicense(t)} className="btn btn-ghost text-xs"><KeyRound size={13}/> Lisans</button>
                    {t.status !== "aktif" && (
                      <button onClick={() => updateStatus(t.id, "aktif")} className="btn btn-ghost text-xs">Aktifleştir</button>
                    )}
                    {t.status !== "askida" && (
                      <button onClick={() => updateStatus(t.id, "askida")} className="btn btn-ghost text-xs">Askıya Al</button>
                    )}
                    <button onClick={() => { setBootstrapFor(t.id); setBootstrapResult(null); }} className="btn btn-ghost text-xs">
                      İlk Admini Oluştur
                    </button>
                    <button onClick={() => deleteTenant(t)} className="btn btn-ghost text-xs text-red-400"><Trash2 size={13}/> Sil</button>
                  </div>

                  {bootstrapFor === t.id && (
                    <div className="mt-3 pt-3 border-t border-[var(--border)]">
                      <QuickAddPanel
                        title="İlk Süper Admin"
                        testId={`bootstrap-${t.id}`}
                        fields={[
                          { name: "admin_full_name", label: "Ad Soyad", required: true },
                          { name: "admin_email", label: "E-posta", type: "email", required: true },
                          { name: "admin_password", label: "Şifre", type: "password", required: true },
                        ]}
                        onSubmit={async (v) => {
                          const { data } = await api.post(`/platform/tenants/${t.id}/bootstrap-admin`, v);
                          setBootstrapResult(data);
                          load();
                        }}
                      />
                      {bootstrapResult && (
                        <div className="text-xs text-[var(--primary)] p-2 bg-[var(--primary)]/10 rounded">
                          Oluşturuldu: {bootstrapResult.email} — artık bu bilgilerle giriş yapabilir.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {tenants.length === 0 && (
                <div className="text-[var(--text-dim)] text-sm">Henüz tenant yok — yukarıdan ilk kooperatifi oluşturun.</div>
              )}
            </div>
          )}
        </>
      )}

      {view === "stats" && (
        !stats ? <div className="text-[var(--text-dim)]">Yükleniyor…</div> : (
          <div className="space-y-6">
            <section>
              <h2 className="font-display text-lg mb-3">Tenant İstatistikleri</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Toplam Tenant" value={stats.tenants.total} />
                <KPI label="Aktif" value={stats.tenants.active} accent="text-[var(--primary)]" />
                <KPI label="Askıya Alınan" value={stats.tenants.suspended} />
                <KPI label="Silinen" value={stats.tenants.deleted} />
                <KPI label="Deneme Lisanslı" value={stats.tenants.trial} />
                <KPI label="Lisansı Bitmiş" value={stats.tenants.license_expired} accent="text-red-400" />
                <KPI label="Yakında Bitecek" value={stats.tenants.license_expiring_soon} accent="text-amber-400" />
              </div>
            </section>

            <section>
              <h2 className="font-display text-lg mb-3">Kullanıcı İstatistikleri</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Toplam Kullanıcı" value={stats.users.total} />
                <KPI label="Aktif" value={stats.users.active} accent="text-[var(--primary)]" />
                <KPI label="Pasif" value={stats.users.inactive} />
                <KPI label="DAU (bugün)" value={stats.users.dau} />
                <KPI label="MAU (30 gün)" value={stats.users.mau} />
              </div>
            </section>

            <section>
              <h2 className="font-display text-lg mb-3">Veri İstatistikleri</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Çiftçi" value={stats.data.farmers} />
                <KPI label="Parsel" value={stats.data.parcels} />
                <KPI label="Üretim Sezonu" value={stats.data.production_cycles} />
                <KPI label="Sözleşme" value={stats.data.contracts} />
                <KPI label="Hakediş" value={stats.data.entitlements} />
                <KPI label="Görev" value={stats.data.tasks} />
                <KPI label="Form Yanıtı" value={stats.data.form_responses} />
                <KPI label="Dosya/Doküman" value={stats.data.uploads} />
                <KPI label="Depolama (MB)" value={stats.data.storage_mb} />
              </div>
            </section>

            <section>
              <h2 className="font-display text-lg mb-3">İletişim İstatistikleri</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(stats.communications).length === 0 ? (
                  <div className="text-[var(--text-dim)] text-sm">Henüz gönderim yok.</div>
                ) : Object.entries(stats.communications).map(([ch, v]) => (
                  <div key={ch} className="card p-4">
                    <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase mb-1">{ch}</div>
                    <div className="font-display text-xl"><span className="text-[var(--primary)]">{v.sent}</span> / <span className="text-red-400">{v.failed}</span></div>
                    <div className="text-[10px] text-[var(--text-dim)] mt-1">başarılı / başarısız</div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h2 className="font-display text-lg mb-3">Yapay Zeka Kullanımı</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Toplam İstek" value={stats.ai_usage.total_requests} />
                <KPI label="Bu Ay" value={stats.ai_usage.requests_this_month} />
                {Object.entries(stats.ai_usage.by_feature || {}).map(([f, c]) => (
                  <KPI key={f} label={f} value={c} />
                ))}
              </div>
            </section>

            <section>
              <h2 className="font-display text-lg mb-3">Güvenlik İstatistikleri</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="Başarılı Giriş (30g)" value={stats.security.successful_logins_30d} accent="text-[var(--primary)]" />
                <KPI label="Başarısız Giriş (30g)" value={stats.security.failed_logins_30d} accent="text-red-400" />
                <KPI label="Şu An Kilitli Hesap" value={stats.security.locked_accounts_now} accent={stats.security.locked_accounts_now > 0 ? "text-red-400" : ""} />
                <KPI label="Toplam Audit Log" value={stats.security.audit_log_count} />
              </div>
            </section>
          </div>
        )
      )}

      {view === "health" && (
        <div className="space-y-6">
          <section>
            <h2 className="font-display text-lg mb-3">Sunucu Kaynakları</h2>
            {!health ? <div className="text-[var(--text-dim)]">Yükleniyor…</div> : health.error ? (
              <div className="text-amber-400 text-sm">psutil kullanılamıyor: {health.error}</div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI label="CPU" value={`%${health.cpu_percent}`} accent={health.cpu_percent > 80 ? "text-red-400" : "text-[var(--primary)]"} />
                <KPI label="RAM" value={`%${health.ram_percent} (${health.ram_used_mb}/${health.ram_total_mb} MB)`} accent={health.ram_percent > 80 ? "text-red-400" : "text-[var(--primary)]"} />
                <KPI label="Disk" value={`%${health.disk_percent} (${health.disk_used_gb}/${health.disk_total_gb} GB)`} accent={health.disk_percent > 80 ? "text-red-400" : "text-[var(--primary)]"} />
                <KPI label="Çalışan Süreç" value={health.process_count} />
              </div>
            )}
          </section>

          <section>
            <h2 className="font-display text-lg mb-3">API Çağrı İstatistikleri</h2>
            {!apiStats ? <div className="text-[var(--text-dim)]">Yükleniyor…</div> : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <KPI label="Toplam Çağrı" value={apiStats.total} />
                  <KPI label="Başarılı" value={apiStats.success} accent="text-[var(--primary)]" />
                  <KPI label="Hatalı" value={apiStats.error} accent={apiStats.error > 0 ? "text-red-400" : ""} />
                  <KPI label="Ort. Yanıt Süresi" value={`${apiStats.avg_duration_ms} ms`} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="card p-4">
                    <div className="text-xs text-[var(--text-dim)] uppercase tracking-widest mb-2">En Çok Kullanılan Uçlar</div>
                    {apiStats.top_paths.map((p, i) => (
                      <div key={i} className="flex justify-between text-sm py-1 border-b border-[var(--border)] last:border-0">
                        <span className="font-mono text-xs">{p.path}</span>
                        <span className="text-[var(--text-dim)]">{p.count} · {p.avg_ms}ms</span>
                      </div>
                    ))}
                    {apiStats.top_paths.length === 0 && <div className="text-[var(--text-dim)] text-sm">Veri yok.</div>}
                  </div>
                  <div className="card p-4">
                    <div className="text-xs text-[var(--text-dim)] uppercase tracking-widest mb-2">En Çok Hata Üreten Uçlar</div>
                    {apiStats.top_errors.map((p, i) => (
                      <div key={i} className="flex justify-between text-sm py-1 border-b border-[var(--border)] last:border-0">
                        <span className="font-mono text-xs">{p.path}</span>
                        <span className="text-red-400">{p.status} × {p.count}</span>
                      </div>
                    ))}
                    {apiStats.top_errors.length === 0 && <div className="text-[var(--text-dim)] text-sm">Hiç hata yok.</div>}
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      <Drawer open={!!moduleTenant} onClose={() => setModuleTenant(null)} title={`Modüller — ${moduleTenant?.name || ""}`}>
        <div className="p-4 space-y-2">
          {MODULE_ORDER.map((key) => {
            const m = modules.find((x) => x.key === key);
            if (!m) return null;
            return (
              <div key={key} className="flex items-center justify-between p-3 card">
                <span className="text-sm">{m.label}</span>
                <button
                  onClick={() => toggleModule(key, !m.enabled)}
                  className={`badge ${m.enabled ? "badge-a" : "badge-d"}`}
                  data-testid={`module-toggle-${key}`}
                >
                  {m.enabled ? "Açık" : "Kapalı"}
                </button>
              </div>
            );
          })}
        </div>
      </Drawer>

      <Drawer open={!!licenseTenant} onClose={() => setLicenseTenant(null)} title={`Lisans — ${licenseTenant?.name || ""}`}>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Plan</label>
            <select className="input" value={licenseForm.plan || "standard"}
                    onChange={(e) => setLicenseForm((f) => ({ ...f, plan: e.target.value }))}>
              <option value="trial">Deneme</option>
              <option value="standard">Standart</option>
              <option value="premium">Premium</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Bitiş Tarihi (opsiyonel)</label>
            <input type="date" className="input" value={(licenseForm.expires_at || "").slice(0, 10)}
                   onChange={(e) => setLicenseForm((f) => ({ ...f, expires_at: e.target.value ? `${e.target.value}T23:59:59+00:00` : null }))} />
          </div>
          {LICENSE_FIELDS.map((f) => (
            <div key={f.key}>
              <label className="text-xs text-[var(--text-dim)] mb-1 block">{f.label} (boş = sınırsız)</label>
              <input type="number" className="input" value={licenseForm[f.key] ?? ""}
                     onChange={(e) => setLicenseForm((v) => ({ ...v, [f.key]: e.target.value }))} />
            </div>
          ))}
          <button onClick={saveLicense} className="btn btn-primary w-full justify-center">
            {licenseData?.license ? "Lisansı Güncelle" : "Lisans Oluştur"}
          </button>

          {licenseData?.usage && (
            <div className="pt-3 border-t border-[var(--border)] space-y-1.5">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-widest mb-1">Şu Anki Kullanım</div>
              <div className="text-sm flex justify-between"><span>Kullanıcı</span><span>{licenseData.usage.user_count}</span></div>
              <div className="text-sm flex justify-between"><span>Parsel</span><span>{licenseData.usage.parcel_count}</span></div>
              <div className="text-sm flex justify-between"><span>Depolama</span><span>{licenseData.usage.storage_mb} MB</span></div>
              <div className="text-sm flex justify-between"><span>AI (bu ay)</span><span>{licenseData.usage.ai_count_this_month}</span></div>
              <div className="text-sm flex justify-between"><span>SMS (bu ay)</span><span>{licenseData.usage.sms_count_this_month}</span></div>
              <div className="text-sm flex justify-between"><span>WhatsApp (bu ay)</span><span>{licenseData.usage.whatsapp_count_this_month}</span></div>
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}
