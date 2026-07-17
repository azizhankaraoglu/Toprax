import { useEffect, useMemo, useState } from "react";
import api from "@/api";
import { ArrowUp, ArrowDown, Pin, Eye, EyeOff, Download, Columns3, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * IT-11 — SmartDataGrid: Query Engine'e (IT-08) bağlı, yeniden kullanılabilir
 * veri tablosu. Kolon göster/gizle/sırala/sabitle, kolon bazlı hızlı filtre,
 * çoklu sıralama (başlığa tıkla → asc/desc/kapalı döngüsü, birden fazla
 * kolona tıklanırsa öncelik sırasıyla birikir), sayfalama, CSV dışa aktarma,
 * satır çoklu seçim.
 *
 * Kolon bazlı hızlı filtre ile FilterPanel.jsx (IT-09) FARKLI şeyler yapar:
 * FilterPanel çok koşullu/AND-OR sorgu kurucu, SmartDataGrid'in filtre
 * satırı tablo başlığının altında "excel tarzı" tek-alan hızlı daraltmadır.
 * İkisi aynı ekranda birlikte de kullanılabilir.
 *
 * Kullanım:
 *   <SmartDataGrid module="soil" columns={[
 *     { key: "date", label: "Tarih", type: "date" },
 *     { key: "ph", label: "pH", type: "number" },
 *     ...
 *   ]} defaultSort={[{ field: "date", dir: "desc" }]} />
 *
 * Not: CSV dışa aktarma mevcut filtre/sıralamayla eşleşen İLK 500 kaydı
 * indirir (Query Engine'in page_size tavanı) — arka planda tam veri seti
 * dışa aktarımı (streaming export) v1 kapsamı dışıdır.
 */
export default function SmartDataGrid({ module, columns, defaultSort = [], pageSizeOptions = [25, 50, 100], onRowClick, initialFilters = null, rowActions = null }) {
  const [colOrder, setColOrder] = useState(columns.map((c) => c.key));
  const [hidden, setHidden] = useState(new Set());
  const [pinned, setPinned] = useState(new Set());
  const [showColMenu, setShowColMenu] = useState(false);

  // KONU 3 (drill-down): dashboard kartından gelen ön-filtre (URL query param'ı
  // sayfa tarafından initialFilters olarak geçirir). Grid'in mevcut kolon-filtre
  // mekanizmasını (quickFilters) besler — yeni bir filtre yolu İCAT EDİLMEZ.
  const [quickFilters, setQuickFilters] = useState(initialFilters || {}); // key -> value
  const [sortState, setSortState] = useState(defaultSort);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(pageSizeOptions[0]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [exporting, setExporting] = useState(false);

  const colByKey = useMemo(() => Object.fromEntries(columns.map((c) => [c.key, c])), [columns]);

  const visibleOrderedKeys = useMemo(() => {
    const ordered = colOrder.filter((k) => !hidden.has(k));
    const pinnedKeys = ordered.filter((k) => pinned.has(k));
    const restKeys = ordered.filter((k) => !pinned.has(k));
    return [...pinnedKeys, ...restKeys];
  }, [colOrder, hidden, pinned]);

  function buildFilters() {
    return Object.entries(quickFilters)
      .filter(([, v]) => v !== "" && v != null)
      .map(([key, value]) => {
        const type = colByKey[key]?.type;
        return { field: key, operator: type === "number" || type === "date" ? "eq" : "contains", value: type === "number" ? Number(value) : value };
      });
  }

  function load() {
    setLoading(true);
    setError("");
    api.post(`/query/${module}`, {
      filters: buildFilters(),
      logic: "AND",
      sort: sortState.length ? sortState : undefined,
      page,
      page_size: pageSize,
      fields: visibleOrderedKeys,
    })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total); })
      .catch((err) => setError(err.response?.data?.detail || "Veri yüklenemedi."))
      .finally(() => setLoading(false));
  }

  useEffect(load, [module, JSON.stringify(quickFilters), JSON.stringify(sortState), page, pageSize, JSON.stringify(visibleOrderedKeys)]);
  useEffect(() => { setPage(1); }, [JSON.stringify(quickFilters), JSON.stringify(sortState)]);

  function toggleSort(key) {
    setSortState((prev) => {
      const idx = prev.findIndex((s) => s.field === key);
      if (idx === -1) return [...prev, { field: key, dir: "asc" }];
      if (prev[idx].dir === "asc") {
        const copy = [...prev]; copy[idx] = { field: key, dir: "desc" }; return copy;
      }
      return prev.filter((s) => s.field !== key);
    });
  }

  function sortBadge(key) {
    const idx = sortState.findIndex((s) => s.field === key);
    if (idx === -1) return null;
    const dir = sortState[idx].dir;
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-[var(--primary)]">
        {dir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
        {sortState.length > 1 && <span>{idx + 1}</span>}
      </span>
    );
  }

  function moveCol(key, dir) {
    setColOrder((prev) => {
      const idx = prev.indexOf(key);
      const swapWith = idx + dir;
      if (swapWith < 0 || swapWith >= prev.length) return prev;
      const copy = [...prev];
      [copy[idx], copy[swapWith]] = [copy[swapWith], copy[idx]];
      return copy;
    });
  }

  function toggleHidden(key) {
    setHidden((prev) => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });
  }

  function togglePinned(key) {
    setPinned((prev) => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });
  }

  function toggleRow(id) {
    setSelected((prev) => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  }

  function toggleAllOnPage() {
    setSelected((prev) => {
      const allSelected = items.every((it) => prev.has(it.id));
      const s = new Set(prev);
      items.forEach((it) => (allSelected ? s.delete(it.id) : s.add(it.id)));
      return s;
    });
  }

  function csvEscape(v) {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }

  async function exportCsv() {
    setExporting(true);
    try {
      const { data } = await api.post(`/query/${module}`, {
        filters: buildFilters(), logic: "AND",
        sort: sortState.length ? sortState : undefined,
        page: 1, page_size: 500, fields: visibleOrderedKeys,
      });
      const header = visibleOrderedKeys.map((k) => csvEscape(colByKey[k]?.label || k)).join(",");
      const rows = data.items.map((row) => visibleOrderedKeys.map((k) => csvEscape(row[k])).join(","));
      const csv = [header, ...rows].join("\n");
      const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${module}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="card overflow-hidden" data-testid={`smart-grid-${module}`}>
      <div className="p-3 border-b border-[var(--border)] flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs text-[var(--text-dim)]">
          {selected.size > 0 ? `${selected.size} satır seçili · ` : ""}{total} kayıt
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button onClick={() => setShowColMenu((s) => !s)} className="btn text-xs"><Columns3 size={13} /> Kolonlar</button>
            {showColMenu && (
              <div className="absolute right-0 top-full mt-1 z-20 card p-2 w-64 max-h-80 overflow-y-auto scrollbar">
                {colOrder.map((key, idx) => (
                  <div key={key} className="flex items-center gap-1 py-1 text-xs">
                    <button onClick={() => moveCol(key, -1)} disabled={idx === 0} className="text-[var(--text-dim)] disabled:opacity-20">↑</button>
                    <button onClick={() => moveCol(key, 1)} disabled={idx === colOrder.length - 1} className="text-[var(--text-dim)] disabled:opacity-20">↓</button>
                    <span className="flex-1 truncate">{colByKey[key]?.label}</span>
                    <button onClick={() => togglePinned(key)} className={pinned.has(key) ? "text-[var(--primary)]" : "text-[var(--text-dim)]"}><Pin size={12} /></button>
                    <button onClick={() => toggleHidden(key)} className="text-[var(--text-dim)]">
                      {hidden.has(key) ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={exportCsv} disabled={exporting} className="btn text-xs"><Download size={13} /> {exporting ? "…" : "CSV"}</button>
        </div>
      </div>

      {error && <div className="p-3 text-xs text-red-400">{error}</div>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3 w-8">
                <input type="checkbox" checked={items.length > 0 && items.every((it) => selected.has(it.id))} onChange={toggleAllOnPage} />
              </th>
              {visibleOrderedKeys.map((key) => (
                <th key={key} className="p-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort(key)}>
                  <span className="inline-flex items-center gap-1">{colByKey[key]?.label} {sortBadge(key)}</span>
                </th>
              ))}
              {rowActions && <th className="p-3 text-right whitespace-nowrap">İşlem</th>}
            </tr>
            <tr className="border-b border-[var(--border)]">
              <th className="p-1"></th>
              {visibleOrderedKeys.map((key) => (
                <th key={key} className="p-1">
                  <input
                    className="input text-xs py-1"
                    placeholder="filtrele…"
                    value={quickFilters[key] || ""}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setQuickFilters((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </th>
              ))}
              {rowActions && <th className="p-1"></th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={visibleOrderedKeys.length + 1 + (rowActions ? 1 : 0)} className="p-6 text-center text-[var(--text-dim)] text-sm">Yükleniyor…</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={visibleOrderedKeys.length + 1 + (rowActions ? 1 : 0)} className="p-6 text-center text-[var(--text-dim)] text-sm">Kayıt bulunamadı.</td></tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]"
                    onClick={() => onRowClick && onRowClick(row)} style={onRowClick ? { cursor: "pointer" } : undefined}>
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(row.id)} onChange={() => toggleRow(row.id)} />
                  </td>
                  {visibleOrderedKeys.map((key) => (
                    <td key={key} className="p-3 text-xs whitespace-nowrap">{String(row[key] ?? "")}</td>
                  ))}
                  {rowActions && (
                    <td className="p-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end">{rowActions(row, load)}</div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="p-3 border-t border-[var(--border)] flex items-center justify-between">
        <select className="input text-xs w-auto" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
          {pageSizeOptions.map((n) => <option key={n} value={n}>{n} / sayfa</option>)}
        </select>
        <div className="flex items-center gap-2 text-xs">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="btn text-xs disabled:opacity-30"><ChevronLeft size={13} /></button>
          <span>{page} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="btn text-xs disabled:opacity-30"><ChevronRight size={13} /></button>
        </div>
      </div>
    </div>
  );
}
