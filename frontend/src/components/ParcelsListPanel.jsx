/**
 * ParcelsListPanel — Parseller sayfasına elastik filtre + satır düzenle/sil +
 * çoklu seçim & toplu silme (#3). Harita-merkezli Parcels.jsx'e bir açılır
 * "Liste & Filtre" bölümü olarak eklenir (BulkRemoteSensing ile AYNI desen).
 *
 * - FilterPanel (Query Engine) ile parselleri HER alanıyla sorgula.
 * - Satır: çiftçi/köy/alan/ürün/risk + RowActions (hızlı düzenle / sil).
 * - Çoklu seç → "Seçili N Parseli Sil" (POST /parcels/bulk-delete — bağlı
 *   sözleşmesi olanlar atlanır ve raporlanır).
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import FilterPanel from "@/components/FilterPanel";
import RowActions from "@/components/RowActions";
import { List, Trash2, MapPin } from "lucide-react";

const risk = (lvl) => ({ yesil: "badge-a", sari: "badge-c", turuncu: "badge-c", kirmizi: "badge-d" }[lvl] || "badge-neutral");

const EDIT_FIELDS = [
  { name: "name", label: "Ad", span2: true },
  { name: "area_dekar", label: "Alan (dekar)", type: "number", step: "0.1" },
  { name: "current_crop", label: "Ürün" },
  { name: "risk_level", label: "Risk", type: "select", options: [
    { value: "yesil", label: "Düşük Risk" }, { value: "sari", label: "İzlemeye Değer" },
    { value: "turuncu", label: "Riskli" }, { value: "kirmizi", label: "Acil Müdahale" },
  ] },
];

export default function ParcelsListPanel() {
  const nav = useNavigate();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [sel, setSel] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const onResults = (items, t) => { setRows(items || []); setTotal(t || 0); setSel(new Set()); setMsg(null); };

  const allSel = rows.length > 0 && sel.size === rows.length;
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSel(() => (allSel ? new Set() : new Set(rows.map((r) => r.id))));

  async function bulkDelete() {
    const ids = [...sel];
    if (!ids.length) return;
    if (!window.confirm(`Seçili ${ids.length} parsel silinsin mi?\n(Arşivlenir — geri alınabilir; bağlı sözleşmesi olanlar atlanır.)`)) return;
    setBusy(true); setMsg(null);
    try {
      const { data } = await api.post("/parcels/bulk-delete", { parcel_ids: ids });
      const skippedIds = new Set((data.skipped || []).map((s) => s.id));
      setRows((prev) => prev.filter((r) => !(ids.includes(r.id) && !skippedIds.has(r.id))));
      setSel(new Set());
      let m = `${data.deleted_count} parsel silindi.`;
      if (data.skipped?.length) m += ` ${data.skipped.length} parsel atlandı (bağlı sözleşme).`;
      setMsg({ ok: true, text: m });
    } catch (err) {
      setMsg({ ok: false, text: err.response?.data?.detail || "Toplu silme başarısız." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="parcels-list-panel">
      <div className="flex items-center gap-2 mb-3">
        <List size={18} className="text-[var(--primary)]" />
        <h3 className="font-display text-lg">Parsel Listesi — Filtre & Toplu İşlem</h3>
      </div>
      <p className="text-xs text-[var(--text-dim)] mb-3">
        Parselleri her bilgisiyle sorgulayın (Gelişmiş Filtre), satırları düzenleyin/silin veya çoklu seçip toplu silin.
      </p>

      <FilterPanel module="parcels" onResults={onResults} pageSize={200} />

      {rows.length > 0 && (
        <div className="card overflow-hidden">
          <div className="p-3 border-b border-[var(--border)] flex flex-wrap items-center gap-3">
            <div className="text-xs text-[var(--text-dim)]">{sel.size} / {rows.length} seçili (toplam {total})</div>
            <button onClick={bulkDelete} disabled={busy || sel.size === 0}
              className="btn btn-ghost text-xs text-red-400 ml-auto" data-testid="parcels-bulk-delete">
              <Trash2 size={14} /> Seçili {sel.size} Parseli Sil
            </button>
          </div>

          {msg && (
            <div className={`p-3 text-xs ${msg.ok ? "text-[var(--primary)]" : "text-red-400"} border-b border-[var(--border)]`}>
              {msg.text}
            </div>
          )}

          <div className="max-h-[460px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)] sticky top-0 bg-[var(--surface)]">
                  <th className="p-3 w-8"><input type="checkbox" checked={allSel} onChange={toggleAll} /></th>
                  <th className="p-3">Parsel</th><th className="p-3">Köy</th><th className="p-3">Alan</th>
                  <th className="p-3">Ürün</th><th className="p-3">Risk</th><th className="p-3 text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className={`border-b border-[var(--border)] hover:bg-[var(--surface-2)] ${sel.has(p.id) ? "bg-[var(--surface-2)]" : ""}`}>
                    <td className="p-3"><input type="checkbox" checked={sel.has(p.id)} onChange={() => toggle(p.id)} /></td>
                    <td className="p-3 cursor-pointer" onClick={() => nav(`/parseller/${p.id}`)}>
                      <div className="flex items-center gap-1.5"><MapPin size={12} className="text-[var(--text-dim)]" />{p.name || p.parcel_code}</div>
                    </td>
                    <td className="p-3 text-[var(--text-dim)]">{p.village || p.mahalle || "—"}</td>
                    <td className="p-3">{p.area_dekar} da</td>
                    <td className="p-3 text-[var(--text-dim)]">{p.current_crop || "—"}</td>
                    <td className="p-3"><span className={`badge ${risk(p.risk_level)}`}>{p.risk_level || "—"}</span></td>
                    <td className="p-3">
                      <div className="flex justify-end">
                        <RowActions
                          entityLabel="parsel" fields={EDIT_FIELDS} values={p}
                          onSave={async (v) => {
                            const body = { ...v };
                            if (body.area_dekar) body.area_dekar = Number(body.area_dekar);
                            await api.put(`/parcels/${p.id}`, body);
                            setRows((prev) => prev.map((r) => (r.id === p.id ? { ...r, ...body } : r)));
                          }}
                          onDelete={async () => {
                            await api.delete(`/parcels/${p.id}`);
                            setRows((prev) => prev.filter((r) => r.id !== p.id));
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
