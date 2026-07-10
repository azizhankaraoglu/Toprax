/**
 * TOPRAK BİLGİSİ MODÜLÜ (M06)
 *
 * Tüm parsellerin toprak analizlerinin merkezi yönetimi.
 * - Özet kartlar (toplam, ortalama pH/EC/OM)
 * - pH dağılımı pasta grafik
 * - Son analiz listesi
 */

import { useEffect, useState } from "react";
import api from "@/api";
import { FlaskConical, Beaker, Sprout, AlertCircle } from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { QuickAddPanel } from "@/components/QuickAdd";

const PH_COLORS = ["#ef4444", "#4ade80", "#fbbf24", "#60a5fa"];

export default function ToprakBilgisi() {
  const [summary, setSummary] = useState(null);
  const [samples, setSamples] = useState([]);
  const [parcels, setParcels] = useState([]);

  const load = () => {
    api.get("/soil-samples/summary").then((r) => setSummary(r.data));
    api.get("/soil-samples").then((r) => setSamples(r.data));
  };

  useEffect(() => {
    load();
    api.get("/parcels", { params: { limit: 500 } }).then((r) => setParcels(r.data));
  }, []);

  if (!summary) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1600px]" data-testid="toprak-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M06 · MODÜL</div>
        <h1 className="font-display text-4xl">Toprak Bilgisi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Tüm parsellerin toprak analiz verileri ve gübre önerileri</p>
      </header>

      {/* KPI KARTLARI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-5">
          <FlaskConical className="text-[var(--primary)] mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Toplam Numune</div>
          <div className="font-display text-3xl">{summary.total}</div>
        </div>
        <div className="card p-5">
          <Beaker className="text-blue-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Ortalama pH</div>
          <div className="font-display text-3xl">{summary.avg_ph}</div>
        </div>
        <div className="card p-5">
          <div className="text-amber-400 mb-2 text-2xl">⚡</div>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Ortalama EC</div>
          <div className="font-display text-3xl">{summary.avg_ec}</div>
          <div className="text-xs text-[var(--text-dim)]">dS/m</div>
        </div>
        <div className="card p-5">
          <Sprout className="text-emerald-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Org. Madde Ort.</div>
          <div className="font-display text-3xl">%{summary.avg_om}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* pH DAĞILIMI */}
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">pH Dağılımı</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={summary.ph_distribution} dataKey="count" nameKey="label" outerRadius={90} label={(e) => `${e.count}`}>
                {summary.ph_distribution.map((_, i) => <Cell key={i} fill={PH_COLORS[i]}/>)}
              </Pie>
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
              <Legend wrapperStyle={{ fontSize: 11 }}/>
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* UYARILAR */}
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 flex items-center gap-2">
            <AlertCircle size={18} className="text-amber-400"/> Dikkat Edilmesi Gerekenler
          </h3>
          <div className="space-y-3">
            {summary.ph_distribution.find(p => p.label.includes("Asitli"))?.count > 0 && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm">
                <div className="font-medium text-red-400">{summary.ph_distribution.find(p => p.label.includes("Asitli"))?.count} parsel asitli</div>
                <div className="text-xs text-[var(--text-dim)] mt-1">Kireç uygulaması önerilir. Pancarda asitli toprak verim kaybına yol açar.</div>
              </div>
            )}
            {summary.avg_om < 2 && (
              <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm">
                <div className="font-medium text-amber-400">Düşük organik madde</div>
                <div className="text-xs text-[var(--text-dim)] mt-1">Bölge genelinde organik madde ortalaması %{summary.avg_om}. Yeşil gübreleme/kompost önerilir.</div>
              </div>
            )}
            <div className="p-3 bg-[var(--primary)]/10 border border-[var(--primary)]/30 rounded-lg text-sm">
              <div className="font-medium text-[var(--primary)]">Akıllı Öneri</div>
              <div className="text-xs text-[var(--text-dim)] mt-1">Sentinel Hub uydu entegrasyonu aktive edildiğinde, NDVI sapması ile birleştirerek otomatik gübre dozu önerisi hesaplanabilir.</div>
            </div>
          </div>
        </div>
      </div>

      {/* SON ANALİZLER TABLOSU */}
      <QuickAddPanel
        title="Yeni Toprak Analizi"
        testId="soil-sample-add"
        fields={[
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "date", label: "Tarih", type: "date", required: true },
          { name: "lab_name", label: "Laboratuvar", required: true },
          { name: "ph", label: "pH", type: "number", step: "0.01", required: true },
          { name: "ec", label: "EC (dS/m)", type: "number", step: "0.01", required: true },
          { name: "organic_matter_pct", label: "Organik Madde (%)", type: "number", step: "0.01", required: true },
          { name: "n_ppm", label: "N (ppm)", type: "number", required: true },
          { name: "p_ppm", label: "P (ppm)", type: "number", required: true },
          { name: "k_ppm", label: "K (ppm)", type: "number", required: true },
          { name: "recommendation", label: "Öneri (boş bırakılırsa otomatik hesaplanır)", type: "textarea", span2: true },
        ]}
        onSubmit={async (v) => {
          await api.post("/soil-samples", {
            ...v,
            ph: Number(v.ph), ec: Number(v.ec), organic_matter_pct: Number(v.organic_matter_pct),
            n_ppm: Number(v.n_ppm), p_ppm: Number(v.p_ppm), k_ppm: Number(v.k_ppm),
            recommendation: v.recommendation || null,
          });
          load();
        }}
      />
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)]">
          <h3 className="font-display text-lg">Son Analizler</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-4">Tarih</th><th className="p-4">Lab</th>
              <th className="p-4">pH</th><th className="p-4">EC</th><th className="p-4">OM%</th>
              <th className="p-4">N (ppm)</th><th className="p-4">P (ppm)</th><th className="p-4">K (ppm)</th>
              <th className="p-4">Öneri</th>
            </tr>
          </thead>
          <tbody>
            {samples.slice(0, 30).map((s) => (
              <tr key={s.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 text-xs">{s.date}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{s.lab_name}</td>
                <td className="p-4"><span className={`badge ${s.ph < 6.5 ? "badge-d" : s.ph > 8 ? "badge-c" : "badge-a"}`}>{s.ph}</span></td>
                <td className="p-4">{s.ec}</td>
                <td className="p-4">{s.organic_matter_pct}</td>
                <td className="p-4">{s.n_ppm}</td>
                <td className="p-4">{s.p_ppm}</td>
                <td className="p-4">{s.k_ppm}</td>
                <td className="p-4 text-xs text-[var(--primary)] max-w-[200px]">{s.recommendation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
