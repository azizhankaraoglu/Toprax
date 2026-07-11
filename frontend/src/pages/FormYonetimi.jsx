import { useEffect, useMemo, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import {
  Layers, Plus, X, Check, Pencil, EyeOff, Eye, ArrowUp, ArrowDown,
  ListTree, ChevronRight, Trash2,
} from "lucide-react";

// =====================================================================
// ALAN TANIMLARI (Form Yönetimi)
// =====================================================================
export function AlanTanimlari() {
  const [meta, setMeta] = useState(null);
  const [lookupGroups, setLookupGroups] = useState([]);
  const [activeModule, setActiveModule] = useState(null);
  const [fields, setFields] = useState([]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null); // field def obje veya null
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/field-definitions/meta"),
      api.get("/lookups/groups"),
    ]).then(([m, g]) => {
      setMeta(m.data);
      setLookupGroups(g.data.filter((x) => x.is_active !== false));
      setActiveModule(m.data.modules[0]?.key);
    });
  }, []);

  const loadFields = (module) => {
    if (!module) return;
    setLoading(true);
    api.get("/field-definitions", { params: { module } }).then((r) => {
      setFields(r.data.sort((a, b) => a.order - b.order));
      setLoading(false);
    });
  };

  useEffect(() => { loadFields(activeModule); }, [activeModule]);

  async function move(field, dir) {
    const sorted = [...fields].sort((a, b) => a.order - b.order);
    const idx = sorted.findIndex((f) => f.id === field.id);
    const swapWith = sorted[idx + dir];
    if (!swapWith) return;
    await api.post("/field-definitions/reorder", {
      items: [
        { id: field.id, order: swapWith.order },
        { id: swapWith.id, order: field.order },
      ],
    });
    loadFields(activeModule);
  }

  async function toggleVisible(field) {
    await api.put(`/field-definitions/${field.id}`, { visible: !field.visible });
    loadFields(activeModule);
  }

  async function deactivate(field) {
    if (!window.confirm(`"${field.label}" alanını pasife almak istediğinize emin misiniz? Girilmiş veriler etkilenmez.`)) return;
    await api.delete(`/field-definitions/${field.id}`);
    loadFields(activeModule);
  }

  const lookupCapable = useMemo(() => new Set(meta?.lookup_capable_types || []), [meta]);

  if (!meta) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="field-definitions-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM AYARLARI</div>
          <h1 className="font-display text-4xl">Form Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Çiftçi, Parsel, Sözleşme, Ekim Planlama ve Toprak ekranlarındaki alanların
            zorunluluğunu, görünürlüğünü, sırasını ve tipini yönetin.
          </p>
        </div>
        <button onClick={() => setCreating(true)} className="btn btn-primary">
          <Plus size={14} /> Yeni Alan
        </button>
      </header>

      {/* Modül sekmeleri */}
      <div className="flex gap-1 mb-5 border-b border-[var(--border)]">
        {meta.modules.map((m) => (
          <button
            key={m.key}
            onClick={() => setActiveModule(m.key)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${
              activeModule === m.key
                ? "border-[var(--primary)] text-[var(--primary)]"
                : "border-transparent text-[var(--text-dim)] hover:text-white"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-[var(--text-dim)] text-sm">Yükleniyor…</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3 w-16">Sıra</th>
                <th className="p-3">Etiket / Alan Anahtarı</th>
                <th className="p-3">Tip</th>
                <th className="p-3">Sekme</th>
                <th className="p-3">Zorunlu</th>
                <th className="p-3">Görünür</th>
                <th className="p-3">Hassas</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f, idx) => (
                <tr key={f.id} className={`border-b border-[var(--border)] hover:bg-[var(--surface-2)] ${f.is_active === false ? "opacity-40" : ""}`}>
                  <td className="p-3">
                    <div className="flex gap-1">
                      <button onClick={() => move(f, -1)} disabled={idx === 0} className="text-[var(--text-dim)] hover:text-white disabled:opacity-20"><ArrowUp size={13} /></button>
                      <button onClick={() => move(f, 1)} disabled={idx === fields.length - 1} className="text-[var(--text-dim)] hover:text-white disabled:opacity-20"><ArrowDown size={13} /></button>
                    </div>
                  </td>
                  <td className="p-3">
                    <div>{f.label}</div>
                    <div className="text-[11px] text-[var(--text-dim)] font-mono">{f.field_key}</div>
                  </td>
                  <td className="p-3"><span className="badge badge-b">{f.field_type}</span></td>
                  <td className="p-3 text-xs text-[var(--text-dim)]">{f.tab || "—"}</td>
                  <td className="p-3">
                    <span className={`badge ${f.required ? "badge-c" : "badge-neutral"}`}>{f.required ? "Zorunlu" : "Opsiyonel"}</span>
                  </td>
                  <td className="p-3">
                    <button onClick={() => toggleVisible(f)} className={`badge ${f.visible ? "badge-a" : "badge-d"}`}>
                      {f.visible ? <Eye size={11} /> : <EyeOff size={11} />} {f.visible ? "Görünür" : "Gizli"}
                    </button>
                  </td>
                  <td className="p-3">
                    {f.sensitive && <span className="badge badge-d">Hassas</span>}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => setEditing(f)} className="text-[var(--text-dim)] hover:text-white"><Pencil size={14} /></button>
                      {f.is_active !== false && (
                        <button onClick={() => deactivate(f)} className="text-red-400 hover:text-red-300"><Trash2 size={14} /></button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {fields.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-[var(--text-dim)] text-sm">Bu modülde henüz özel alan tanımlanmamış.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {(creating || editing) && (
        <FieldFormDialog
          meta={meta}
          lookupGroups={lookupGroups}
          activeModule={activeModule}
          field={editing}
          fields={fields}
          onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={() => { setCreating(false); setEditing(null); loadFields(activeModule); }}
        />
      )}
    </div>
  );
}

function FieldFormDialog({ meta, lookupGroups, activeModule, field, fields, onClose, onSaved }) {
  const isEdit = !!field;
  const [form, setForm] = useState(() => ({
    module: field?.module || activeModule,
    field_key: field?.field_key || "",
    label: field?.label || "",
    field_type: field?.field_type || "text",
    required: field?.required || false,
    visible: field?.visible ?? true,
    help_text: field?.help_text || "",
    placeholder: field?.placeholder || "",
    default_value: field?.default_value || "",
    tab: field?.tab || "",
    lookup_group_id: field?.lookup_group_id || "",
    sensitive: field?.sensitive || false,
    depends_on_field: field?.depends_on_field || "",
  }));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const isLookupCapable = meta.lookup_capable_types.includes(form.field_type);
  // IT-01.5 — kaskad: sadece kendisi de bir lookup grubuna bağlı (aksi halde
  // filtrelenecek bir seçili "değer" -> "lookup_value id" eşlemesi kurulamaz),
  // kendisinden farklı, aynı modüldeki alanlar üst-alan adayı olabilir.
  const cascadeCandidates = (fields || []).filter(
    (f) => f.field_key !== form.field_key && f.lookup_group_id
  );

  async function save() {
    setSaving(true);
    setError("");
    try {
      const payload = { ...form };
      if (!isLookupCapable) {
        payload.lookup_group_id = null;
        payload.depends_on_field = null;
      } else {
        if (!payload.lookup_group_id) payload.lookup_group_id = null;
        if (!payload.depends_on_field) payload.depends_on_field = null;
      }
      if (isEdit) {
        await api.put(`/field-definitions/${field.id}`, payload);
      } else {
        await api.post("/field-definitions", payload);
      }
      onSaved();
    } catch (err) {
      setError(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="card p-5 max-w-[560px] w-full max-h-[85vh] overflow-y-auto scrollbar" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg">{isEdit ? "Alanı Düzenle" : "Yeni Alan"}</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-3">{error}</div>}

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Etiket (ekranda görünen) *</label>
            <input className="input" value={form.label} onChange={(e) => set("label", e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Alan Anahtarı (field_key) *</label>
            <input className="input font-mono text-xs" placeholder="orn_alan_adi" disabled={isEdit}
                   value={form.field_key} onChange={(e) => set("field_key", e.target.value.trim())} />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Alan Tipi *</label>
            <select className="input" value={form.field_type} onChange={(e) => set("field_type", e.target.value)}>
              {meta.field_types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {isLookupCapable && (
            <div className="col-span-2">
              <label className="text-xs text-[var(--text-dim)] mb-1 block">Lookup Grubu</label>
              <select className="input" value={form.lookup_group_id || ""} onChange={(e) => set("lookup_group_id", e.target.value)}>
                <option value="">— Bağlanmasın (statik seçenek kullanılacaksa boş bırakın) —</option>
                {lookupGroups.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </select>
            </div>
          )}

          {isLookupCapable && (
            <div className="col-span-2">
              <label className="text-xs text-[var(--text-dim)] mb-1 block">Bağımlı Olduğu Alan (Kaskad)</label>
              <select className="input" value={form.depends_on_field || ""} onChange={(e) => set("depends_on_field", e.target.value)}>
                <option value="">— Bağımsız (her zaman tüm liste görünür) —</option>
                {cascadeCandidates.map((f) => <option key={f.field_key} value={f.field_key}>{f.label} ({f.field_key})</option>)}
              </select>
              <div className="text-[10px] text-[var(--text-dim)] mt-1">
                Seçilirse bu alan, kullanıcı seçilen alanı doldurana kadar boş kalır;
                doldurunca sadece onun lookup grubunun altındaki (parent_id ile bağlı) değerleri listeler.
                Örnek: İlçe, İl'e bağımlı.
              </div>
            </div>
          )}

          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Sekme (Tab)</label>
            <input className="input" placeholder="örn. Kimlik Bilgileri" value={form.tab} onChange={(e) => set("tab", e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Varsayılan Değer</label>
            <input className="input" value={form.default_value} onChange={(e) => set("default_value", e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Placeholder</label>
            <input className="input" value={form.placeholder} onChange={(e) => set("placeholder", e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Yardım Metni</label>
            <textarea className="input" rows={2} value={form.help_text} onChange={(e) => set("help_text", e.target.value)} />
          </div>

          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={form.required} onChange={(e) => set("required", e.target.checked)} />
            Zorunlu alan
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={form.visible} onChange={(e) => set("visible", e.target.checked)} />
            Formda görünsün
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={form.sensitive} onChange={(e) => set("sensitive", e.target.checked)} />
            Hassas (Admin altı roller için maskelenir)
          </label>
        </div>

        <button onClick={save} disabled={saving || !form.label || !form.field_key} className="btn btn-primary w-full justify-center mt-5">
          <Check size={14} /> {saving ? "Kaydediliyor…" : "Kaydet"}
        </button>
      </div>
    </div>
  );
}

// =====================================================================
// LOOKUP YÖNETİMİ
// =====================================================================
export function LookupYonetimi() {
  const [groups, setGroups] = useState([]);
  const [activeGroup, setActiveGroup] = useState(null);
  const [values, setValues] = useState([]);
  const [parentValues, setParentValues] = useState([]); // IT-01.5 — activeGroup.parent_group_id varsa üst grubun değerleri
  const [loadingValues, setLoadingValues] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkParentId, setBulkParentId] = useState("");
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  const loadGroups = () => api.get("/lookups/groups").then((r) => {
    setGroups(r.data);
    if (!activeGroup && r.data.length > 0) setActiveGroup(r.data[0]);
  });

  useEffect(() => { loadGroups(); /* eslint-disable-next-line */ }, []);

  const groupsById = useMemo(() => Object.fromEntries(groups.map((g) => [g.id, g])), [groups]);

  const loadValues = (group) => {
    if (!group) return;
    setLoadingValues(true);
    setBulkText(""); setBulkParentId(""); setBulkResult(null);
    Promise.all([
      api.get(`/lookups/groups/${group.id}/values`),
      group.parent_group_id ? api.get(`/lookups/groups/${group.parent_group_id}/values`) : Promise.resolve({ data: [] }),
    ]).then(([own, parent]) => {
      setValues(own.data.sort((a, b) => a.order - b.order));
      setParentValues(parent.data.sort((a, b) => a.order - b.order));
      setLoadingValues(false);
    });
  };

  useEffect(() => { loadValues(activeGroup); /* eslint-disable-next-line */ }, [activeGroup]);

  async function toggleValueActive(v) {
    await api.put(`/lookups/values/${v.id}`, { is_active: !(v.is_active !== false) });
    loadValues(activeGroup);
  }

  // IT-01.5 — "Üst Değer" seçilirken kaynak: grup parent_group_id taşıyorsa
  // ÜST GRUBUN değerleri (çapraz-grup kaskad, örn. ilçe -> il), taşımıyorsa
  // grubun KENDİ değerleri (kendine ağaç, eski davranış).
  const parentOptionsSource = activeGroup?.parent_group_id ? parentValues : values;
  // Tabloda "Üst Değer" etiketini çözmek için: kendi değerleri + (varsa) üst grup değerleri.
  const valuesById = useMemo(
    () => Object.fromEntries([...parentValues, ...values].map((v) => [v.id, v])),
    [values, parentValues]
  );

  async function submitBulk() {
    if (!activeGroup || !bulkText.trim()) return;
    setBulkBusy(true);
    setBulkResult(null);
    try {
      const r = await api.post(`/lookups/groups/${activeGroup.id}/values/bulk-import`, {
        text: bulkText, parent_id: bulkParentId || null,
      });
      setBulkResult(r.data);
      setBulkText("");
      loadValues(activeGroup);
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="lookup-management-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM AYARLARI</div>
        <h1 className="font-display text-4xl">Lookup Yönetimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Sulama Tipi, Ürün, Risk Seviyesi gibi seçim listelerini burada yönetin.
          Form Yönetimi'nde bir alanı buradaki gruplardan birine bağlayabilirsiniz.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-5">
        {/* Grup listesi */}
        <div className="card p-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-sm text-[var(--text-dim)] uppercase tracking-wider">Gruplar</h3>
          </div>
          <QuickAddPanel
            title="Yeni Grup"
            testId="lookup-group-add"
            fields={[
              { name: "key", label: "Anahtar (key)", required: true },
              { name: "label", label: "Görünen Ad", required: true },
              {
                name: "parent_group_id", label: "Üst Grup (kaskad için, opsiyonel)", type: "select",
                options: groups.map((g) => ({ value: g.id, label: g.label })),
              },
            ]}
            onSubmit={async (v) => {
              await api.post("/lookups/groups", { ...v, parent_group_id: v.parent_group_id || null });
              loadGroups();
            }}
          />
          <div className="space-y-1 mt-2">
            {groups.map((g) => (
              <button
                key={g.id}
                onClick={() => setActiveGroup(g)}
                className={`w-full flex items-center justify-between text-left text-sm px-3 py-2 rounded-lg transition-colors ${
                  activeGroup?.id === g.id ? "bg-[var(--primary)] text-black" : "hover:bg-[var(--surface-2)] text-[var(--text)]"
                }`}
              >
                <span className="flex items-center gap-2">
                  <Layers size={13} />
                  <span>
                    {g.label}
                    {g.parent_group_id && groupsById[g.parent_group_id] && (
                      <span className="block text-[10px] opacity-70">→ {groupsById[g.parent_group_id].label}</span>
                    )}
                  </span>
                </span>
                <ChevronRight size={13} />
              </button>
            ))}
            {groups.length === 0 && <div className="text-xs text-[var(--text-dim)] px-2 py-4">Henüz grup yok.</div>}
          </div>
        </div>

        {/* Değerler */}
        <div className="card p-4">
          {!activeGroup ? (
            <div className="text-[var(--text-dim)] text-sm">Soldan bir grup seçin.</div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-4">
                <ListTree size={16} className="text-[var(--primary)]" />
                <h3 className="font-display text-lg">{activeGroup.label}</h3>
                <span className="text-xs text-[var(--text-dim)] font-mono">({activeGroup.key})</span>
                {activeGroup.parent_group_id && groupsById[activeGroup.parent_group_id] && (
                  <span className="badge badge-neutral text-[10px]">Üst grup: {groupsById[activeGroup.parent_group_id].label}</span>
                )}
              </div>

              <QuickAddPanel
                title="Yeni Değer"
                testId="lookup-value-add"
                fields={[
                  { name: "value", label: "Sistem Değeri", required: true },
                  { name: "label", label: "Görünen Ad", required: true },
                  {
                    name: "parent_id",
                    label: activeGroup.parent_group_id
                      ? `Üst Değer (${groupsById[activeGroup.parent_group_id]?.label || "üst grup"}, opsiyonel)`
                      : "Üst Değer (hiyerarşi için, opsiyonel)",
                    type: "select",
                    options: parentOptionsSource.map((v) => ({ value: v.id, label: v.label })),
                  },
                ]}
                onSubmit={async (v) => {
                  const payload = { ...v, parent_id: v.parent_id || null };
                  await api.post(`/lookups/groups/${activeGroup.id}/values`, payload);
                  loadValues(activeGroup);
                }}
              />

              <div className="card p-3 mt-3 bg-[var(--surface-2)]">
                <div className="text-xs font-medium mb-2">Toplu Değer Girişi (kopyala-yapıştır, satır başına bir değer)</div>
                {activeGroup.parent_group_id && (
                  <select className="input text-xs mb-2" value={bulkParentId} onChange={(e) => setBulkParentId(e.target.value)}>
                    <option value="">— Üst Değer seçin ({groupsById[activeGroup.parent_group_id]?.label}) —</option>
                    {parentOptionsSource.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                  </select>
                )}
                <textarea
                  className="input text-xs font-mono"
                  rows={5}
                  placeholder={"Her satıra bir değer.\nİstersen \"sistem_degeri|Görünen Ad\" biçiminde de yazabilirsin,\naksi halde sistem değeri otomatik üretilir."}
                  value={bulkText}
                  onChange={(e) => setBulkText(e.target.value)}
                  data-testid="lookup-bulk-textarea"
                />
                <button
                  className="btn btn-primary text-xs mt-2"
                  disabled={bulkBusy || !bulkText.trim() || (activeGroup.parent_group_id && !bulkParentId)}
                  onClick={submitBulk}
                  data-testid="lookup-bulk-submit"
                >
                  {bulkBusy ? "Ekleniyor…" : "Toplu Ekle"}
                </button>
                {bulkResult && (
                  <div className="text-[11px] text-[var(--text-dim)] mt-2">
                    {bulkResult.created} eklendi, {bulkResult.skipped_existing} zaten vardı (atlandı)
                    {bulkResult.invalid?.length > 0 && `, ${bulkResult.invalid.length} satır geçersiz`}.
                  </div>
                )}
              </div>

              {loadingValues ? (
                <div className="text-[var(--text-dim)] text-sm">Yükleniyor…</div>
              ) : (
                <table className="w-full text-sm mt-3">
                  <thead>
                    <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                      <th className="p-2">Değer</th>
                      <th className="p-2">Sistem Değeri</th>
                      <th className="p-2">Üst Değer</th>
                      <th className="p-2">Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {values.map((v) => (
                      <tr key={v.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                        <td className="p-2">{v.label}</td>
                        <td className="p-2 text-xs text-[var(--text-dim)] font-mono">{v.value}</td>
                        <td className="p-2 text-xs text-[var(--text-dim)]">{v.parent_id ? (valuesById[v.parent_id]?.label || "—") : "—"}</td>
                        <td className="p-2">
                          <button onClick={() => toggleValueActive(v)} className={`badge ${v.is_active !== false ? "badge-a" : "badge-d"}`}>
                            {v.is_active !== false ? "Aktif" : "Pasif"}
                          </button>
                        </td>
                      </tr>
                    ))}
                    {values.length === 0 && (
                      <tr><td colSpan={4} className="p-4 text-center text-[var(--text-dim)] text-xs">Bu grupta henüz değer yok.</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
