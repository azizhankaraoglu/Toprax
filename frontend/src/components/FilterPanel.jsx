import { useEffect, useState } from "react";
import api from "@/api";
import { Filter, Plus, X, Search, Star, Save, Trash2, ChevronDown, ChevronUp } from "lucide-react";

/**
 * IT-09 — Genel Filtre Paneli (Query Engine — IT-08 — üzerine ince bir UI).
 * Herhangi bir liste ekranına eklenebilir; mevcut basit arama/filtreleri
 * DEĞİŞTİRMEZ, yanına "Gelişmiş Filtre" olarak eklenir.
 *
 * Kullanım:
 *   <FilterPanel module="farmers" onResults={(items, total) => setFarmers(items)} />
 *
 * Modülün filtrelenebilir alan listesini GET /query/{module}/filterable-fields'tan
 * çeker (CORE + field_definitions'ta filterable=True birleşimi, bkz. query_engine.py),
 * koşulları POST /query/{module}'e gönderir. Kayıtlı Sorgular/Favoriler için
 * /saved-queries uçlarını kullanır.
 */
const TEXT_OPS = [
  { v: "eq", l: "eşittir" }, { v: "ne", l: "eşit değildir" },
  { v: "contains", l: "içerir" }, { v: "in", l: "şunlardan biri (virgülle ayır)" },
  { v: "is_null", l: "boş" }, { v: "is_not_null", l: "dolu" },
];
const NUMERIC_OPS = [
  { v: "eq", l: "eşittir" }, { v: "ne", l: "eşit değildir" },
  { v: "gt", l: ">" }, { v: "gte", l: "≥" }, { v: "lt", l: "<" }, { v: "lte", l: "≤" },
  { v: "between", l: "arasında" },
  { v: "is_null", l: "boş" }, { v: "is_not_null", l: "dolu" },
];
const NO_VALUE_OPS = new Set(["is_null", "is_not_null"]);
const NUMERIC_TYPES = new Set(["number", "decimal"]);

function opsFor(type) {
  return NUMERIC_TYPES.has(type) || type === "date" ? NUMERIC_OPS : TEXT_OPS;
}

function emptyRow(fields) {
  const first = fields[0];
  return { field: first?.key || "", operator: "eq", value: "" };
}

export default function FilterPanel({ module, onResults, pageSize = 50 }) {
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState([]);
  const [rows, setRows] = useState([]);
  const [logic, setLogic] = useState("AND");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [savedQueries, setSavedQueries] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [shareOnSave, setShareOnSave] = useState(false);

  useEffect(() => {
    api.get(`/query/${module}/filterable-fields`).then((r) => {
      setFields(r.data.fields);
      setRows([emptyRow(r.data.fields)]);
    });
    loadSavedQueries();
  }, [module]);

  function loadSavedQueries() {
    api.get("/saved-queries", { params: { module } }).then((r) => setSavedQueries(r.data));
  }

  const set = (idx, patch) => setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, emptyRow(fields)]);
  const removeRow = (idx) => setRows((rs) => rs.filter((_, i) => i !== idx));

  function fieldType(key) {
    return fields.find((f) => f.key === key)?.type || "text";
  }

  function buildFilters() {
    return rows
      .filter((r) => r.field && (NO_VALUE_OPS.has(r.operator) || r.value !== ""))
      .map((r) => {
        let value = r.value;
        if (r.operator === "in") value = String(value).split(",").map((v) => v.trim()).filter(Boolean);
        else if (r.operator === "between") value = [r.valueMin, r.valueMax].map(Number);
        else if (NUMERIC_TYPES.has(fieldType(r.field)) && !NO_VALUE_OPS.has(r.operator)) value = Number(value);
        return { field: r.field, operator: r.operator, value: NO_VALUE_OPS.has(r.operator) ? null : value };
      });
  }

  async function runSearch() {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post(`/query/${module}`, {
        filters: buildFilters(), logic, page: 1, page_size: pageSize,
      });
      onResults(data.items, data.total);
    } catch (err) {
      setError(err.response?.data?.detail || "Sorgu çalıştırılamadı.");
    } finally {
      setLoading(false);
    }
  }

  function applySaved(sq) {
    setLogic(sq.logic || "AND");
    setRows(
      (sq.filters || []).map((f) => {
        if (f.operator === "between") return { field: f.field, operator: f.operator, valueMin: f.value?.[0], valueMax: f.value?.[1] };
        if (f.operator === "in") return { field: f.field, operator: f.operator, value: (f.value || []).join(", ") };
        return { field: f.field, operator: f.operator, value: f.value ?? "" };
      })
    );
    setOpen(true);
    setTimeout(runSearch, 0);
  }

  async function saveCurrent() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      await api.post("/saved-queries", {
        module, name: saveName.trim(), filters: buildFilters(), logic, is_shared: shareOnSave,
      });
      setSaveName(""); setShowSaveForm(false); setShareOnSave(false);
      loadSavedQueries();
    } catch (err) {
      setError(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleFavorite(sq) {
    await api.post(`/saved-queries/${sq.id}/favorite`);
    loadSavedQueries();
  }

  async function removeSaved(sq) {
    if (!window.confirm(`"${sq.name}" silinsin mi?`)) return;
    await api.delete(`/saved-queries/${sq.id}`);
    loadSavedQueries();
  }

  return (
    <div className="card p-4 mb-4" data-testid={`filter-panel-${module}`}>
      <button className="flex items-center gap-2 text-sm font-medium" onClick={() => setOpen((o) => !o)}>
        <Filter size={15} /> Gelişmiş Filtre
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          {savedQueries.length > 0 && (
            <div className="flex flex-wrap gap-2 pb-2 border-b border-[var(--border)]">
              {savedQueries.map((sq) => (
                <div key={sq.id} className="flex items-center gap-1 badge badge-neutral">
                  <button onClick={() => applySaved(sq)} className="hover:underline">{sq.name}</button>
                  {sq.is_shared && <span className="text-[10px] opacity-60">(paylaşılan)</span>}
                  <button onClick={() => toggleFavorite(sq)} title="Favori">
                    <Star size={11} fill={sq.is_favorite ? "currentColor" : "none"} />
                  </button>
                  {sq.is_owner && (
                    <button onClick={() => removeSaved(sq)} title="Sil"><Trash2 size={11} /></button>
                  )}
                </div>
              ))}
            </div>
          )}

          {rows.map((row, idx) => (
            <div key={idx} className="flex items-center gap-2">
              {idx > 0 && (
                <select className="input w-20 text-xs" value={logic} onChange={(e) => setLogic(e.target.value)}>
                  <option value="AND">VE</option>
                  <option value="OR">VEYA</option>
                </select>
              )}
              {idx === 0 && <span className="w-20 text-xs text-[var(--text-dim)]">Koşul</span>}
              <select className="input flex-1" value={row.field} onChange={(e) => set(idx, { field: e.target.value, operator: "eq", value: "" })}>
                {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </select>
              <select className="input w-44" value={row.operator} onChange={(e) => set(idx, { operator: e.target.value, value: "" })}>
                {opsFor(fieldType(row.field)).map((op) => <option key={op.v} value={op.v}>{op.l}</option>)}
              </select>
              {row.operator === "between" ? (
                <>
                  <input className="input w-24" type="number" placeholder="min" value={row.valueMin ?? ""} onChange={(e) => set(idx, { valueMin: e.target.value })} />
                  <input className="input w-24" type="number" placeholder="max" value={row.valueMax ?? ""} onChange={(e) => set(idx, { valueMax: e.target.value })} />
                </>
              ) : !NO_VALUE_OPS.has(row.operator) ? (
                <input
                  className="input flex-1"
                  type={NUMERIC_TYPES.has(fieldType(row.field)) ? "number" : fieldType(row.field) === "date" ? "date" : "text"}
                  value={row.value ?? ""}
                  onChange={(e) => set(idx, { value: e.target.value })}
                />
              ) : (
                <div className="flex-1" />
              )}
              <button onClick={() => removeRow(idx)} disabled={rows.length === 1} className="text-[var(--text-dim)] hover:text-red-400 disabled:opacity-20">
                <X size={14} />
              </button>
            </div>
          ))}

          {error && <div className="text-xs text-red-400">{error}</div>}

          <div className="flex items-center gap-2 pt-1">
            <button onClick={addRow} className="btn text-xs"><Plus size={13} /> Koşul Ekle</button>
            <button onClick={runSearch} disabled={loading} className="btn btn-primary text-xs">
              <Search size={13} /> {loading ? "Aranıyor…" : "Ara"}
            </button>
            <button onClick={() => setShowSaveForm((s) => !s)} className="btn text-xs"><Save size={13} /> Sorguyu Kaydet</button>
          </div>

          {showSaveForm && (
            <div className="flex items-center gap-2 pt-1">
              <input className="input flex-1" placeholder="Sorgu adı" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
              <label className="flex items-center gap-1 text-xs whitespace-nowrap">
                <input type="checkbox" checked={shareOnSave} onChange={(e) => setShareOnSave(e.target.checked)} /> Paylaş
              </label>
              <button onClick={saveCurrent} disabled={saving || !saveName.trim()} className="btn btn-primary text-xs">Kaydet</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
