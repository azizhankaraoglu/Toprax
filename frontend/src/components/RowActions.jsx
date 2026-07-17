/**
 * RowActions — tablo satırları için ortak "Düzenle + Sil" aksiyonları.
 *
 * Amaç: Sözleşme/Ekim/Sulama/Kantar/Randevu gibi salt-listeleme sayfalarına
 * az kod tekrarıyla düzenleme (modal form) ve silme (onaylı) eklemek —
 * QuickAdd.jsx'in alan render mantığının kardeşi (aynı `fields` sözleşmesi).
 *
 * Props:
 *  - fields   : [{name,label,type,required,default,options,step,span2}] (düzenleme formu)
 *  - values   : mevcut satır (form ön-doldurma için)
 *  - onSave   : async (values) => {...}  (genelde api.put + reload)
 *  - onDelete : async () => {...}        (genelde api.delete + reload)
 *  - entityLabel : onay metninde geçen ad (ör. "sözleşme")
 *  - canEdit/canDelete : yetkiye göre butonları gizlemek için (varsayılan true)
 *
 * fields/onSave verilmezse sadece Sil, onDelete verilmezse sadece Düzenle görünür.
 */
import { useState } from "react";
import { Pencil, Trash2, X } from "lucide-react";

export default function RowActions({
  fields = null,
  values = {},
  onSave = null,
  onDelete = null,
  entityLabel = "kayıt",
  canEdit = true,
  canDelete = true,
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function startEdit() {
    setForm(Object.fromEntries((fields || []).map((f) => [f.name, values[f.name] ?? f.default ?? ""])));
    setError("");
    setEditing(true);
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSave(form);
      setEditing(false);
    } catch (err) {
      setError(err.response?.data?.detail || "Kaydedilemedi, alanları kontrol edin.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Bu ${entityLabel} silinsin mi?\n(Kayıt arşivlenir — geri alınabilir.)`)) return;
    setBusy(true);
    try {
      await onDelete();
    } catch (err) {
      alert(err.response?.data?.detail || "Silinemedi.");
    } finally {
      setBusy(false);
    }
  }

  const showEdit = canEdit && fields && onSave;
  const showDelete = canDelete && onDelete;

  return (
    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
      {showEdit && (
        <button onClick={startEdit} disabled={busy}
          className="p-1.5 rounded hover:bg-[var(--surface-2)] text-[var(--text-dim)] hover:text-[var(--primary)]"
          title="Düzenle" data-testid="row-edit">
          <Pencil size={14} />
        </button>
      )}
      {showDelete && (
        <button onClick={remove} disabled={busy}
          className="p-1.5 rounded hover:bg-red-500/10 text-[var(--text-dim)] hover:text-red-400"
          title="Sil" data-testid="row-delete">
          <Trash2 size={14} />
        </button>
      )}

      {editing && (
        <div className="fixed inset-0 z-[3000] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setEditing(false)}>
          <form onSubmit={save} onClick={(e) => e.stopPropagation()}
            className="card p-5 w-full max-w-lg space-y-3 max-h-[85vh] overflow-auto">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-lg">Düzenle</h3>
              <button type="button" onClick={() => setEditing(false)} className="text-[var(--text-dim)] hover:text-white">
                <X size={18} />
              </button>
            </div>
            {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded">{error}</div>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {fields.map((f) => (
                <div key={f.name} className={f.span2 ? "md:col-span-2" : ""}>
                  <label className="text-xs text-[var(--text-dim)] mb-1 block">{f.label}{f.required && " *"}</label>
                  {f.type === "select" ? (
                    <select className="input" required={f.required}
                      value={form[f.name] ?? ""}
                      onChange={(e) => setForm((s) => ({ ...s, [f.name]: e.target.value }))}>
                      <option value="">Seç...</option>
                      {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : f.type === "textarea" ? (
                    <textarea className="input" rows={f.rows || 3} required={f.required}
                      value={form[f.name] ?? ""}
                      onChange={(e) => setForm((s) => ({ ...s, [f.name]: e.target.value }))} />
                  ) : (
                    <input className="input" type={f.type || "text"} step={f.step} required={f.required}
                      value={form[f.name] ?? ""}
                      onChange={(e) => setForm((s) => ({ ...s, [f.name]: e.target.value }))} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={busy} className="btn btn-primary">
                {busy ? "Kaydediliyor…" : "Kaydet"}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="btn btn-ghost">İptal</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
