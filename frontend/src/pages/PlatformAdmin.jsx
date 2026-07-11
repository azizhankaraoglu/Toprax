import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Building2, LogOut, Users, Sprout } from "lucide-react";

export default function PlatformAdmin() {
  const [tenants, setTenants] = useState(null);
  const [error, setError] = useState("");
  const [bootstrapFor, setBootstrapFor] = useState(null); // tenant id
  const [bootstrapResult, setBootstrapResult] = useState(null);

  const load = () => api.get("/platform/tenants")
    .then((r) => setTenants(r.data))
    .catch((e) => setError(e.response?.data?.detail || "Yüklenemedi"));

  useEffect(load, []);

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
      <header className="flex items-center justify-between mb-8">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">TABSIS PLATFORM</div>
          <h1 className="font-display text-4xl">Tenant (Kurum) Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Her kooperatif ayrı bir tenant — verileri birbirinden tamamen izole.
          </p>
        </div>
        <button onClick={logout} className="btn btn-ghost text-xs"><LogOut size={14}/> Çıkış</button>
      </header>

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
                  </div>
                  <div className="text-xs text-[var(--text-dim)] font-mono mt-0.5">{t.slug}</div>
                </div>
                <span className={`badge ${t.status === "aktif" ? "badge-a" : t.status === "askida" ? "badge-c" : "badge-d"}`}>
                  {t.status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3 text-sm">
                <div className="flex items-center gap-2 text-[var(--text-dim)]">
                  <Users size={13}/> {t.user_count} kullanıcı
                </div>
                <div className="flex items-center gap-2 text-[var(--text-dim)]">
                  <Sprout size={13}/> {t.farmer_count} çiftçi
                </div>
              </div>

              <div className="text-xs text-[var(--text-dim)] mb-3">{t.contact_email}</div>

              <div className="flex gap-2 flex-wrap">
                {t.status !== "aktif" && (
                  <button onClick={() => updateStatus(t.id, "aktif")} className="btn btn-ghost text-xs">Aktifleştir</button>
                )}
                {t.status !== "askida" && (
                  <button onClick={() => updateStatus(t.id, "askida")} className="btn btn-ghost text-xs">Askıya Al</button>
                )}
                <button onClick={() => { setBootstrapFor(t.id); setBootstrapResult(null); }} className="btn btn-ghost text-xs">
                  İlk Admini Oluştur
                </button>
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
    </div>
  );
}
