import { useEffect, useMemo, useState } from "react";
import api, { BACKEND_URL } from "@/api";
import { Upload, X, FileText } from "lucide-react";

/**
 * Sprint A1 — field_definitions altyapısını kullanarak bir modülün
 * (farmers/parcels/contracts/plantings/soil) dinamik alanlarını otomatik
 * render eder. Form Yönetimi ekranında yapılan değişiklikler (görünürlük,
 * zorunluluk, sıra, lookup) BURADA KOD DEĞİŞTİRMEDEN yansır — Sprint A1'in
 * temel amacı budur.
 *
 * Kullanım (create — dosya alanları "kayıttan sonra doldurulur" notu gösterir):
 *   <DynamicFieldsSection module="farmers" values={extra} onChange={(k, v) => setExtra(e => ({...e, [k]: v}))} />
 *   ...
 *   await api.post("/farmers", { ...coreForm, ...extra });
 *
 * Kullanım (edit — entityId verilirse file/image/multifile alanları IT-04
 * dosya yükleme widget'ı olarak aktif render edilir):
 *   <DynamicFieldsSection module="farmers" entityId={id} values={editForm} onChange={...} />
 *
 * Konum tipleri (geojson/coordinate) hâlâ UI karşılığı olmayan tiplerdir —
 * bilgi notu gösterilir.
 */
const NOT_YET_SUPPORTED = new Set(["geojson", "coordinate"]);
const FILE_TYPES = new Set(["file", "image", "multifile"]);

export default function DynamicFieldsSection({ module, values, onChange, title = "Ek Bilgiler", entityId }) {
  const [fields, setFields] = useState(null);
  const [lookupValuesByGroup, setLookupValuesByGroup] = useState({});

  useEffect(() => {
    let cancelled = false;
    api.get("/field-definitions", { params: { module } }).then(async (r) => {
      const visible = r.data
        .filter((f) => f.is_active !== false && f.visible)
        .sort((a, b) => a.order - b.order);
      if (cancelled) return;
      setFields(visible);

      const groupIds = [...new Set(visible.map((f) => f.lookup_group_id).filter(Boolean))];
      const entries = await Promise.all(
        groupIds.map((gid) => api.get(`/lookups/groups/${gid}/values`).then((res) => [gid, res.data]))
      );
      if (!cancelled) setLookupValuesByGroup(Object.fromEntries(entries));
    });
    return () => { cancelled = true; };
  }, [module]);

  const grouped = useMemo(() => {
    if (!fields) return [];
    const byTab = {};
    for (const f of fields) {
      const tab = f.tab || "Diğer";
      (byTab[tab] = byTab[tab] || []).push(f);
    }
    return Object.entries(byTab);
  }, [fields]);

  // IT-01.5 — kaskad select: field_key -> field tanımı (depends_on_field'ın
  // işaret ettiği "üst alan"ı bulmak için).
  const fieldsByKey = useMemo(
    () => Object.fromEntries((fields || []).map((f) => [f.field_key, f])),
    [fields]
  );

  if (!fields || fields.length === 0) return null;

  return (
    <div className="space-y-5">
      {title && <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider pt-2 border-t border-[var(--border)]">{title}</div>}
      {grouped.map(([tab, tabFields]) => (
        <div key={tab}>
          <div className="text-xs font-medium text-[var(--primary)] mb-2">{tab}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {tabFields.map((f) => {
              // Kaskad: bu alan depends_on_field taşıyorsa, üst alanın ŞU ANKİ
              // seçili "value"sunu üst alanın lookup grubundaki karşılık gelen
              // lookup_value id'sine çeviririz — bu id, kendi grubumuzdaki
              // değerlerin parent_id'siyle eşleştirilir (bkz. DynamicField).
              const parentField = f.depends_on_field ? fieldsByKey[f.depends_on_field] : null;
              const parentLookupValues = parentField?.lookup_group_id
                ? lookupValuesByGroup[parentField.lookup_group_id]
                : undefined;
              // parentLookupValues henüz yüklenmemişse (async fetch tamamlanmadan
              // önceki geçici render) cascadeReady=false — bu durumda DynamicField
              // henüz eldeki değeri "geçersiz" sanıp TEMİZLEMEZ (bkz. DynamicField).
              const cascadeReady = !parentField || Array.isArray(parentLookupValues);
              const cascadeParentValueId = cascadeReady && parentLookupValues
                ? parentLookupValues.find((pv) => pv.value === values[f.depends_on_field])?.id
                : undefined;
              return (
                <DynamicField
                  key={f.id}
                  field={f}
                  value={values[f.field_key]}
                  lookupValues={f.lookup_group_id ? lookupValuesByGroup[f.lookup_group_id] : null}
                  onChange={(v) => onChange(f.field_key, v)}
                  module={module}
                  entityId={entityId}
                  cascadeParentField={parentField}
                  cascadeParentValueId={cascadeParentValueId}
                  cascadeReady={cascadeReady}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function DynamicField({ field, value, lookupValues, onChange, module, entityId, cascadeParentField, cascadeParentValueId, cascadeReady }) {
  const wide = ["textarea", "url"].includes(field.field_type);
  const label = (
    <label className="text-xs text-[var(--text-dim)] mb-1 block">
      {field.label}{field.required && " *"}
    </label>
  );

  // IT-01.5 — kaskad select: sadece lookup'a bağlı select/radio/lookup/
  // autocomplete alanlarında anlamlıdır (statik `options` listesinde
  // parent_id verisi yok, bu yüzden depends_on_field orada no-op kalır).
  const isCascadeSelect = !!field.depends_on_field && !!lookupValues
    && ["select", "radio", "lookup", "autocomplete"].includes(field.field_type);
  const cascadeOptions = useMemo(() => {
    if (!isCascadeSelect) return null;
    if (!cascadeReady || !cascadeParentValueId) return [];
    return lookupValues
      .filter((v) => v.is_active !== false && v.parent_id === cascadeParentValueId)
      .map((v) => ({ value: v.value, label: v.label }));
  }, [isCascadeSelect, cascadeReady, cascadeParentValueId, lookupValues]);

  // Üst alanın seçimi değiştiğinde (veya kaskad verisi ilk kez hazır olduğunda)
  // artık geçerli olmayan bir alt seçim varsa otomatik temizler. cascadeReady
  // false iken (lookup verisi henüz yüklenmedi) ÇALIŞMAZ — aksi halde edit
  // ekranında mevcut geçerli bir eşleşme (örn. il=Konya, ilce=Selçuklu) veri
  // henüz gelmeden yanlışlıkla temizlenebilirdi.
  useEffect(() => {
    if (isCascadeSelect && cascadeReady && value && cascadeOptions && !cascadeOptions.some((o) => o.value === value)) {
      onChange("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cascadeParentValueId, cascadeReady]);

  if (FILE_TYPES.has(field.field_type)) {
    return <FileFieldWidget field={field} module={module} entityId={entityId} />;
  }

  if (NOT_YET_SUPPORTED.has(field.field_type)) {
    return (
      <div className={wide ? "md:col-span-2" : ""}>
        {label}
        <div className="input text-xs text-[var(--text-dim)] flex items-center opacity-60">
          Bu alan tipi ({field.field_type}) için doküman/konum yönetimi yakında eklenecek.
        </div>
      </div>
    );
  }

  if (field.field_type === "checkbox" || field.field_type === "switch") {
    return (
      <label className="flex items-center gap-2 text-xs cursor-pointer pt-5">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} required={field.required} />
        {field.label}{field.required && " *"}
      </label>
    );
  }

  if (["select", "radio", "lookup", "autocomplete"].includes(field.field_type)) {
    const options = isCascadeSelect
      ? cascadeOptions
      : (lookupValues
          ? lookupValues.filter((v) => v.is_active !== false).map((v) => ({ value: v.value, label: v.label }))
          : (field.options || []).map((o) => ({ value: o, label: o })));
    const waitingForParent = isCascadeSelect && cascadeReady && !cascadeParentValueId;
    return (
      <div>
        {label}
        <select
          className="input"
          required={field.required}
          value={value ?? ""}
          disabled={waitingForParent}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {waitingForParent
              ? `Önce "${cascadeParentField?.label || "üst alan"}" seçin`
              : (field.placeholder || "Seç...")}
          </option>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {field.help_text && <div className="text-[10px] text-[var(--text-dim)] mt-1">{field.help_text}</div>}
      </div>
    );
  }

  if (field.field_type === "multiselect") {
    const options = lookupValues
      ? lookupValues.filter((v) => v.is_active !== false).map((v) => ({ value: v.value, label: v.label }))
      : (field.options || []).map((o) => ({ value: o, label: o }));
    const selected = Array.isArray(value) ? value : [];
    function toggle(v) {
      onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
    }
    return (
      <div className="md:col-span-2">
        {label}
        <div className="flex flex-wrap gap-2">
          {options.map((o) => (
            <button type="button" key={o.value} onClick={() => toggle(o.value)}
                    className={`px-2 py-1 rounded text-xs border ${selected.includes(o.value) ? "bg-[var(--primary)] text-black border-[var(--primary)]" : "border-[var(--border)] text-[var(--text-dim)]"}`}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (field.field_type === "textarea") {
    return (
      <div className="md:col-span-2">
        {label}
        <textarea className="input" rows={2} placeholder={field.placeholder} required={field.required}
                  value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
      </div>
    );
  }

  const inputType = {
    number: "number", decimal: "number", date: "date", datetime: "datetime-local",
    time: "time", email: "email", url: "url", phone: "tel",
  }[field.field_type] || "text";
  const step = field.field_type === "decimal" ? "0.01" : undefined;

  return (
    <div>
      {label}
      <input
        className="input"
        type={inputType}
        step={step}
        placeholder={field.placeholder}
        required={field.required}
        value={value ?? ""}
        onChange={(e) => onChange(inputType === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)}
      />
      {field.help_text && <div className="text-[10px] text-[var(--text-dim)] mt-1">{field.help_text}</div>}
    </div>
  );
}

/**
 * IT-04 — file/image/multifile alan tiplerinin UI karşılığı. Bu widget
 * `values`/`onChange` sözleşmesini KULLANMAZ (dosyalar entity dokümanında
 * bir kolon değil, ayrı `uploads` koleksiyonunda (module, entity_id,
 * field_key) ile ilişkili kayıtlardır — bkz. backend/storage.py). Bu yüzden
 * entityId gerektirir: kayıt henüz oluşturulmamışsa (create akışı) bilgi
 * notu gösterir, kayıt oluştuktan sonra (edit akışı) gerçek yükleme/silme
 * yapar.
 */
function FileFieldWidget({ field, module, entityId }) {
  const [uploads, setUploads] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const isMulti = field.field_type === "multifile";

  const load = () => {
    if (!entityId) return;
    api.get("/uploads", { params: { module, entity_id: entityId, field_key: field.field_key } })
      .then((r) => setUploads(r.data));
  };

  useEffect(() => { load(); }, [module, entityId, field.field_key]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      // Tekil (file/image) alanda yeni yükleme eskisinin yerine geçer.
      if (!isMulti && uploads.length > 0) {
        await api.delete(`/uploads/${uploads[0].id}`);
      }
      const form = new FormData();
      form.append("file", file);
      form.append("module", module);
      form.append("entity_id", entityId);
      form.append("field_key", field.field_key);
      await api.post("/uploads", form, { headers: { "Content-Type": "multipart/form-data" } });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Yükleme başarısız");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleRemove(id) {
    await api.delete(`/uploads/${id}`);
    load();
  }

  const fileUrl = (u) => `${BACKEND_URL}${u.url}?token=${localStorage.getItem("token")}`;
  const label = (
    <label className="text-xs text-[var(--text-dim)] mb-1 block">{field.label}{field.required && " *"}</label>
  );

  if (!entityId) {
    return (
      <div className="md:col-span-2">
        {label}
        <div className="input text-xs text-[var(--text-dim)] flex items-center opacity-60">
          Bu alan sadece kayıt oluşturulduktan sonra (Düzenle ekranından) doldurulabilir.
        </div>
      </div>
    );
  }

  return (
    <div className="md:col-span-2">
      {label}
      {error && <div className="text-xs text-red-400 mb-1">{error}</div>}
      {uploads.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {uploads.map((u) => (
            <div key={u.id} className="flex items-center gap-2 p-1.5 pr-2 rounded border border-[var(--border)] text-xs bg-[var(--surface-2)]">
              {field.field_type !== "file" && u.content_type?.startsWith("image/") ? (
                <img src={fileUrl(u)} alt={u.filename} className="w-8 h-8 object-cover rounded" />
              ) : (
                <FileText size={16} className="text-[var(--text-dim)]" />
              )}
              <a href={fileUrl(u)} target="_blank" rel="noreferrer"
                 className="text-[var(--primary)] hover:underline max-w-[140px] truncate">{u.filename}</a>
              <button type="button" onClick={() => handleRemove(u.id)} className="text-red-400 hover:text-red-300">
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {(isMulti || uploads.length === 0) && (
        <label className="btn btn-ghost text-xs cursor-pointer inline-flex">
          <Upload size={13} /> {uploading ? "Yükleniyor…" : "Dosya Seç"}
          <input type="file" className="hidden" onChange={handleFile} disabled={uploading}
                 accept={field.field_type === "image" ? "image/*" : undefined} />
        </label>
      )}
      {field.help_text && <div className="text-[10px] text-[var(--text-dim)] mt-1">{field.help_text}</div>}
    </div>
  );
}
