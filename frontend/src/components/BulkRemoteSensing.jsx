/**
 * BulkRemoteSensing — elastik filtre + parsel seçimi + toplu Uzaktan Algılama.
 *
 * Parcels sayfasında ve Uzaktan Algılama menüsünde AYNI şekilde kullanılır:
 *   1. FilterPanel (Query Engine) ile parselleri HER alanıyla sorgula.
 *   2. Sonuç tablosundan çoklu/tekil seç (satır checkbox + tümünü seç).
 *   3. "Seçili Parsellerde Uydu Analizi Çalıştır" → /remote-sensing/manual-sync
 *      (NDVI istatistiği + opsiyonel uydu görüntüsü). Sonuç parsel.remote_sensing'e
 *      tarih damgasıyla yazılır (geçmiş veriler saklanır — bkz. RemoteSensingPanel).
 *
 * Not: gerçek EOSDA çağrısı için Ayarlar › Entegrasyonlar › EOSDA anahtarı +
 * mock_mode kapalı olmalı; aksi halde deterministik MOCK veri üretilir.
 */
import { useMemo, useState } from "react";
import api from "@/api";
import FilterPanel from "@/components/FilterPanel";
import { Satellite, RefreshCw, MapPin } from "lucide-react";

const risk = (lvl) => ({ yesil: "badge-a", sari: "badge-c", turuncu: "badge-c", kirmizi: "badge-d" }[lvl] || "badge-neutral");

export default function BulkRemoteSensing({ title = "Toplu Uzaktan Algılama" }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(() => new Set());
  const [indices, setIndices] = useState({ ndvi: true, ndre: false });
  const [withImage, setWithImage] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const onResults = (items, t) => { setRows(items || []); setTotal(t || 0); setSelected(new Set()); setResult(null); };

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(() => (allSelected ? new Set() : new Set(rows.map((r) => r.id))));

  const idxList = useMemo(() => Object.entries(indices).filter(([, v]) => v).map(([k]) => k), [indices]);

  async function run() {
    const ids = [...selected];
    if (!ids.length || idxList.length === 0) return;
    setBusy(true);
    setResult(null);
    try {
      const { data } = await api.post("/remote-sensing/manual-sync", {
        parcel_ids: ids,
        indices: idxList,
        task_types: withImage ? ["statistics", "download"] : ["statistics"],
      });
      setResult({ ok: true, ...data });
    } catch (err) {
      setResult({ ok: false, detail: err.response?.data?.detail || "Çalıştırılamadı (EOSDA yetkisi/entegrasyonu gerekli)." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="bulk-remote-sensing">
      <div className="flex items-center gap-2 mb-3">
        <Satellite size={18} className="text-[var(--primary)]" />
        <h3 className="font-display text-lg">{title}</h3>
      </div>
      <p className="text-xs text-[var(--text-dim)] mb-3">
        Parselleri her bilgisiyle sorgulayın (Gelişmiş Filtre), tekli/çoklu seçin ve uydu analizini manuel çalıştırın.
      </p>

      <FilterPanel module="parcels" onResults={onResults} pageSize={200} />

      {rows.length > 0 && (
        <div className="card overflow-hidden">
          {/* Kontrol çubuğu */}
          <div className="p-3 border-b border-[var(--border)] flex flex-wrap items-center gap-3">
            <div className="text-xs text-[var(--text-dim)]">{selected.size} / {rows.length} seçili (toplam {total})</div>
            <div className="flex items-center gap-3 text-xs">
              <label className="flex items-center gap-1"><input type="checkbox" checked={indices.ndvi} onChange={(e) => setIndices((i) => ({ ...i, ndvi: e.target.checked }))} /> NDVI</label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={indices.ndre} onChange={(e) => setIndices((i) => ({ ...i, ndre: e.target.checked }))} /> NDRE</label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={withImage} onChange={(e) => setWithImage(e.target.checked)} /> Uydu görüntüsü de indir</label>
            </div>
            <button onClick={run} disabled={busy || selected.size === 0 || idxList.length === 0}
              className="btn btn-primary text-xs ml-auto" data-testid="bulk-rs-run">
              <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Seçili {selected.size} Parselde Çalıştır
            </button>
          </div>

          {result && (
            <div className={`p-3 text-xs ${result.ok ? "text-[var(--primary)]" : "text-red-400"} border-b border-[var(--border)]`}>
              {result.ok
                ? `Analiz kuyruğa alındı: ${result.queued ?? 0} görev, ${result.processed ?? 0} işlendi. Sonuçlar parsel detayında (Uzaktan Algılama) görünür.`
                : result.detail}
            </div>
          )}

          <div className="max-h-[420px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)] sticky top-0 bg-[var(--surface)]">
                  <th className="p-3 w-8"><input type="checkbox" checked={allSelected} onChange={toggleAll} /></th>
                  <th className="p-3">Parsel</th><th className="p-3">Köy</th><th className="p-3">Alan</th>
                  <th className="p-3">NDVI</th><th className="p-3">Risk</th><th className="p-3">Son Analiz</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const rs = p.remote_sensing || {};
                  return (
                    <tr key={p.id} className={`border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer ${selected.has(p.id) ? "bg-[var(--surface-2)]" : ""}`}
                        onClick={() => toggle(p.id)}>
                      <td className="p-3" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} /></td>
                      <td className="p-3"><div className="flex items-center gap-1.5"><MapPin size={12} className="text-[var(--text-dim)]" />{p.name || p.parcel_code}</div></td>
                      <td className="p-3 text-[var(--text-dim)]">{p.village || p.mahalle || "—"}</td>
                      <td className="p-3">{p.area_dekar} da</td>
                      <td className="p-3">{rs.last_ndvi ?? p.ndvi_latest ?? "—"}</td>
                      <td className="p-3"><span className={`badge ${risk(p.risk_level)}`}>{p.risk_level || "—"}</span></td>
                      <td className="p-3 text-[var(--text-dim)] text-xs">{rs.last_analysis_date ? new Date(rs.last_analysis_date).toLocaleDateString("tr-TR") : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
