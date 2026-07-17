import { useEffect, useState } from "react";
import api from "@/api";
import { Droplets, AlertTriangle, Waves } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";
import { QuickAddPanel } from "@/components/QuickAdd";
import RowActions from "@/components/RowActions";

const METHOD_COLORS = { damla: "#4ade80", yağmurlama: "#60a5fa", karık: "#fbbf24", diğer: "#97a8a0" };
const RISK_COLORS = { düşük: "text-[var(--primary)]", orta: "text-amber-400", yüksek: "text-red-400" };
const METHOD_OPTS = [{ value: "damla", label: "Damla" }, { value: "yağmurlama", label: "Yağmurlama" }, { value: "karık", label: "Karık" }];

export default function Sulama() {
  const [data, setData] = useState(null);
  const [parcels, setParcels] = useState([]);
  const [events, setEvents] = useState([]);

  const load = () => {
    api.get("/irrigation/summary").then((r) => setData(r.data));
    api.get("/irrigation/events", { params: { limit: 100 } }).then((r) => setEvents(r.data)).catch(() => setEvents([]));
  };
  const parcelName = (pid) => { const p = parcels.find((x) => x.id === pid); return p ? `${p.parcel_code} — ${p.name}` : pid; };
  useEffect(() => {
    load();
    api.get("/parcels", { params: { limit: 500 } }).then((r) => setParcels(r.data));
  }, []);
  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1600px]" data-testid="sulama-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M15 · MODÜL</div>
        <h1 className="font-display text-4xl">Sulama & Kaynak Yönetimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">2025 sezonu su kullanımı, kaynak takibi ve kuraklık riski</p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-5">
          <Droplets className="text-[var(--primary)] mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Toplam Su</div>
          <div className="font-display text-3xl">{(data.total_m3 / 1000).toFixed(1)}k</div>
          <div className="text-xs text-[var(--text-dim)]">m³</div>
        </div>
        <div className="card p-5">
          <Waves className="text-blue-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Sulama Olayı</div>
          <div className="font-display text-3xl">{data.events_count}</div>
        </div>
        <div className="card p-5">
          <div className="text-amber-400 mb-2 text-lg">⛲</div>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Aktif Kaynak</div>
          <div className="font-display text-3xl">{data.water_sources.length}</div>
        </div>
        <div className="card p-5">
          <AlertTriangle className="text-red-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Yüksek Risk Bölge</div>
          <div className="font-display text-3xl">{data.drought_risk.filter(d => d.level === "yüksek").length}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Bölge Bazlı Su Tüketimi</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.by_region}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
              <XAxis dataKey="name" stroke="#97a8a0" />
              <YAxis stroke="#97a8a0" />
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
              <Bar dataKey="water_m3" fill="#4ade80" radius={[6, 6, 0, 0]} name="m³"/>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Yönteme Göre Su Kullanımı</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={data.by_method} dataKey="m3" nameKey="method" outerRadius={90} label={(e) => `${e.method} ${(e.m3/1000).toFixed(1)}k`}>
                {data.by_method.map((m) => <Cell key={m.method} fill={METHOD_COLORS[m.method] || "#97a8a0"}/>)}
              </Pie>
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Kuraklık Risk Paneli</h3>
          <div className="space-y-2">
            {data.drought_risk.map((d) => (
              <div key={d.region} className="flex items-center justify-between p-3 bg-[var(--surface-2)] rounded-lg">
                <div>
                  <div className="font-medium text-sm">{d.region}</div>
                  <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{d.level} risk</div>
                </div>
                <div className={`font-display text-2xl ${RISK_COLORS[d.level]}`}>%{d.risk_pct}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Su Kaynakları (Doluluk)</h3>
          <div className="space-y-2 max-h-[400px] overflow-y-auto scrollbar">
            {data.water_sources.slice(0, 12).map((s) => (
              <div key={s.id} className="p-3 bg-[var(--surface-2)] rounded-lg">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-sm">{s.name}</div>
                  <div className="text-xs text-[var(--text-dim)] uppercase">{s.type}</div>
                </div>
                <div className="h-2 bg-[var(--bg)] rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${s.current_level_pct < 40 ? "bg-red-400" : s.current_level_pct < 70 ? "bg-amber-400" : "bg-[var(--primary)]"}`}
                       style={{ width: `${s.current_level_pct}%` }}/>
                </div>
                <div className="text-[11px] text-[var(--text-dim)] mt-1">Doluluk %{s.current_level_pct} · Kapasite {s.capacity_m3_per_day} m³/gün</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <QuickAddPanel
        title="Yeni Sulama Kaydı"
        testId="irrigation-add"
        fields={[
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "date", label: "Tarih", type: "date", required: true },
          { name: "method", label: "Yöntem", type: "select", required: true,
            options: [{ value: "damla", label: "Damla" }, { value: "yağmurlama", label: "Yağmurlama" }, { value: "karık", label: "Karık" }] },
          { name: "water_m3", label: "Su Miktarı (m³)", type: "number", step: "0.1", required: true },
          { name: "moisture_before", label: "Nem (öncesi, %)", type: "number" },
          { name: "moisture_after", label: "Nem (sonrası, %)", type: "number" },
        ]}
        onSubmit={async (v) => {
          await api.post("/irrigation/events", {
            ...v,
            water_m3: Number(v.water_m3),
            moisture_before: v.moisture_before ? Number(v.moisture_before) : null,
            moisture_after: v.moisture_after ? Number(v.moisture_after) : null,
          });
          load();
        }}
      />

      <div className="card overflow-hidden mt-4">
        <div className="p-4 border-b border-[var(--border)]"><h3 className="font-display text-lg">Son Sulama Kayıtları</h3></div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Tarih</th><th className="p-4">Parsel</th><th className="p-4">Yöntem</th><th className="p-4">Su (m³)</th><th className="p-4">Nem Ö/S</th><th className="p-4 text-right">İşlem</th>
          </tr></thead>
          <tbody>
            {events.length === 0 && <tr><td colSpan={6} className="p-4 text-[var(--text-dim)] text-xs">Kayıt yok.</td></tr>}
            {events.map((e) => (
              <tr key={e.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 text-[var(--text-dim)]">{e.date}</td>
                <td className="p-4">{parcelName(e.parcel_id)}</td>
                <td className="p-4">{e.method}</td>
                <td className="p-4">{e.water_m3} m³</td>
                <td className="p-4 text-[var(--text-dim)]">{e.moisture_before ?? "-"} / {e.moisture_after ?? "-"}</td>
                <td className="p-4">
                  <div className="flex justify-end">
                    <RowActions
                      entityLabel="sulama kaydı"
                      values={e}
                      fields={[
                        { name: "date", label: "Tarih", type: "date" },
                        { name: "method", label: "Yöntem", type: "select", options: METHOD_OPTS },
                        { name: "water_m3", label: "Su (m³)", type: "number", step: "0.1" },
                        { name: "moisture_before", label: "Nem öncesi (%)", type: "number" },
                        { name: "moisture_after", label: "Nem sonrası (%)", type: "number" },
                      ]}
                      onSave={async (v) => {
                        await api.put(`/irrigation/events/${e.id}`, {
                          date: v.date || null,
                          method: v.method || null,
                          water_m3: v.water_m3 === "" ? null : Number(v.water_m3),
                          moisture_before: v.moisture_before === "" ? null : Number(v.moisture_before),
                          moisture_after: v.moisture_after === "" ? null : Number(v.moisture_after),
                        });
                        load();
                      }}
                      onDelete={async () => { await api.delete(`/irrigation/events/${e.id}`); load(); }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
