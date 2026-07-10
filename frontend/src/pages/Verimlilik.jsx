import { useEffect, useState } from "react";
import api from "@/api";
import { TrendingUp, Award, Target } from "lucide-react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

export default function Verimlilik() {
  const [data, setData] = useState(null);
  const [scenario, setScenario] = useState({ drought: 0, price: 0, cost: 0 });
  const [scenarioResult, setScenarioResult] = useState(null);

  useEffect(() => { api.get("/analytics/yields").then((r) => setData(r.data)); }, []);

  useEffect(() => {
    api.get("/analytics/scenario", {
      params: { drought_pct: scenario.drought, price_pct: scenario.price, cost_pct: scenario.cost }
    }).then((r) => setScenarioResult(r.data));
  }, [scenario]);

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1600px]" data-testid="verimlilik-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M17 · MODÜL</div>
        <h1 className="font-display text-4xl">Verimlilik & Analitik</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Veriden içgörü — karar destek motoru</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="card p-5 lg:col-span-2">
          <h3 className="font-display text-lg mb-4">5 Yıllık Verim Trendi (ton/dekar)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data.trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
              <XAxis dataKey="year" stroke="#97a8a0"/>
              <YAxis stroke="#97a8a0"/>
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
              <Legend wrapperStyle={{ fontSize: 12 }}/>
              <Line type="monotone" dataKey="ton_per_dekar" stroke="#4ade80" strokeWidth={3} name="Ton/Dekar" dot={{ r: 5 }}/>
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <Award className="text-[var(--primary)] mb-2"/>
          <h3 className="font-display text-lg mb-1">En Verimli 10 Parsel</h3>
          <div className="text-xs text-[var(--text-dim)] mb-3">2025 sezonu</div>
          <div className="space-y-1.5 max-h-[260px] overflow-y-auto scrollbar">
            {data.top_parcels.slice(0, 10).map((p, i) => (
              <div key={p.id} className="flex items-center justify-between p-2 bg-[var(--surface-2)] rounded">
                <div>
                  <div className="text-xs text-[var(--text-dim)]">#{i+1}</div>
                  <div className="text-sm font-medium">{(p.actual_ton/p.area_dekar).toFixed(2)} t/da</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-[var(--text-dim)]">{p.area_dekar.toFixed(0)} dekar</div>
                  <div className="text-sm text-[var(--primary)]">{p.actual_ton.toFixed(1)} ton</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-5 mb-6">
        <h3 className="font-display text-lg mb-4">Bölge Performans Karşılaştırması</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data.by_region}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
            <XAxis dataKey="region" stroke="#97a8a0"/>
            <YAxis yAxisId="left" stroke="#97a8a0"/>
            <YAxis yAxisId="right" orientation="right" stroke="#fbbf24"/>
            <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
            <Legend wrapperStyle={{ fontSize: 12 }}/>
            <Bar yAxisId="left" dataKey="ton_per_dekar" fill="#4ade80" name="Ton/Dekar" radius={[6,6,0,0]}/>
            <Bar yAxisId="right" dataKey="avg_polar" fill="#fbbf24" name="Polar Oranı %" radius={[6,6,0,0]}/>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card p-5">
        <div className="flex items-center gap-2 mb-1">
          <Target className="text-amber-400" size={20}/>
          <h3 className="font-display text-lg">Senaryo Simülatörü (What-if)</h3>
        </div>
        <p className="text-xs text-[var(--text-dim)] mb-5">Risk faktörlerini ayarla, kâr-zarar etkisini gör</p>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-2 block">KURAKLIK ETKİSİ (verim düşüşü)</label>
            <input type="range" min="0" max="50" value={scenario.drought}
                   onChange={(e) => setScenario({...scenario, drought: parseInt(e.target.value)})}
                   className="w-full"/>
            <div className="text-sm mt-1">-%{scenario.drought}</div>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-2 block">FİYAT DEĞİŞİMİ</label>
            <input type="range" min="-30" max="50" value={scenario.price}
                   onChange={(e) => setScenario({...scenario, price: parseInt(e.target.value)})}
                   className="w-full"/>
            <div className="text-sm mt-1">{scenario.price > 0 ? "+" : ""}%{scenario.price}</div>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-2 block">MALİYET ARTIŞI</label>
            <input type="range" min="0" max="50" value={scenario.cost}
                   onChange={(e) => setScenario({...scenario, cost: parseInt(e.target.value)})}
                   className="w-full"/>
            <div className="text-sm mt-1">+%{scenario.cost}</div>
          </div>
        </div>

        {scenarioResult && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="p-4 bg-[var(--surface-2)] rounded-lg">
              <div className="text-xs text-[var(--text-dim)]">Mevcut Kâr</div>
              <div className="font-display text-2xl">{fmt(scenarioResult.base.profit)} ₺</div>
            </div>
            <div className="p-4 bg-[var(--surface-2)] rounded-lg">
              <div className="text-xs text-[var(--text-dim)]">Senaryo Kârı</div>
              <div className="font-display text-2xl">{fmt(scenarioResult.scenario.profit)} ₺</div>
            </div>
            <div className="p-4 bg-[var(--surface-2)] rounded-lg">
              <div className="text-xs text-[var(--text-dim)]">Senaryo Tonajı</div>
              <div className="font-display text-2xl">{fmt(scenarioResult.scenario.ton)} <span className="text-sm text-[var(--text-dim)]">ton</span></div>
            </div>
            <div className={`p-4 rounded-lg ${scenarioResult.scenario.profit_delta_pct < 0 ? "bg-red-500/10" : "bg-[var(--primary)]/10"}`}>
              <div className="text-xs text-[var(--text-dim)]">Kâr Değişimi</div>
              <div className={`font-display text-2xl ${scenarioResult.scenario.profit_delta_pct < 0 ? "text-red-400" : "text-[var(--primary)]"}`}>
                {scenarioResult.scenario.profit_delta_pct > 0 ? "+" : ""}%{scenarioResult.scenario.profit_delta_pct}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
