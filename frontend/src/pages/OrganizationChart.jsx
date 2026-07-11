/**
 * ORGANİZASYON HİYERARŞİSİ (IT-07b / FAZ 3 devam)
 *
 * Birim (OrganizationUnit) + Pozisyon (Position) + Kullanıcı Ataması
 * (UserPosition — manager_user_id) yönetimi + ağaç görselleştirme.
 * approval.py'nin "hierarchy" hedefli onay adımları BURADAKİ manager_user_id
 * zincirini kullanır (bkz. backend/organization.py docstring'i).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Landmark, Plus, Users, ChevronRight, ChevronDown } from "lucide-react";

function UnitNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ marginLeft: depth * 18 }} className="mb-1">
      <div className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-[var(--surface-2)]">
        {node.children?.length > 0 ? (
          <button onClick={() => setOpen((o) => !o)} className="text-[var(--text-dim)]">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : <span className="w-[14px]" />}
        <Landmark size={14} className="text-[var(--primary)]" />
        <span className="font-medium text-sm">{node.name}</span>
        <span className="text-[10px] text-[var(--text-dim)]">({node.positions?.length || 0} pozisyon)</span>
      </div>
      {node.positions?.map((p) => (
        <div key={p.id} style={{ marginLeft: (depth + 1) * 18 }} className="text-xs py-1 px-2 flex items-center gap-2">
          <Users size={12} className="text-[var(--text-dim)]" />
          <span>{p.title}</span>
          {p.occupants?.map((o) => (
            <span key={o.id} className="badge badge-neutral">{o.full_name || o.email || o.id}</span>
          ))}
          {(!p.occupants || p.occupants.length === 0) && <span className="text-[var(--text-dim)]">— boş —</span>}
        </div>
      ))}
      {open && node.children?.map((c) => <UnitNode key={c.id} node={c} depth={depth + 1} />)}
    </div>
  );
}

export default function OrganizationChart() {
  const [tree, setTree] = useState([]);
  const [units, setUnits] = useState([]);
  const [positions, setPositions] = useState([]);
  const [users, setUsers] = useState([]);
  const [unitForm, setUnitForm] = useState({ name: "", parent_unit_id: "" });
  const [positionForm, setPositionForm] = useState({ title: "", organization_unit_id: "", level: 0 });
  const [assignForm, setAssignForm] = useState({ user_id: "", position_id: "", manager_user_id: "" });
  const [error, setError] = useState("");

  function loadAll() {
    api.get("/org-chart").then((r) => setTree(r.data.tree));
    api.get("/organization-units").then((r) => setUnits(r.data));
    api.get("/positions").then((r) => setPositions(r.data));
  }
  useEffect(() => {
    loadAll();
    api.get("/users").then((r) => setUsers(r.data));
  }, []);

  async function submitUnit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/organization-units", { ...unitForm, parent_unit_id: unitForm.parent_unit_id || null });
      setUnitForm({ name: "", parent_unit_id: "" });
      loadAll();
    } catch (err) { setError(err.response?.data?.detail || "Birim oluşturulamadı"); }
  }

  async function submitPosition(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/positions", positionForm);
      setPositionForm({ title: "", organization_unit_id: "", level: 0 });
      loadAll();
    } catch (err) { setError(err.response?.data?.detail || "Pozisyon oluşturulamadı"); }
  }

  async function submitAssign(e) {
    e.preventDefault();
    setError("");
    try {
      await api.put(`/users/${assignForm.user_id}/position`, {
        position_id: assignForm.position_id,
        manager_user_id: assignForm.manager_user_id || null,
        is_primary: true,
      });
      setAssignForm({ user_id: "", position_id: "", manager_user_id: "" });
      loadAll();
    } catch (err) { setError(err.response?.data?.detail || "Atama yapılamadı"); }
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="organization-chart-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">ORGANİZASYON</div>
        <h1 className="font-display text-4xl">Organizasyon Hiyerarşisi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Birim / Pozisyon / Yönetici ataması — Onay Zinciri Motoru'nun "hiyerarşi bazlı" (talep sahibinin
          doğrudan yöneticisi) onay hedefini bu yapı belirler.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <div className="grid grid-cols-3 gap-4 mb-6">
        <form onSubmit={submitUnit} className="card p-4 space-y-2">
          <h3 className="font-display text-sm flex items-center gap-2"><Landmark size={14} className="text-[var(--primary)]" />Yeni Birim</h3>
          <input className="input w-full text-sm" placeholder="Birim adı (ör. Saha Operasyonları)" required
                 value={unitForm.name} onChange={(e) => setUnitForm((f) => ({ ...f, name: e.target.value }))} />
          <select className="input w-full text-sm" value={unitForm.parent_unit_id}
                  onChange={(e) => setUnitForm((f) => ({ ...f, parent_unit_id: e.target.value }))}>
            <option value="">— Üst birim yok (kök) —</option>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <button type="submit" className="btn btn-primary text-xs w-full justify-center"><Plus size={12} /> Birim Ekle</button>
        </form>

        <form onSubmit={submitPosition} className="card p-4 space-y-2">
          <h3 className="font-display text-sm flex items-center gap-2"><Users size={14} className="text-[var(--primary)]" />Yeni Pozisyon</h3>
          <input className="input w-full text-sm" placeholder="Pozisyon (ör. Bölge Sorumlusu)" required
                 value={positionForm.title} onChange={(e) => setPositionForm((f) => ({ ...f, title: e.target.value }))} />
          <select className="input w-full text-sm" required value={positionForm.organization_unit_id}
                  onChange={(e) => setPositionForm((f) => ({ ...f, organization_unit_id: e.target.value }))}>
            <option value="">Birim seç...</option>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <input className="input w-full text-sm" type="number" placeholder="Seviye (onay sıralamasında referans)"
                 value={positionForm.level} onChange={(e) => setPositionForm((f) => ({ ...f, level: Number(e.target.value) }))} />
          <button type="submit" className="btn btn-primary text-xs w-full justify-center"><Plus size={12} /> Pozisyon Ekle</button>
        </form>

        <form onSubmit={submitAssign} className="card p-4 space-y-2">
          <h3 className="font-display text-sm flex items-center gap-2"><Users size={14} className="text-[var(--primary)]" />Kullanıcı Ata</h3>
          <select className="input w-full text-sm" required value={assignForm.user_id}
                  onChange={(e) => setAssignForm((f) => ({ ...f, user_id: e.target.value }))}>
            <option value="">Kullanıcı seç...</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
          </select>
          <select className="input w-full text-sm" required value={assignForm.position_id}
                  onChange={(e) => setAssignForm((f) => ({ ...f, position_id: e.target.value }))}>
            <option value="">Pozisyon seç...</option>
            {positions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
          <select className="input w-full text-sm" value={assignForm.manager_user_id}
                  onChange={(e) => setAssignForm((f) => ({ ...f, manager_user_id: e.target.value }))}>
            <option value="">— Yöneticisi yok (zincirin tepesi) —</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
          </select>
          <button type="submit" className="btn btn-primary text-xs w-full justify-center"><Plus size={12} /> Ata</button>
        </form>
      </div>

      <div className="card p-5">
        <h3 className="font-display text-lg mb-3">Org Şeması</h3>
        {tree.length === 0 && <div className="text-xs text-[var(--text-dim)] p-4 text-center">Henüz birim tanımlı değil — yukarıdan başlayın.</div>}
        {tree.map((n) => <UnitNode key={n.id} node={n} />)}
      </div>
    </div>
  );
}
