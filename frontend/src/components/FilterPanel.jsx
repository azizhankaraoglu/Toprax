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

export default function FilterPanel({ module, onResults, pageSize = 50, onFiltersChange }) {
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
  // SON HAL #2 — alanın lookup_group_id (dinamik alan) VEYA lookup_key (kod
  // seviyesi CORE alan, bkz. query_engine.py) taşıması durumunda değer
  // kutusu yerine DB'deki gerçek lookup değerlerinden bir seçim listesi
  // gösterilir. group key -> id eşlemesi (lookup_key'li alanlar için) ve
  // group id -> değerler listesi ayrı ayrı önbelleklenir (her alan için
  // tekrar tekrar aynı istek atılmasın diye).
  const [lookupGroupsByKey, setLookupGroupsByKey] = useState(null);
  const [lookupValuesByGroupId, setLookupValuesByGroupId] = useState({});
  // 2026-08-20 — ÖNCEDEN seçenek listesi `/lookups/groups/{id}/values`
  // (TAM katalog, ör. 81 il/973 ilçe) idi; parselde/çiftçide karşılığı
  // olmayan değerler de filtrede görünüyordu. Artık AYRICA `/query/
  // {module}/distinct?field=` (bkz. query_engine.py) ile o modülde
  // GERÇEKTEN kullanılan değerler çekilip, aşağıdaki `lookupOptions`
  // hesabında TAM katalog bu kümeye göre süzülür — hem doğru Türkçe
  // etiket (lookup_values.label) hem sadece-DB'deki-veri garantisi.
  const [distinctValuesByField, setDistinctValuesByField] = useState({});

  useEffect(() => {
    api.get(`/query/${module}/filterable-fields`).then((r) => {
      setFields(r.data.fields);
      setRows([emptyRow(r.data.fields)]);
    });
    loadSavedQueries();
  }, [module]);

  // Grup key->id eşlemesi bir kez çekilir (herhangi bir alan lookup_key
  // taşıyorsa gerekir).
  useEffect(() => {
    if (fields.some((f) => f.lookup_key) && !lookupGroupsByKey) {
      api.get("/lookups/groups").then((r) => {
        setLookupGroupsByKey(Object.fromEntries(r.data.map((g) => [g.key, g.id])));
      }).catch(() => setLookupGroupsByKey({}));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields]);

  function lookupGroupIdFor(field) {
    if (!field) return null;
    if (field.lookup_group_id) return field.lookup_group_id;
    if (field.lookup_key) return lookupGroupsByKey?.[field.lookup_key] || null;
    return null;
  }

  function ensureLookupValuesLoaded(groupId) {
    if (!groupId || lookupValuesByGroupId[groupId]) return;
    api.get(`/lookups/groups/${groupId}/values`).then((r) => {
      setLookupValuesByGroupId((prev) => ({ ...prev, [groupId]: r.data }));
    }).catch(() => setLookupValuesByGroupId((prev) => ({ ...prev, [groupId]: [] })));
  }

  function ensureDistinctValuesLoaded(fieldKey) {
    if (!fieldKey || distinctValuesByField[fieldKey]) return;
    api.get(`/query/${module}/distinct`, { params: { field: fieldKey } }).then((r) => {
      setDistinctValuesByField((prev) => ({ ...prev, [fieldKey]: new Set(r.data.values || []) }));
    }).catch(() => setDistinctValuesByField((prev) => ({ ...prev, [fieldKey]: new Set() })));
  }

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
      // SmartDataGrid entegrasyonu (ör. Toprak.jsx) — grid kendi sayfalama/
      // sıralamasıyla sunucudan çekmeye devam eder, bu panel sadece KOŞULLARI
      // dışarı verir (onFiltersChange varsa); onResults hâlâ çağrılır (panelin
      // kendi başına, bir liste state'ine bağlı kullanımı BOZULMAZ).
      if (onFiltersChange) onFiltersChange(buildFilters(), logic);
      const { data } = await api.post(`/query/${module}`, {
        filters: buildFilters(), logic, page: 1, page_size: pageSize,
      });
      onResults?.(data.items, data.total);
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

  // Denetim UI düzeltmesi (2026-07-24) — kapalıyken AiAssistantBox'ın
  // (bkz. o bileşen) "btn btn-ghost" pill'iyle AYNI kompakt görünüm:
  // önceden HER ZAMAN tam genişlikte, kenarlıklı bir "card" içinde
  // render ediliyordu, bu da arama kutusu + AI Asistanı ile aynı satıra
  // sığmasını engelliyordu. Açıkken davranış/İÇERİK DEĞİŞMEDİ, sadece
  // dış sarmalayıcı — data-testid HER İKİ durumda da aynı kalır.
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-ghost" data-testid={`filter-panel-${module}`}>
        <Filter size={15} /> Gelişmiş Filtre <ChevronDown size={14} />
      </button>
    );
  }

  return (
    <div className="card p-4 mb-4 w-full" data-testid={`filter-panel-${module}`}>
      <button className="flex items-center gap-2 text-sm font-medium" onClick={() => setOpen((o) => !o)}>
        <Filter size={15} /> Gelişmiş Filtre
        <ChevronUp size={14} />
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

          {rows.map((row, idx) => {
            const fieldDef = fields.find((f) => f.key === row.field);
            const groupId = lookupGroupIdFor(fieldDef);
            if (groupId) { ensureLookupValuesLoaded(groupId); ensureDistinctValuesLoaded(row.field); }
            const inUseValues = groupId ? distinctValuesByField[row.field] : null;
            // Tam katalog (doğru Türkçe etiketler için) × bu modülde
            // GERÇEKTEN kullanılan değerler (DB-only kural) — kesişimi al.
            const lookupOptions = groupId && inUseValues
              ? (lookupValuesByGroupId[groupId] || []).filter((o) => o.is_active !== false && inUseValues.has(o.value))
              : null;
            return (
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
              {/* SON HAL — operatör kutusu küçültüldü (metin boyu 12px, dar
                  genişlik); önceden .input sınıfının tam boyu (14px/geniş
                  padding) kullanılıyordu, satır gereksiz büyük görünüyordu. */}
              <select
                className="input w-32 !py-1.5 !text-xs shrink-0"
                value={row.operator}
                onChange={(e) => set(idx, { operator: e.target.value, value: "" })}
              >
                {opsFor(fieldType(row.field)).map((op) => <option key={op.v} value={op.v}>{op.l}</option>)}
              </select>
              {row.operator === "between" ? (
                <>
                  <input className="input w-24" type="number" placeholder="min" value={row.valueMin ?? ""} onChange={(e) => set(idx, { valueMin: e.target.value })} />
                  <input className="input w-24" type="number" placeholder="max" value={row.valueMax ?? ""} onChange={(e) => set(idx, { valueMax: e.target.value })} />
                </>
              ) : !NO_VALUE_OPS.has(row.operator) ? (
                lookupOptions ? (
                  // SON HAL #2 (2026-08-20 güncellemesi) — bu alan bir lookup
                  // grubuna bağlı: serbest metin yerine DB'de bu modülde
                  // GERÇEKTEN kullanılan (ve doğru Türkçe etiketli) değerlerden
                  // seçilir — tam lookup kataloğu DEĞİL (bkz. yukarıdaki kesişim).
                  <select className="input flex-1" value={row.value ?? ""} onChange={(e) => set(idx, { value: e.target.value })}>
                    <option value="">— değer seçin —</option>
                    {lookupOptions.map((o) => (
                      <option key={o.id} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="input flex-1"
                    type={NUMERIC_TYPES.has(fieldType(row.field)) ? "number" : fieldType(row.field) === "date" ? "date" : "text"}
                    value={row.value ?? ""}
                    onChange={(e) => set(idx, { value: e.target.value })}
                  />
                )
              ) : (
                <div className="flex-1" />
              )}
              <button onClick={() => removeRow(idx)} disabled={rows.length === 1} className="text-[var(--text-dim)] hover:text-red-400 disabled:opacity-20">
                <X size={14} />
              </button>
            </div>
          );})}

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
