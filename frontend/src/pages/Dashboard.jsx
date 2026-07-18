import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import {
  Users, Map as MapIcon, FileText, TrendingUp, Wheat, Target,
  ArrowUpRight, AlertTriangle, Satellite, Radio, Plane
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid, Legend
} from "recharts";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

function timeAgo(iso) {
  if (!iso) return "—";
  const diffMin = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (diffMin < 60) return `${diffMin} dk önce`;
  if (diffMin < 1440) return `${Math.round(diffMin / 60)} sa önce`;
  return `${Math.round(diffMin / 1440)} gün önce`;
}

function KPI({ icon: Icon, label, value, suffix, delta, accent, to }) {
  const navigate = useNavigate();
  // KONU 3 — drill-down: `to` verilmişse kart tıklanabilir, ilgili filtreli
  // liste ekranına götürür (CLAUDE.md Kural 5). Verilmemişse eski statik davranış.
  const clickable = !!to;
  return (
    <div
      className={`card card-hover p-5 fade-in ${clickable ? "cursor-pointer" : ""}`}
      data-testid={`kpi-${label}`}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => navigate(to) : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === "Enter") navigate(to); } : undefined}
      title={clickable ? "Detaya git" : undefined}
    >
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent || "bg-[var(--primary)]/10 text-[var(--primary)]"}`}>
          <Icon size={20} />
        </div>
        {delta ? <span className="text-xs text-[var(--primary)] flex items-center gap-1"><ArrowUpRight size={12}/>{delta}</span>
               : clickable && <ArrowUpRight size={14} className="text-[var(--text-dim)]" />}
      </div>
      <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">{label}</div>
      <div className="font-display text-3xl mt-1">{value}{suffix && <span className="text-base text-[var(--text-dim)] ml-1">{suffix}</span>}</div>
    </div>
  );
}

const KARNE_COLORS = { A: "#FF8C00", B: "#3B82F6", C: "#F59E0B", D: "#EF4444" };

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/dashboard/overview").then((r) => setData(r.data));
  }, []);

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const k = data.kpis;
  const karneData = Object.entries(data.karne_distribution).map(([name, value]) => ({ name, value }));

  return (
    <div className="p-8 max-w-[1600px]" data-testid="dashboard-page">
      <header className="mb-8 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">2025 SEZONU · GENEL BAKIŞ</div>
          <h1 className="font-display text-4xl">Kooperatif Yönetim Paneli</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">Tüm bölgeler — gerçek zamanlı operasyonel görünüm</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
          <span className="pulse-dot"/> Canlı veri
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI icon={Users} label="Sözleşmeli Çiftçi" value={fmt(k.farmers_total)} to="/ciftciler" />
        <KPI icon={MapIcon} label="Toplam Parsel" value={fmt(k.parcels_total)} to="/parseller" />
        <KPI icon={Wheat} label="Toplam Alan" value={fmt(k.total_area_dekar)} suffix="dekar" to="/parseller" />
        <KPI icon={FileText} label="Aktif Sözleşme" value={fmt(k.active_contracts)} accent="bg-info/10 text-info" to="/sozlesmeler" />
        <KPI icon={Target} label="Hedef Hasat" value={fmt(k.expected_ton)} suffix="ton" accent="bg-warning/10 text-warning" />
        <KPI icon={TrendingUp} label="Gerçekleşen" value={fmt(k.actual_ton)} suffix="ton" delta={`%${k.yield_completion_pct}`} accent="bg-success/10 text-success" />
        <KPI icon={AlertTriangle} label="Riskli Parsel" value={fmt(k.risky_parcels)} accent="bg-danger/10 text-danger" to="/parseller?risk=1" />
        <KPI icon={Users} label="A Karne Çiftçi" value={data.karne_distribution.A} accent="bg-orange/10 text-orange-500" to="/ciftciler?karne=A" />
      </div>

      {/* Sprint 2 — GIS/IoT/Drone canlı durum kartları (gerçek veriden) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI icon={Satellite} label="Ortalama NDVI" value={k.avg_ndvi} accent="bg-info/10 text-info" to="/uydu" />
        <KPI icon={Satellite} label="Son Uydu Analizi" value={timeAgo(k.last_satellite_scan)} accent="bg-info/10 text-info" to="/uydu" />
        <KPI icon={Radio} label="Aktif Sensör" value={`${fmt(k.iot_sensors_active)} / ${fmt(k.iot_sensors_total)}`} accent="bg-info/10 text-info" to="/operasyon" />
        <KPI icon={Plane} label="Drone Görevi" value={fmt(k.drone_missions_total)} accent="bg-info/10 text-info" to="/operasyon" />
      </div>

      {/* #2 — Ekili / Söküm durumu (uydu + manuel) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <KPI icon={Wheat} label="Ekili Parsel" value={fmt(k.ekili_parcels ?? 0)} accent="bg-success/10 text-success" to="/parseller" />
        <KPI icon={MapIcon} label="Ekili Değil" value={fmt(k.ekili_degil_parcels ?? 0)} to="/parseller" />
        <KPI icon={TrendingUp} label="Sökülen Parsel" value={fmt(k.sokulen_parcels ?? 0)} accent="bg-warning/10 text-warning" to="/parseller" />
        <KPI icon={Wheat} label="Sökülen Alan" value={fmt(k.sokulen_alan_dekar ?? 0)} suffix="dekar" accent="bg-warning/10 text-warning" />
        <KPI icon={Target} label="Kalan (Sökülecek) Alan" value={fmt(k.kalan_alan_dekar ?? 0)} suffix="dekar" accent="bg-info/10 text-info" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg">5 Yıllık Hasat Trendi</h3>
            <div className="text-xs text-[var(--text-dim)]">Ton bazında</div>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data.yield_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
              <XAxis dataKey="year" stroke="#97a8a0" />
              <YAxis stroke="#97a8a0" />
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 12 }}/>
              <Line type="monotone" dataKey="expected" stroke="#fbbf24" strokeWidth={2} name="Beklenen" dot={{ r: 4 }}/>
              <Line type="monotone" dataKey="ton" stroke="#4ade80" strokeWidth={3} name="Gerçekleşen" dot={{ r: 5 }}/>
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Çiftçi Karne Dağılımı</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={karneData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                {karneData.map((e) => <Cell key={e.name} fill={KARNE_COLORS[e.name]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
            </PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-4 gap-2 mt-2">
            {karneData.map((d) => (
              <div key={d.name} className="text-center">
                <div className="text-xs text-[var(--text-dim)]">Karne {d.name}</div>
                <div className="font-display text-xl" style={{ color: KARNE_COLORS[d.name] }}>{d.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg">Bölge / Fabrika Performansı</h3>
          <div className="text-xs text-[var(--text-dim)]">Verim ton/dekar</div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data.regions}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
            <XAxis dataKey="name" stroke="#97a8a0" />
            <YAxis stroke="#97a8a0" />
            <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
            <Bar dataKey="yield_ton" fill="#4ade80" radius={[6, 6, 0, 0]} name="Toplam Ton" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
