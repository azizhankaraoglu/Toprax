/**
 * SON HAL — Toplu işlem için parsel filtreleme + çoklu seçim (ortak bileşen).
 *
 * FilterPanel (Query Engine, module="parcels") ile parselleri bulur,
 * checkbox'lı tabloda çoklu seçtirir. Ekim Kaydı (toplu ekim), Sulama
 * (toplu sulama) ve Operasyon (toplu görev) AYNI bileşeni kullanır —
 * her sayfa sadece kendi "ortak alanlar" formunu + submit'ini ekler.
 *
 * Kullanım:
 *   <BulkParcelSelect onSelectionChange={(ids) => setSel(ids)} testId="..." />
 *   onSelectionChange her seçim değişiminde string[] (parsel id) alır.
 */
import { useState } from "react";
import FilterPanel from "@/components/FilterPanel";

export default function BulkParcelSelect({ onSelectionChange, testId = "bulk-parcel" }) {
  const [rows, setRows] = useState([]);
  const [sel, setSel] = useState(new Set());

  function update(next) {
    setSel(next);
    onSelectionChange([...next]);
  }
  const toggle = (id) => update(new Set(sel.has(id) ? [...sel].filter((x) => x !== id) : [...sel, id]));
  const toggleAll = () => update(sel.size === rows.length ? new Set() : new Set(rows.map((r) => r.id)));

  return (
    <div data-testid={testId}>
      <FilterPanel module="parcels" pageSize={200}
                   onResults={(items) => { setRows(items || []); update(new Set()); }} />

      {rows.length > 0 && (
        <>
          <div className="max-h-[260px] overflow-y-auto scrollbar border border-[var(--border)] rounded-lg mt-3">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5 w-8">
                    <input type="checkbox" checked={sel.size === rows.length && rows.length > 0}
                           onChange={toggleAll} data-testid={`${testId}-select-all`} />
                  </th>
                  <th className="p-2.5">Parsel</th><th className="p-2.5">Köy/Mahalle</th>
                  <th className="p-2.5">Alan (da)</th><th className="p-2.5">Ekim Durumu</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}
                      className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer"
                      onClick={() => toggle(r.id)}>
                    <td className="p-2.5" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={sel.has(r.id)} onChange={() => toggle(r.id)} />
                    </td>
                    <td className="p-2.5">{r.name}</td>
                    <td className="p-2.5 text-[var(--text-dim)]">{r.mahalle || r.village || "—"}</td>
                    <td className="p-2.5">{r.area_dekar}</td>
                    <td className="p-2.5 text-[var(--text-dim)]">{r.ekim_durumu || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-xs text-[var(--text-dim)] mt-2">{sel.size} parsel seçili ({rows.length} sonuç)</div>
        </>
      )}
    </div>
  );
}
