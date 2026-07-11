import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Users, Shield, Plus, X, Check } from "lucide-react";

export function KullaniciYonetimi() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({ role: "", custom_role_id: "", grant: [], revoke: [] });
  const [newRoleForm, setNewRoleForm] = useState(false);

  const load = () => {
    api.get("/users").then((r) => setUsers(r.data));
    api.get("/users/roles").then((r) => setRoles(r.data));
  };
  useEffect(() => {
    load();
    api.get("/permissions/catalog").then((r) => setCatalog(r.data.catalog));
  }, []);

  function openEdit(u) {
    setEditingUser(u);
    setEditForm({
      role: u.role || "",
      custom_role_id: u.custom_role_id || "",
      grant: u.permission_overrides?.grant || [],
      revoke: u.permission_overrides?.revoke || [],
    });
  }

  function toggleOverride(list, key, permKey) {
    const has = editForm[list].includes(permKey);
    setEditForm((f) => ({
      ...f,
      [list]: has ? f[list].filter((k) => k !== permKey) : [...f[list], permKey],
    }));
  }

  async function saveEdit() {
    await api.put(`/users/${editingUser.id}/role`, {
      role: editForm.custom_role_id ? null : editForm.role,
      custom_role_id: editForm.custom_role_id || null,
      grant: editForm.grant,
      revoke: editForm.revoke,
    });
    setEditingUser(null);
    load();
  }

  async function toggleActive(u) {
    await api.put(`/users/${u.id}/status`, { active: !u.active });
    load();
  }

  if (!roles || !catalog) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="users-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM AYARLARI</div>
        <h1 className="font-display text-4xl">Kullanıcılar ve Roller</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Personel ekleyin, rol atayın, gerekirse role ek/eksik izin tanımlayın.
        </p>
      </header>

      <QuickAddPanel
        title="Yeni Personel"
        testId="user-add"
        fields={[
          { name: "full_name", label: "Ad Soyad", required: true },
          { name: "email", label: "E-posta", type: "email", required: true },
          { name: "password", label: "Şifre", type: "password", required: true },
          { name: "phone", label: "Telefon" },
          { name: "role", label: "Rol", type: "select", required: true,
            options: roles.built_in.map((r) => ({ value: r.key, label: r.label })) },
        ]}
        onSubmit={async (v) => { await api.post("/users", v); load(); }}
      />

      <div className="card overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad Soyad</th><th className="p-4">E-posta</th><th className="p-4">Rol</th>
            <th className="p-4">Ek/Eksik İzin</th><th className="p-4">Durum</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {users.map((u) => {
              const customRole = roles.custom.find((r) => r.id === u.custom_role_id);
              const overrideCount = (u.permission_overrides?.grant?.length || 0) + (u.permission_overrides?.revoke?.length || 0);
              return (
                <tr key={u.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                  <td className="p-4">{u.full_name}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{u.email}</td>
                  <td className="p-4">
                    {customRole ? (
                      <span className="badge badge-b">{customRole.name} (özel)</span>
                    ) : (
                      <span className="badge badge-a">{roles.built_in.find((r) => r.key === u.role)?.label || u.role}</span>
                    )}
                  </td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{overrideCount > 0 ? `${overrideCount} değişiklik` : "—"}</td>
                  <td className="p-4">
                    <button onClick={() => toggleActive(u)} className={`badge ${u.active === false ? "badge-d" : "badge-a"}`}>
                      {u.active === false ? "Pasif" : "Aktif"}
                    </button>
                  </td>
                  <td className="p-4">
                    <button onClick={() => openEdit(u)} className="btn btn-ghost text-xs">Düzenle</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editingUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setEditingUser(null)}>
          <div className="card p-5 max-w-[600px] w-full max-h-[85vh] overflow-y-auto scrollbar" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-lg">{editingUser.full_name} — Rol & İzinler</h3>
              <button onClick={() => setEditingUser(null)}><X size={18}/></button>
            </div>

            <label className="text-xs text-[var(--text-dim)] mb-1 block">ROL</label>
            <select className="input mb-3" value={editForm.custom_role_id || editForm.role}
                    onChange={(e) => {
                      const val = e.target.value;
                      const isCustom = roles.custom.some((r) => r.id === val);
                      setEditForm((f) => ({ ...f, role: isCustom ? f.role : val, custom_role_id: isCustom ? val : "" }));
                    }}>
              <optgroup label="Built-in Roller">
                {roles.built_in.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
              </optgroup>
              {roles.custom.length > 0 && (
                <optgroup label="Özel Roller">
                  {roles.custom.map((r) => <option key={r.id} value={r.id}>{r.name} (özel)</option>)}
                </optgroup>
              )}
            </select>

            <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">İnce Ayar (role ek/eksik izin)</div>
            <div className="space-y-3 max-h-[350px] overflow-y-auto scrollbar pr-1">
              {Object.entries(catalog).map(([modKey, mod]) => (
                <div key={modKey}>
                  <div className="text-xs font-medium text-[var(--text-dim)] mb-1">{mod.label}</div>
                  <div className="space-y-1">
                    {mod.permissions.map((p) => {
                      const granted = editForm.grant.includes(p.key);
                      const revoked = editForm.revoke.includes(p.key);
                      return (
                        <div key={p.key} className="flex items-center justify-between text-xs p-1.5 rounded bg-[var(--surface-2)]">
                          <span>{p.label}</span>
                          <div className="flex gap-1">
                            <button
                              onClick={() => toggleOverride("grant", "grant", p.key)}
                              className={`px-2 py-0.5 rounded ${granted ? "bg-[var(--primary)] text-black" : "border border-[var(--border)]"}`}
                            >+ Ver</button>
                            <button
                              onClick={() => toggleOverride("revoke", "revoke", p.key)}
                              className={`px-2 py-0.5 rounded ${revoked ? "bg-red-500 text-white" : "border border-[var(--border)]"}`}
                            >- Kısıtla</button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <button onClick={saveEdit} className="btn btn-primary w-full justify-center mt-4">
              <Check size={14}/> Kaydet
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function OzelRoller() {
  const [customRoles, setCustomRoles] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", permissions: [] });

  const load = () => api.get("/roles/custom").then((r) => setCustomRoles(r.data));
  useEffect(() => {
    load();
    api.get("/permissions/catalog").then((r) => setCatalog(r.data.catalog));
  }, []);

  function togglePerm(key) {
    setForm((f) => ({
      ...f,
      permissions: f.permissions.includes(key) ? f.permissions.filter((k) => k !== key) : [...f.permissions, key],
    }));
  }

  async function submit() {
    await api.post("/roles/custom", form);
    setForm({ name: "", permissions: [] });
    setCreating(false);
    load();
  }

  async function remove(id) {
    await api.delete(`/roles/custom/${id}`);
    load();
  }

  if (!catalog) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="custom-roles-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM AYARLARI</div>
          <h1 className="font-display text-4xl">Özel Roller</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Modül × fonksiyon bazında kendi rolünüzü tanımlayın (örn. "Bölge Sorumlusu").
          </p>
        </div>
        {!creating && (
          <button onClick={() => setCreating(true)} className="btn btn-primary"><Plus size={14}/> Yeni Özel Rol</button>
        )}
      </header>

      {creating && (
        <div className="card p-5 mb-6">
          <input className="input mb-4" placeholder="Rol adı (örn. Bölge Sorumlusu)"
                 value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}/>
          <div className="space-y-3 max-h-[400px] overflow-y-auto scrollbar mb-4">
            {Object.entries(catalog).map(([modKey, mod]) => (
              <div key={modKey}>
                <div className="text-xs font-medium text-[var(--text-dim)] mb-1">{mod.label}</div>
                <div className="grid grid-cols-2 gap-1">
                  {mod.permissions.map((p) => (
                    <label key={p.key} className="flex items-center gap-2 text-xs p-1.5 rounded bg-[var(--surface-2)] cursor-pointer">
                      <input type="checkbox" checked={form.permissions.includes(p.key)} onChange={() => togglePerm(p.key)}/>
                      {p.label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={submit} disabled={!form.name || form.permissions.length === 0} className="btn btn-primary">
              <Check size={14}/> Kaydet
            </button>
            <button onClick={() => setCreating(false)} className="btn btn-ghost">İptal</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {customRoles.map((r) => (
          <div key={r.id} className="card p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Shield size={15} className="text-[var(--primary)]"/>
                <h3 className="font-display text-base">{r.name}</h3>
              </div>
              <button onClick={() => remove(r.id)} className="text-red-400"><X size={14}/></button>
            </div>
            <div className="text-xs text-[var(--text-dim)]">{r.permissions.length} izin tanımlı</div>
          </div>
        ))}
        {customRoles.length === 0 && !creating && (
          <div className="text-[var(--text-dim)] text-sm">Henüz özel rol yok.</div>
        )}
      </div>
    </div>
  );
}
