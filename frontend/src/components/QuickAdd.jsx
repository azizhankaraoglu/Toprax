import { useState } from "react";

/**
 * Ortak "hızlı ekle" form paneli. Sadece görüntüleme olan sayfalara
 * (Sözleşme, Ekim, Operasyon, Lojistik, Kantar, E-belge, IoT, Drone vb.)
 * tutarlı ve az kod tekrarıyla veri giriş formu eklemek için kullanılır.
 *
 * fields: [{ name, label, type: "text"|"number"|"date"|"datetime-local"|"select"|"textarea",
 *            required, default, options: [{value,label}], span2 }]
 * onSubmit: async (values) => {...}  — başarısızsa throw eder (axios hatası yeterli)
 */
export function QuickAddPanel({ title, fields, onSubmit, submitLabel = "Ekle", testId }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.default ?? ""]))
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function setField(name, value) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(values);
      setValues(Object.fromEntries(fields.map((f) => [f.name, f.default ?? ""])));
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
            {f.type === "select" ? (
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
      <button type="submit" disabled={submitting} className="btn btn-primary">
        {submitting ? "Kaydediliyor…" : submitLabel}
      </button>
    </form>
  );
}
