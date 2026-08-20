/**
 * SABİT KATALOG YÖNETİMİ — 2026-08-19
 *
 * `backend/catalog_registry.py`'nin admin ekranı. Kullanıcı isteği: geçmiş
 * geliştirmelerde koda gömülmüş sabitlerin (ör. "Tespit Edilen Organizmalar",
 * toprak biyolojisi ölçüm eşikleri) admin tarafından eklenebilir/
 * değiştirilebilir/silinebilir olması.
 *
 * Alan listesi SABİT DEĞİL — backend `GET /catalogs` her kataloğun alan
 * şemasını (`fields[]`) döner, form buradan üretilir. Yeni bir katalog
 * yönetilebilir yapmak için SADECE `CATALOG_REGISTRY`'ye satır eklenir,
 * bu dosya DEĞİŞMEZ (lib/mapWidgets registry'sinin felsefesiyle AYNI).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Database, Plus, Trash2, RotateCcw, Save, X, Loader2, Info } from "lucide-react";

const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(", ");
  return e?.message || "Bilinmeyen hata";
};

const SOURCE_BADGE = {
  default: { label: "Varsayılan", cls: "badge-neutral" },
  override: { label: "Düzenlendi", cls: "badge-b" },
  custom: { label: "Eklendi", cls: "badge-a" },
};

export default function CatalogManager() {
  const [catalogs, setCatalogs] = useState([]);
  const [active, setActive] = useState(null);
  const [data, setData] = useState(null);
  const [editKey, setEditKey] = useState(null);
  const [draft, setDraft] = useState({});
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const flash = (kind, text) => { setMsg({ kind, text }); setTimeout(() => setMsg(null), 5000); };

  useEffect(() => {
    api.get("/catalogs")
      .then((r) => { setCatalogs(r.data || []); if (r.data?.[0]) setActive(r.data[0].key); })
      .catch((e) => flash("err", errText(e)));
  }, []);

  const load = (key) => {
    if (!key) return;
    api.get(`/catalogs/${key}/items`)
      .then((r) => setData(r.data))
      .catch((e) => flash("err", errText(e)));
  };
  useEffect(() => { load(active); /* eslint-disable-next-line */ }, [active]);

  const fields = data?.catalog?.fields || [];
  const items = data?.items || [];

  function startEdit(item) {
    setAdding(false);
    setEditKey(item.key);
    setDraft(Object.fromEntries(fields.map((f) => [f.key, item[f.key] ?? ""])));
  }

  function startAdd() {
    setEditKey(null);
    setAdding(true);
    setDraft(Object.fromEntries(fields.map((f) => [f.key, f.type === "bool" ? false : ""])));
  }

  async function save() {
    const key = (draft.key || "").trim();
    if (!key) return flash("err", "Sistem anahtarı zorunlu.");
    const missing = fields.filter((f) => f.required && !String(draft[f.key] ?? "").trim());
    if (missing.length) return flash("err", `Zorunlu alan: ${missing.map((f) => f.label).join(", ")}`);

    setBusy(true);
    const values = {};
    fields.forEach((f) => {
      if (f.key === "key") return;
      let v = draft[f.key];
      if (v === "" || v === undefined) return;
      if (f.type === "number") v = Number(v);
      values[f.key] = v;
    });
    try {
      await api.put(`/catalogs/${active}/items/${key}`, { key, values });
      flash("ok", adding ? "Yeni kalem eklendi." : "Kalem güncellendi.");
      setEditKey(null); setAdding(false); load(active);
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function remove(item) {
    if (!window.confirm(`"${item.label || item.key}" kaleminden vazgeçilsin mi? (pasife alınır, "Varsayılana Döndür" ile geri gelir)`)) return;
    try {
      await api.delete(`/catalogs/${active}/items/${item.key}`);
      flash("ok", "Kalem pasife alındı."); load(active);
    } catch (e) { flash("err", errText(e)); }
  }

  async function reset(item) {
    try {
      const r = await api.post(`/catalogs/${active}/items/${item.key}/reset`);
      flash("ok", r.data.restored_to_default
        ? "Kalem sistem varsayılanına döndürüldü."
        : "Özel kalem tamamen kaldırıldı.");
      load(active);
    } catch (e) { flash("err", errText(e)); }
  }

  function fieldInput(f) {
    const v = draft[f.key];
    const set = (val) => setDraft((d) => ({ ...d, [f.key]: val }));
    if (f.type === "bool") {
      return <input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} />;
    }
    if (f.type === "select") {
      return (
        <select className="input w-full" value={v ?? ""} onChange={(e) => set(e.target.value)}>
          <option value="">—</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    return (
      <input className="input w-full" type={f.type === "number" ? "number" : "text"}
             value={v ?? ""} onChange={(e) => set(e.target.value)}
             disabled={f.immutable && !adding}
             placeholder={f.immutable && !adding ? "(değiştirilemez)" : ""} />
    );
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="catalog-manager">
      <header className="mb-4">
        <h2 className="font-display text-2xl flex items-center gap-2">
          <Database size={20} /> Sabit Katalogları
        </h2>
        <p className="text-[var(--text-dim)] text-sm mt-1 max-w-3xl">
          Motorların kullandığı kod-seviyesi sabitler. Sistem varsayılanları her
          zaman yerinde durur; buradan yaptığınız değişiklik onların üzerine biner
          ve <b>"Varsayılana Döndür"</b> ile her an geri alınabilir.
        </p>
      </header>

      {msg && (
        <div className={`card p-3 mb-4 text-sm ${msg.kind === "ok" ? "text-[var(--primary)]" : "text-red-400"}`}>
          {msg.text}
        </div>
      )}

      <div className="flex gap-2 mb-4 flex-wrap">
        {catalogs.map((c) => (
          <button key={c.key} onClick={() => { setActive(c.key); setEditKey(null); setAdding(false); }}
                  data-testid={`catalog-${c.key}`}
                  className={`btn text-xs ${active === c.key ? "btn-primary" : "btn-ghost"}`}>
            {c.label} <span className="opacity-70">({c.item_count})</span>
          </button>
        ))}
      </div>

      {data && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <p className="text-xs text-[var(--text-dim)] flex items-center gap-1.5">
              <Info size={13} /> {data.catalog.description}
            </p>
            <button className="btn btn-ghost text-xs" onClick={startAdd} data-testid="catalog-add">
              <Plus size={14} /> Yeni Kalem
            </button>
          </div>

          {(adding || editKey) && (
            <div className="card p-4 mb-4" data-testid="catalog-form">
              <div className="font-medium text-sm mb-3">
                {adding ? "Yeni Kalem" : `Düzenle: ${editKey}`}
              </div>
              <div className="grid md:grid-cols-3 gap-3">
                {fields.map((f) => (
                  <label key={f.key} className="text-xs">
                    {f.label}{f.required && " *"}
                    <div className="mt-1">{fieldInput(f)}</div>
                  </label>
                ))}
              </div>
              <div className="flex gap-2 mt-3">
                <button className="btn btn-primary text-xs" onClick={save} disabled={busy}>
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Kaydet
                </button>
                <button className="btn btn-ghost text-xs"
                        onClick={() => { setEditKey(null); setAdding(false); }}>
                  <X size={14} /> Vazgeç
                </button>
              </div>
            </div>
          )}

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                <tr className="border-b border-[var(--border)]">
                  {fields.slice(0, 5).map((f) => <th key={f.key} className="text-left p-3">{f.label}</th>)}
                  <th className="text-left p-3">Durum</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const inactive = it.is_active === false;
                  const src = SOURCE_BADGE[it._source] || SOURCE_BADGE.default;
                  return (
                    <tr key={it.key}
                        className={`border-b border-[var(--border)] ${inactive ? "opacity-45" : ""}`}
                        data-testid={`catalog-row-${it.key}`}>
                      {fields.slice(0, 5).map((f) => (
                        <td key={f.key} className="p-3">
                          {f.type === "bool"
                            ? (it[f.key] ? "Evet" : "—")
                            : (it[f.key] ?? "—").toString().slice(0, 70)}
                        </td>
                      ))}
                      <td className="p-3">
                        {inactive
                          ? <span className="badge badge-d">Silindi</span>
                          : <span className={`badge ${src.cls}`}>{src.label}</span>}
                      </td>
                      <td className="p-3 text-right whitespace-nowrap">
                        {!inactive && (
                          <>
                            <button className="btn btn-ghost text-xs" onClick={() => startEdit(it)}>Düzenle</button>
                            <button className="btn btn-ghost text-xs text-red-400" onClick={() => remove(it)}>
                              <Trash2 size={12} />
                            </button>
                          </>
                        )}
                        {(it._source !== "default" || inactive) && (
                          <button className="btn btn-ghost text-xs" title="Sistem varsayılanına döndür"
                                  onClick={() => reset(it)}>
                            <RotateCcw size={12} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
