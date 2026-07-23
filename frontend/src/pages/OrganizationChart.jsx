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
import { Landmark, Plus, Users, ChevronRight, ChevronDown, Trash2 } from "lucide-react";

// SON HAL #7 — "idari alanlara ve organizasyon hiyerarşisine silme/toplu
// silme fonksiyonu ekle". Ağaç yapısı bir SmartDataGrid değil, bu yüzden
// çoklu seçim burada kendi checkbox'larıyla (birim + pozisyon, iki AYRI
// Set) yönetilir; tekli silme her satırda bir çöp kutusu ikonu, toplu
// silme üstteki "Seçilenleri Sil" çubuğuyla.
function UnitNode({ node, depth = 0, selectedUnits, selectedPositions, onToggleUnit, onTogglePosition, onDeleteUnit, onDeletePosition }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={{ marginLeft: depth * 18 }} className="mb-1">
      <div className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-[var(--surface-2)] group">
        {node.children?.length > 0 ? (
          <button onClick={() => setOpen((o) => !o)} className="text-[var(--text-dim)]">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : <span className="w-[14px]" />}
        <input type="checkbox" checked={selectedUnits.has(node.id)} onChange={() => onToggleUnit(node.id)}
               data-testid={`unit-select-${node.id}`} />
        <Landmark size={14} className="text-[var(--primary)]" />
        <span className="font-medium text-sm">{node.name}</span>
        <span className="text-[10px] text-[var(--text-dim)]">({node.positions?.length || 0} pozisyon)</span>
        <button onClick={() => onDeleteUnit(node)} title="Birimi sil"
                className="ml-1 text-[var(--text-dim)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                data-testid={`unit-delete-${node.id}`}>
          <Trash2 size={12} />
        </button>
      </div>
      {node.positions?.map((p) => (
        <div key={p.id} style={{ marginLeft: (depth + 1) * 18 }} className="text-xs py-1 px-2 flex items-center gap-2 group">
          <input type="checkbox" checked={selectedPositions.has(p.id)} onChange={() => onTogglePosition(p.id)}
                 data-testid={`position-select-${p.id}`} />
          <Users size={12} className="text-[var(--text-dim)]" />
          <span>{p.title}</span>
          {p.occupants?.map((o) => (
            <span key={o.id} className="badge badge-neutral">{o.full_name || o.email || o.id}</span>
          ))}
          {(!p.occupants || p.occupants.length === 0) && <span className="text-[var(--text-dim)]">— boş —</span>}
          <button onClick={() => onDeletePosition(p)} title="Pozisyonu sil"
                  className="text-[var(--text-dim)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                  data-testid={`position-delete-${p.id}`}>
            <Trash2 size={11} />
          </button>
        </div>
      ))}
      {open && node.children?.map((c) => (
        <UnitNode key={c.id} node={c} depth={depth + 1}
                  selectedUnits={selectedUnits} selectedPositions={selectedPositions}
                  onToggleUnit={onToggleUnit} onTogglePosition={onTogglePosition}
                  onDeleteUnit={onDeleteUnit} onDeletePosition={onDeletePosition} />
      ))}
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

  // SON HAL #7 — silme / toplu silme
  const [selectedUnits, setSelectedUnits] = useState(new Set());
  const [selectedPositions, setSelectedPositions] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  function toggleUnit(id) {
    setSelectedUnits((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function togglePosition(id) {
    setSelectedPositions((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  async function deleteUnit(node) {
    if (!window.confirm(`"${node.name}" birimi silinsin mi?\n(Alt birimler/pozisyonlar etkilenmez, kayıt arşivlenir.)`)) return;
    try { await api.delete(`/organization-units/${node.id}`); loadAll(); }
    catch (err) { setError(err.response?.data?.detail || "Birim silinemedi"); }
  }
  async function deletePosition(p) {
    if (!window.confirm(`"${p.title}" pozisyonu silinsin mi?\n(Kayıt arşivlenir — geri alınabilir.)`)) return;
    try { await api.delete(`/positions/${p.id}`); loadAll(); }
    catch (err) { setError(err.response?.data?.detail || "Pozisyon silinemedi"); }
  }
  async function bulkDeleteSelected() {
    if (selectedUnits.size === 0 && selectedPositions.size === 0) return;
    if (!window.confirm(`${selectedUnits.size} birim ve ${selectedPositions.size} pozisyon silinsin mi?\n(Kayıtlar arşivlenir — geri alınabilir.)`)) return;
    setBulkBusy(true);
    try {
      if (selectedUnits.size > 0) await api.post("/organization-units/bulk-delete", { unit_ids: [...selectedUnits] });
      if (selectedPositions.size > 0) await api.post("/positions/bulk-delete", { position_ids: [...selectedPositions] });
      setSelectedUnits(new Set()); setSelectedPositions(new Set());
      loadAll();
    } catch (err) {
      setError(err.response?.data?.detail || "Toplu silme başarısız");
    } finally {
      setBulkBusy(false);
    }
  }

  // #6 — Portföy: bir personelin sorumlu olduğu köyler + oradaki çiftçi/parseller
  const [portfolioUser, setPortfolioUser] = useState("");
  const [portfolio, setPortfolio] = useState(null);
  const [portfolioBusy, setPortfolioBusy] = useState(false);

  async function loadPortfolio(uid) {
    setPortfolioUser(uid);
    setPortfolio(null);
    if (!uid) return;
    setPortfolioBusy(true);
    try {
      const { data } = await api.get(`/portfolio/${uid}`);
      setPortfolio(data);
    } catch {
      setPortfolio(null);
    } finally {
      setPortfolioBusy(false);
    }
  }

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
          doğrudan yöneticisi) onay hedefini bu yapı belirler. Saha sorumluluğu (portföy) ise
          <b> köy bazlıdır</b>: İdari Alanlar'da köye atanan sorumlu, o köydeki çiftçi ve parselleri devralır.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      {/* #6 — PORTFÖY: personelin sorumlu olduğu köyler + çiftçi/parsel özeti */}
      <div className="card p-4 mb-6" data-testid="portfolio-panel">
        <div className="text-sm font-medium mb-2">Portföy (Saha Sorumluluğu)</div>
        <select className="input max-w-sm" value={portfolioUser}
                onChange={(e) => loadPortfolio(e.target.value)} data-testid="portfolio-user">
          <option value="">Personel seçin…</option>
          {users.filter((u) => u.role !== "ciftci").map((u) => (
            <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.role})</option>
          ))}
        </select>

        {portfolioBusy && <div className="text-xs text-[var(--text-dim)] mt-3">Yükleniyor…</div>}
        {portfolio && (
          <div className="mt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div className="bg-[var(--surface-2)] rounded-lg p-3 text-center">
                <div className="font-display text-2xl">{portfolio.areas?.length || 0}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Sorumlu Köy</div>
              </div>
              <div className="bg-[var(--surface-2)] rounded-lg p-3 text-center">
                <div className="font-display text-2xl">{portfolio.farmer_count}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Çiftçi</div>
              </div>
              <div className="bg-[var(--surface-2)] rounded-lg p-3 text-center">
                <div className="font-display text-2xl">{portfolio.parcel_count}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Parsel</div>
              </div>
              <div className="bg-[var(--surface-2)] rounded-lg p-3 text-center">
                <div className="font-display text-2xl">{portfolio.total_area_dekar}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Toplam Alan (da)</div>
              </div>
            </div>
            {portfolio.areas?.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {portfolio.areas.map((a) => (
                  <span key={a.id} className="badge badge-neutral text-[11px]">{a.name}</span>
                ))}
              </div>
            ) : (
              <div className="text-xs text-[var(--text-dim)]">
                Bu personele hiç köy atanmamış — İdari Alanlar'dan bir köye "Sorumlu Personel" olarak atayın.
              </div>
            )}
          </div>
        )}
      </div>

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
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-display text-lg">Org Şeması</h3>
          {(selectedUnits.size > 0 || selectedPositions.size > 0) && (
            <button onClick={bulkDeleteSelected} disabled={bulkBusy} className="btn btn-ghost text-xs text-red-400"
                    data-testid="org-bulk-delete-btn">
              <Trash2 size={12} /> {bulkBusy ? "Siliniyor…" : `Seçilenleri Sil (${selectedUnits.size + selectedPositions.size})`}
            </button>
          )}
        </div>
        <div className="text-[10px] text-[var(--text-dim)] mb-2">Satırların solundaki kutucukla çoklu seçim yapabilir, üzerine gelip çöp kutusuyla tekli silebilirsiniz.</div>
        {tree.length === 0 && <div className="text-xs text-[var(--text-dim)] p-4 text-center">Henüz birim tanımlı değil — yukarıdan başlayın.</div>}
        {tree.map((n) => (
          <UnitNode key={n.id} node={n}
                    selectedUnits={selectedUnits} selectedPositions={selectedPositions}
                    onToggleUnit={toggleUnit} onTogglePosition={togglePosition}
                    onDeleteUnit={deleteUnit} onDeletePosition={deletePosition} />
        ))}
      </div>
    </div>
  );
}
