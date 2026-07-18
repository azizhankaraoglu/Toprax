import { useState } from "react";
import DynamicFieldsSection from "@/components/DynamicFieldsSection";
import ParcelPicker from "@/components/ParcelPicker";

/**
 * Ortak "hızlı ekle" form paneli. Sadece görüntüleme olan sayfalara
 * (Sözleşme, Ekim, Operasyon, Lojistik, Kantar, E-belge, IoT, Drone vb.)
 * tutarlı ve az kod tekrarıyla veri giriş formu eklemek için kullanılır.
 *
 * fields: [{ name, label, type: "text"|"number"|"date"|"datetime-local"|"select"|"textarea"|"parcel",
 *            required, default, options: [{value,label}], span2 }]
 * onSubmit: async (values) => {...}  — başarısızsa throw eder (axios hatası yeterli)
 * extraModule: opsiyonel — verilirse, statik `fields`in altına o modülün
 *   (field_definitions module="...") dinamik alanları eklenir (bkz.
 *   DynamicFieldsSection). Doldurulan değerler onSubmit'e statik `values`
 *   ile BİRLEŞTİRİLMİŞ tek bir düz obje olarak geçirilir — çağıran taraf
 *   ekstra bir birleştirme yapmaz, olduğu gibi POST body'sine spread eder.
 *
 * SON HAL — yeni alan tipi "parcel": select yerine aranabilir ParcelPicker
 * (il/ilçe/mahalle/ada/parsel no/ad ile arar) render eder; values[name]'e
 * seçilen parselin id'si yazılır. 500 satırlık select'lerin yerini alır.
 */
export function QuickAddPanel({ title, fields, onSubmit, submitLabel = "Ekle", testId, extraModule }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.default ?? ""]))
  );
  const [extraValues, setExtraValues] = useState({});
  const [parcelObjs, setParcelObjs] = useState({});          // "parcel" tipli alanların seçili objesi
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function setField(name, value) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    // "parcel" tipi native input değil — required kontrolü elle yapılır.
    const missing = fields.find((f) => f.type === "parcel" && f.required && !values[f.name]);
    if (missing) { setError(`"${missing.label}" seçilmedi — arama kutusundan bir parsel seçin.`); return; }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(extraModule ? { ...values, ...extraValues } : values);
      setValues(Object.fromEntries(fields.map((f) => [f.name, f.default ?? ""])));
      setExtraValues({});
      setParcelObjs({});
      setOpen(false);
    } catch (err) {
      setError(err.response?.data?.detail || "Kaydedilemedi, alanları kontrol edin.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-primary mb-4" data-testid={testId ? `${testId}-open` : undefined}>
        + {title}
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card p-4 mb-4 space-y-3" data-testid={testId}>
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg">{title}</h3>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-[var(--text-dim)] hover:text-white">
          Kapat
        </button>
      </div>
      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded">{error}</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {fields.map((f) => (
          <div key={f.name} className={f.span2 ? "md:col-span-2" : ""}>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">{f.label}{f.required && " *"}</label>
            {f.type === "parcel" ? (
              <ParcelPicker
                value={parcelObjs[f.name] || null}
                onSelect={(p) => {
                  setParcelObjs((prev) => ({ ...prev, [f.name]: p }));
                  setField(f.name, p ? p.id : "");
                }}
                testId={`${testId || "quickadd"}-${f.name}`}
              />
            ) : f.type === "select" ? (
              <select
                className="input"
                required={f.required}
                value={values[f.name] ?? ""}
                onChange={(e) => setField(f.name, e.target.value)}
              >
                <option value="">Seç...</option>
                {(f.options || []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                className="input"
                rows={f.rows || 3}
                required={f.required}
                value={values[f.name] ?? ""}
                onChange={(e) => setField(f.name, e.target.value)}
              />
            ) : (
              <input
                className="input"
                type={f.type || "text"}
                step={f.step}
                required={f.required}
                value={values[f.name] ?? ""}
                onChange={(e) => setField(f.name, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
      {extraModule && (
        <DynamicFieldsSection
          module={extraModule}
          values={extraValues}
          onChange={(key, val) => setExtraValues((e) => ({ ...e, [key]: val }))}
        />
      )}
      <button type="submit" disabled={submitting} className="btn btn-primary">
        {submitting ? "Kaydediliyor…" : submitLabel}
      </button>
    </form>
  );
}
