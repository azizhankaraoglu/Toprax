/**
 * PLATFORM CORE (IT-33 / FAZ 11 TAMAMLANDI)
 *
 * backend/platform_core.py'nin admin ekranı — dört sekme: Feature Flags
 * (aç/kapa toggle'ları), Module Manifest (salt-okunur envanter, IntegrationHub.
 * jsx'in registry kartlarıyla AYNI aile), Licensing (basit CRUD, IT-18'in
 * SupportCatalog.jsx kalıbı), Health Center (servis durumu rozetleri).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Settings, ToggleLeft, ToggleRight, Boxes, BadgeCheck, HeartPulse } from "lucide-react";

const STATUS_BADGE = { saglikli: "badge-a", uyari: "badge-b", hata: "badge-d", kurulu_degil: "badge-neutral" };

export default function PlatformCore() {
  const [tab, setTab] = useState("flags");
  const [flags, setFlags] = useState([]);
  const [manifests, setManifests] = useState([]);
  const [licenses, setLicenses] = useState([]);
  const [health, setHealth] = useState([]);
  const [seeding, setSeeding] = useState(false);

  const loadFlags = () => api.get("/feature-flags").then((r) => setFlags(r.data));
  const loadLicenses = () => api.get("/licenses").then((r) => setLicenses(r.data));
  const loadHealth = () => api.get("/platform-core/health").then((r) => setHealth(r.data));

  useEffect(() => {
    loadFlags();
    api.get("/platform-core/module-manifests").then((r) => setManifests(r.data));
    loadLicenses();
    loadHealth();
  }, []);

  async function seedFlags() {
    setSeeding(true);
    try { await api.post("/feature-flags/seed-defaults"); await loadFlags(); } finally { setSeeding(false); }
  }

  async function toggleFlag(flag) {
    await api.put(`/feature-flags/${flag.key}`, { enabled: !flag.enabled });
    loadFlags();
  }

  async function toggleLicense(l) {
    await api.put(`/licenses/${l.id}`, { is_active: !l.is_active });
    loadLicenses();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="platform-core-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 11 — PLATFORM CORE</div>
          <h1 className="font-display text-4xl flex items-center gap-2"><Settings size={28}/> Platform Core</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Feature Flags, Module Manifest, Lisanslama iskeleti ve Health Center — bundan sonraki
            her modülün uyması gereken platform omurgası.
          </p>
        </div>
      </header>

      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setTab("flags")} className={`btn text-sm ${tab === "flags" ? "btn-primary" : "btn-ghost"}`}><ToggleRight size={14}/> Feature Flags</button>
        <button onClick={() => setTab("manifests")} className={`btn text-sm ${tab === "manifests" ? "btn-primary" : "btn-ghost"}`}><Boxes size={14}/> Module Manifest</button>
        <button onClick={() => setTab("licenses")} className={`btn text-sm ${tab === "licenses" ? "btn-primary" : "btn-ghost"}`}><BadgeCheck size={14}/> Lisanslama</button>
        <button onClick={() => setTab("health")} className={`btn text-sm ${tab === "health" ? "btn-primary" : "btn-ghost"}`}><HeartPulse size={14}/> Health Center</button>
      </div>

      {tab === "flags" && (
        <div className="card overflow-hidden">
          {flags.length === 0 && (
            <div className="p-4 border-b border-[var(--border)]">
              <button onClick={seedFlags} disabled={seeding} className="btn btn-ghost text-sm">
                {seeding ? "Yükleniyor…" : "Varsayılan Feature Flag'leri Yükle"}
              </button>
            </div>
          )}
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-4">Özellik</th><th className="p-4">Anahtar</th><th className="p-4">Durum</th>
            </tr></thead>
            <tbody>
              {flags.map((f) => (
                <tr key={f.key} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                  <td className="p-4">{f.label}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)] font-mono">{f.key}</td>
                  <td className="p-4">
                    <button onClick={() => toggleFlag(f)} className="flex items-center gap-2" data-testid={`flag-toggle-${f.key}`}>
                      {f.enabled ? <ToggleRight size={22} className="text-[var(--primary)]"/> : <ToggleLeft size={22} className="text-[var(--text-dim)]"/>}
                      <span className={`badge ${f.enabled ? "badge-a" : "badge-d"}`}>{f.enabled ? "Açık" : "Kapalı"}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "manifests" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {manifests.map((m) => (
            <div key={m.name} className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-display text-lg">{m.name}</span>
                <span className="badge badge-neutral text-[10px]">v{m.version}</span>
              </div>
              <div className="text-xs text-[var(--text-dim)] mb-1">
                <span className="text-[var(--text)]">Bağımlılıklar:</span> {m.dependencies.length ? m.dependencies.join(", ") : "—"}
              </div>
              <div className="text-xs text-[var(--text-dim)] mb-1">
                <span className="text-[var(--text)]">Menüler:</span> {m.menus.join(", ")}
              </div>
              <div className="text-xs text-[var(--text-dim)] mb-1">
                <span className="text-[var(--text)]">Yetkiler:</span> {m.permissions.join(", ")}
              </div>
              <div className="text-xs text-[var(--text-dim)] mb-1">
                <span className="text-[var(--text)]">API'ler:</span> {m.apis.join(", ")}
              </div>
              <div className="text-xs text-[var(--text-dim)]">
                <span className="text-[var(--text)]">Dashboard Bileşenleri:</span> {m.dashboard_components.join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "licenses" && (
        <>
          <QuickAddPanel
            title="Yeni Lisans"
            testId="license-add"
            fields={[
              { name: "scope_type", label: "Kapsam", type: "select", required: true,
                options: [{ value: "module", label: "Modül" }, { value: "tenant", label: "Tenant" }, { value: "user", label: "Kullanıcı" }] },
              { name: "scope_value", label: "Kapsam Değeri (ör. modül anahtarı/tenant id/user id)", required: true },
              { name: "plan", label: "Plan", type: "select", default: "standard",
                options: [{ value: "trial", label: "Trial" }, { value: "standard", label: "Standard" }, { value: "premium", label: "Premium" }] },
              { name: "expires_at", label: "Son Geçerlilik (opsiyonel, YYYY-MM-DD)" },
              { name: "note", label: "Not (opsiyonel)" },
            ]}
            onSubmit={async (v) => {
              await api.post("/licenses", { ...v, expires_at: v.expires_at || null });
              loadLicenses();
            }}
          />
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-4">Kapsam</th><th className="p-4">Değer</th><th className="p-4">Plan</th>
                <th className="p-4">Son Geçerlilik</th><th className="p-4">Durum</th>
              </tr></thead>
              <tbody>
                {licenses.map((l) => (
                  <tr key={l.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                    <td className="p-4 text-xs text-[var(--text-dim)]">{l.scope_type}</td>
                    <td className="p-4 font-mono text-xs">{l.scope_value}</td>
                    <td className="p-4"><span className="badge badge-neutral">{l.plan}</span></td>
                    <td className="p-4 text-xs text-[var(--text-dim)]">{l.expires_at || "Süresiz"}</td>
                    <td className="p-4">
                      <button onClick={() => toggleLicense(l)} className={`badge ${l.is_active === false ? "badge-d" : "badge-a"}`}>
                        {l.is_active === false ? "Pasif" : "Aktif"}
                      </button>
                    </td>
                  </tr>
                ))}
                {licenses.length === 0 && (
                  <tr><td colSpan="5" className="p-6 text-center text-[var(--text-dim)]">Henüz lisans kaydı yok (tanımsız = serbest kullanım)</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "health" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {health.map((h) => (
            <div key={h.service} className="card p-4 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{h.label}</div>
                <div className="text-xs text-[var(--text-dim)]">{h.detail}</div>
              </div>
              <span className={`badge ${STATUS_BADGE[h.status] || "badge-neutral"}`}>{h.status_label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
