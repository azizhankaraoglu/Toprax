/**
 * EXPERIENCE PROFILE YÖNETİMİ (IT-34 / FAZ 12 — Mobil başlangıç)
 *
 * backend/experience_profile.py'nin admin ekranı. Kabul kriteri "profil kod
 * değişikliği gerektirmeden admin ekranından oluşturulabiliyor" burada
 * karşılanır. dashboard_widgets/menu_items/quick_actions/map_tools/
 * ai_features BİLİNÇLİ OLARAK opak virgülle-ayrılmış metin girişi —
 * map_workspace.py'nin (IT-14) aynı "backend key'leri doğrulamaz" felsefesi,
 * burada da yeni bir seç-kutusu/registry İCAT EDİLMEDİ.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { UserSquare2, Smartphone } from "lucide-react";

function toList(text) {
  return (text || "").split(",").map((s) => s.trim()).filter(Boolean);
}

export function ExperienceProfileYonetimi() {
  const [profiles, setProfiles] = useState([]);
  const [users, setUsers] = useState([]);
  const [assignments, setAssignments] = useState({});
  const [assignForm, setAssignForm] = useState({ user_id: "", experience_profile_id: "" });
  const [error, setError] = useState("");

  const loadProfiles = () => api.get("/experience-profiles").then((r) => setProfiles(r.data));

  useEffect(() => {
    loadProfiles();
    api.get("/users").then((r) => setUsers(r.data));
  }, []);

  useEffect(() => {
    users.forEach((u) => {
      api.get(`/users/${u.id}/experience-profile`).then((r) => {
        setAssignments((a) => ({ ...a, [u.id]: r.data.experience_profile_id }));
      });
    });
  }, [users]);

  async function toggleActive(p) {
    if (p.is_active) {
      await api.delete(`/experience-profiles/${p.id}`);
    } else {
      await api.put(`/experience-profiles/${p.id}`, { is_active: true });
    }
    loadProfiles();
  }

  async function submitAssignment(e) {
    e.preventDefault();
    setError("");
    try {
      await api.put(`/users/${assignForm.user_id}/experience-profile`, {
        experience_profile_id: assignForm.experience_profile_id || null,
      });
      setAssignments((a) => ({ ...a, [assignForm.user_id]: assignForm.experience_profile_id || null }));
      setAssignForm({ user_id: "", experience_profile_id: "" });
    } catch (err) {
      setError(err.response?.data?.detail || "Atama yapılamadı");
    }
  }

  const profilesById = new Map(profiles.map((p) => [p.id, p]));

  return (
    <div className="p-8 max-w-[1400px]" data-testid="experience-profiles-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 12 — MOBİL</div>
        <h1 className="font-display text-4xl flex items-center gap-2"><Smartphone size={28}/> Experience Profile (Mobil Persona)</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Mobil deneyim statik rol bazlı değil — burada tanımlanan profiller kullanıcılara atanır,
          mobil client açılışta <code className="font-mono text-xs">GET /me/experience</code> ile bu konfigürasyonu çeker.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <QuickAddPanel
        title="Yeni Experience Profile"
        testId="experience-profile-add"
        fields={[
          { name: "name", label: "Profil Adı (ör. Ziraat Mühendisi Sahra)", required: true, span2: true },
          { name: "dashboard_widgets", label: "Dashboard Widget'ları (virgülle ayır)" },
          { name: "menu_items", label: "Menü Öğeleri (virgülle ayır)" },
          { name: "quick_actions", label: "Hızlı Aksiyonlar (virgülle ayır)" },
          { name: "map_tools", label: "Harita Araçları (virgülle ayır)" },
          { name: "ai_features", label: "AI Özellikleri (virgülle ayır)" },
        ]}
        onSubmit={async (v) => {
          await api.post("/experience-profiles", {
            name: v.name,
            dashboard_widgets: toList(v.dashboard_widgets),
            menu_items: toList(v.menu_items),
            quick_actions: toList(v.quick_actions),
            map_tools: toList(v.map_tools),
            ai_features: toList(v.ai_features),
          });
          loadProfiles();
        }}
      />

      <div className="card overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Menü Öğeleri</th><th className="p-4">Widget'lar</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {profiles.map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">{p.name}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{p.menu_items.join(", ") || "—"}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{p.dashboard_widgets.join(", ") || "—"}</td>
                <td className="p-4">
                  <button onClick={() => toggleActive(p)} className={`badge ${p.is_active === false ? "badge-d" : "badge-a"}`}>
                    {p.is_active === false ? "Pasif" : "Aktif"}
                  </button>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Henüz Experience Profile yok</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card p-5">
        <h3 className="font-display text-lg mb-3 flex items-center gap-2"><UserSquare2 size={16} className="text-[var(--primary)]"/>Kullanıcıya Profil Ata</h3>
        <form onSubmit={submitAssignment} className="flex flex-wrap items-end gap-2 mb-4">
          <select className="input flex-1 min-w-[200px]" required value={assignForm.user_id}
                  onChange={(e) => setAssignForm((f) => ({ ...f, user_id: e.target.value }))}>
            <option value="">Kullanıcı seç...</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
          </select>
          <select className="input flex-1 min-w-[200px]" value={assignForm.experience_profile_id}
                  onChange={(e) => setAssignForm((f) => ({ ...f, experience_profile_id: e.target.value }))}>
            <option value="">Profil yok (varsayılana dön)</option>
            {profiles.filter((p) => p.is_active !== false).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button type="submit" className="btn btn-primary" data-testid="assign-profile-submit">Ata</button>
        </form>

        <div className="space-y-1.5">
          {users.map((u) => (
            <div key={u.id} className="flex items-center justify-between text-sm border-b border-[var(--border)] pb-1.5">
              <span>{u.full_name} <span className="text-xs text-[var(--text-dim)]">({u.role})</span></span>
              <span className="badge badge-neutral text-[10px]">
                {assignments[u.id] ? (profilesById.get(assignments[u.id])?.name || "…") : "Varsayılan"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
