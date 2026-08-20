/**
 * VRA (Değişken Oranlı Uygulama) — OTURUM-DEVAM-19082026.md madde 9.
 *
 * Parsel bazlı zon haritası: seçilen parsellerin NDVI/toprak (N-P-K)
 * değeri eşit-aralık yöntemiyle Düşük/Orta/Yüksek 3 zona ayrılır, her
 * zona kullanıcı bir uygulama oranı (rate) girer, sonuç Shapefile veya
 * ISOXML (TASKDATA.XML) olarak dışa aktarılır. Zon = parsel (sub-field
 * çözünürlük YOK — backend/vra.py docstring'inde dürüstçe açıklanır).
 */
import { useState } from "react";
import api from "@/api";
import BulkParcelSelect from "@/components/BulkParcelSelect";

const SIGNAL_LABELS = {
  ndvi: "NDVI (Uydu)",
  soil_n: "Toprak Azot (N, ppm)",
  soil_p: "Toprak Fosfor (P, ppm)",
  soil_k: "Toprak Potasyum (K, ppm)",
};
const ZONE_LABELS = { dusuk: "Düşük", orta: "Orta", yuksek: "Yüksek", veri_yok: "Veri Yok" };
const zoneBadge = { dusuk: "badge-b", orta: "badge-c", yuksek: "badge-a", veri_yok: "badge-neutral" };

export default function Vra() {
  const [selectedIds, setSelectedIds] = useState([]);
  const [title, setTitle] = useState("");
  const [signal, setSignal] = useState("ndvi");
  const [unit, setUnit] = useState("kg/da");
  const [productName, setProductName] = useState("");
  const [rates, setRates] = useState({ dusuk: "", orta: "", yuksek: "" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [plan, setPlan] = useState(null);

  async function createPlan(e) {
    e.preventDefault();
    if (busy || !title.trim() || selectedIds.length === 0) return;
    const zone_rates = {
      dusuk: Number(rates.dusuk), orta: Number(rates.orta), yuksek: Number(rates.yuksek),
    };
    if (Object.values(zone_rates).some((v) => Number.isNaN(v))) {
      setMsg("Her zon için geçerli bir oran girilmeli.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const { data } = await api.post("/vra/plans", {
        title: title.trim(), parcel_ids: selectedIds, signal, zone_rates,
        unit, product_name: productName || undefined,
      });
      setPlan(data);
      setMsg(`Zon haritası oluşturuldu (${data.assignments.length} parsel, ${data.no_data_count} veri yok).`);
    } catch (err) {
      setMsg("Hata: " + (err.response?.data?.detail || "Oluşturulamadı"));
    } finally {
      setBusy(false);
    }
  }

  function downloadExport(format) {
    if (!plan) return;
    const url = `${api.defaults.baseURL}/vra/plans/${plan.id}/export/${format}`;
    const token = localStorage.getItem("token");
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => {
        if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || "İndirilemedi"); }
        return r.blob();
      })
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = format === "shapefile" ? `vra_${plan.id.slice(0, 8)}.zip` : `TASKDATA_${plan.id.slice(0, 8)}.xml`;
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch((err) => setMsg("Hata: " + err.message));
  }

  return (
    <div className="p-8 max-w-[1100px]" data-testid="vra-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">KARAR DESTEK</div>
      <h1 className="font-display text-4xl mb-1">VRA — Değişken Oranlı Uygulama</h1>
      <p className="text-sm text-[var(--text-dim)] mb-6">
        Seçili parsellerin NDVI ya da toprak analizi (N/P/K) değerine göre Düşük/Orta/Yüksek
        zonlara ayrılıp uygulama makinesine aktarılabilir bir zon haritası oluşturur. Zon
        çözünürlüğü <b>parsel</b> düzeyindedir — parsel içi (alt-alan) veri sistemde bulunmadığından
        uydurulmaz.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-4">
          <h3 className="text-sm font-medium mb-3">1) Parsel Seç</h3>
          <BulkParcelSelect onSelectionChange={setSelectedIds} testId="vra-parcel-select" />
        </div>

        <div className="card p-4">
          <h3 className="text-sm font-medium mb-3">2) Zon Haritası Parametreleri</h3>
          <form onSubmit={createPlan} className="space-y-3">
            <div>
              <label className="text-[11px] text-[var(--text-dim)]">Plan Başlığı</label>
              <input className="input" required value={title} onChange={(e) => setTitle(e.target.value)}
                     placeholder="ör. 2026 Azotlu Gübreleme Zonu" data-testid="vra-title" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Sinyal</label>
                <select className="input" value={signal} onChange={(e) => setSignal(e.target.value)} data-testid="vra-signal">
                  {Object.entries(SIGNAL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Birim</label>
                <input className="input" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="kg/da" />
              </div>
            </div>
            <div>
              <label className="text-[11px] text-[var(--text-dim)]">Ürün / Girdi Adı (opsiyonel)</label>
              <input className="input" value={productName} onChange={(e) => setProductName(e.target.value)}
                     placeholder="ör. Amonyum Nitrat %33" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              {["dusuk", "orta", "yuksek"].map((z) => (
                <div key={z}>
                  <label className="text-[11px] text-[var(--text-dim)]">{ZONE_LABELS[z]} Zon Oranı</label>
                  <input type="number" step="0.01" className="input" required value={rates[z]}
                         onChange={(e) => setRates((p) => ({ ...p, [z]: e.target.value }))}
                         data-testid={`vra-rate-${z}`} />
                </div>
              ))}
            </div>
            <button type="submit" disabled={busy || selectedIds.length === 0} className="btn btn-primary w-full text-sm" data-testid="vra-create">
              {selectedIds.length === 0 ? "Önce parsel seçin" : `Zon Haritası Oluştur (${selectedIds.length} parsel)`}
            </button>
            {msg && <div className="text-xs text-[var(--text-dim)]">{msg}</div>}
          </form>
        </div>
      </div>

      {plan && (
        <div className="card p-4 mt-4" data-testid="vra-plan-result">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-sm font-medium">{plan.title} — sonuç</h3>
            <div className="flex gap-2">
              <button onClick={() => downloadExport("shapefile")} className="btn btn-ghost text-xs" data-testid="vra-export-shp">
                Shapefile İndir (.zip)
              </button>
              <button onClick={() => downloadExport("isoxml")} className="btn btn-ghost text-xs" data-testid="vra-export-isoxml">
                ISOXML İndir (TASKDATA.XML)
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                  <th className="p-2">Parsel</th><th className="p-2">Sinyal Değeri</th>
                  <th className="p-2">Zon</th><th className="p-2">Oran</th>
                </tr>
              </thead>
              <tbody>
                {plan.assignments.map((a) => (
                  <tr key={a.parcel_id} className="border-b border-[var(--border)]">
                    <td className="p-2">{a.parcel_name || a.parcel_id}</td>
                    <td className="p-2">{a.signal_value ?? "—"}</td>
                    <td className="p-2"><span className={`badge ${zoneBadge[a.zone_class]}`}>{ZONE_LABELS[a.zone_class]}</span></td>
                    <td className="p-2">{a.rate != null ? `${a.rate} ${plan.unit}` : "—"}</td>
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
