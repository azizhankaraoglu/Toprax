import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";

export function Sozlesmeler() {
  const [contracts, setContracts] = useState([]);
  const [parcels, setParcels] = useState([]);
  const load = () => api.get("/contracts", { params: { season: 2025 }}).then((r) => setContracts(r.data));
  useEffect(() => {
    load();
    api.get("/parcels", { params: { limit: 500 } }).then((r) => setParcels(r.data));
  }, []);

  return (
    <div className="p-8" data-testid="sozlesmeler-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M04 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Sözleşme & Kota — 2025</h1>

      <QuickAddPanel
        title="Yeni Sözleşme"
        testId="contract-add"
        fields={[
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "season", label: "Sezon", type: "number", required: true, default: 2025 },
          { name: "variety", label: "Çeşit", required: true },
          { name: "kota_dekar", label: "Kota (dekar)", type: "number", step: "0.1", required: true },
          { name: "kota_ton", label: "Kota (ton)", type: "number", step: "0.1", required: true },
          { name: "advance_seed_kg", label: "Tohum Avansı (kg)", type: "number", step: "0.1" },
          { name: "advance_fertilizer_kg", label: "Gübre Avansı (kg)", type: "number", step: "0.1" },
          { name: "status", label: "Durum", type: "select", default: "taslak",
            options: [{ value: "taslak", label: "Taslak" }, { value: "imzalı", label: "İmzalı" }, { value: "iptal", label: "İptal" }] },
        ]}
        onSubmit={async (v) => {
          await api.post("/contracts", {
            ...v,
            season: Number(v.season),
            kota_dekar: Number(v.kota_dekar),
            kota_ton: Number(v.kota_ton),
            advance_seed_kg: v.advance_seed_kg ? Number(v.advance_seed_kg) : null,
            advance_fertilizer_kg: v.advance_fertilizer_kg ? Number(v.advance_fertilizer_kg) : null,
          });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Sözleşme No</th><th className="p-4">Çeşit</th><th className="p-4">Kota (da)</th><th className="p-4">Kota (ton)</th><th className="p-4">Tohum Avans</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {contracts.slice(0,50).map((c) => (
              <tr key={c.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 font-mono text-xs text-[var(--text-dim)]">{c.contract_no}</td>
                <td className="p-4">{c.variety}</td>
                <td className="p-4">{c.kota_dekar}</td>
                <td className="p-4">{c.kota_ton}</td>
                <td className="p-4">{c.advance_seed_kg} kg</td>
                <td className="p-4"><span className={`badge ${c.status==="imzalı"?"badge-a":"badge-c"}`}>{c.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Ekim() {
  const [plantings, setPlantings] = useState([]);
  const [parcels, setParcels] = useState([]);
  const load = () => api.get("/plantings", { params: { season: 2025 }}).then((r) => setPlantings(r.data));
  useEffect(() => {
    load();
    api.get("/parcels", { params: { limit: 500 } }).then((r) => setParcels(r.data));
  }, []);
  const stageBadge = { ekim: "badge-b", gelişim: "badge-c", olgunlaşma: "badge-c", hasat: "badge-a" };
  return (
    <div className="p-8" data-testid="ekim-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M05 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Ekim Planlama — 2025</h1>

      <QuickAddPanel
        title="Yeni Ekim Kaydı"
        testId="planting-add"
        fields={[
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "season", label: "Sezon", type: "number", required: true, default: 2025 },
          { name: "variety", label: "Çeşit", required: true },
          { name: "planting_date", label: "Ekim Tarihi", type: "date", required: true },
          { name: "expected_harvest_date", label: "Beklenen Hasat", type: "date", required: true },
          { name: "stage", label: "Aşama", type: "select", default: "ekim",
            options: [
              { value: "ekim", label: "Ekim" }, { value: "gelişim", label: "Gelişim" },
              { value: "olgunlaşma", label: "Olgunlaşma" }, { value: "hasat", label: "Hasat" },
            ] },
        ]}
        onSubmit={async (v) => { await api.post("/plantings", { ...v, season: Number(v.season) }); load(); }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Çeşit</th><th className="p-4">Ekim Tarihi</th><th className="p-4">Beklenen Hasat</th><th className="p-4">Aşama</th>
          </tr></thead>
          <tbody>
            {plantings.slice(0,80).map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">{p.variety}</td>
                <td className="p-4 text-[var(--text-dim)]">{p.planting_date}</td>
                <td className="p-4 text-[var(--text-dim)]">{p.expected_harvest_date}</td>
                <td className="p-4"><span className={`badge ${stageBadge[p.stage]||"badge-neutral"}`}>{p.stage}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Lojistik() {
  const [appts, setAppts] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const load = () => api.get("/logistics/appointments").then((r) => setAppts(r.data));
  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
  }, []);
  return (
    <div className="p-8" data-testid="lojistik-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M08 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Lojistik & Kantar</h1>

      <QuickAddPanel
        title="Yeni Randevu"
        testId="appointment-add"
        fields={[
          { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
            options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
          { name: "scheduled_at", label: "Tarih/Saat", type: "datetime-local", required: true },
          { name: "truck_plate", label: "Plaka", required: true },
          { name: "estimated_ton", label: "Tahmini Ton", type: "number", step: "0.1", required: true },
        ]}
        onSubmit={async (v) => {
          await api.post("/logistics/appointments", {
            ...v,
            estimated_ton: Number(v.estimated_ton),
            scheduled_at: new Date(v.scheduled_at).toISOString(),
          });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Tarih</th><th className="p-4">Plaka</th><th className="p-4">Tahmini Ton</th><th className="p-4">Gerçek Ton</th><th className="p-4">Polar</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {appts.map((a) => (
              <tr key={a.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 text-[var(--text-dim)]">{new Date(a.scheduled_at).toLocaleString("tr-TR")}</td>
                <td className="p-4 font-mono">{a.truck_plate}</td>
                <td className="p-4">{a.estimated_ton} t</td>
                <td className="p-4">{a.actual_ton ? `${a.actual_ton} t` : "-"}</td>
                <td className="p-4">{a.polar_oran ? `%${a.polar_oran}` : "-"}</td>
                <td className="p-4"><span className="badge badge-b">{a.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Karne() {
  const [top, setTop] = useState([]);
  const [bottom, setBottom] = useState([]);
  useEffect(() => {
    api.get("/karne/top").then((r) => setTop(r.data));
    api.get("/karne/bottom").then((r) => setBottom(r.data));
  }, []);
  return (
    <div className="p-8" data-testid="karne-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M12 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Çiftçi Karne / Performans Skoru</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 text-[var(--primary)]">🏆 En Yüksek 10</h3>
          {top.map((f, i) => (
            <div key={f.id} className="flex items-center justify-between p-3 border-b border-[var(--border)]">
              <div className="flex items-center gap-3">
                <div className="text-[var(--text-dim)] font-display text-xl w-6">#{i+1}</div>
                <div><div className="text-sm">{f.full_name}</div><div className="text-xs text-[var(--text-dim)]">{f.village}</div></div>
              </div>
              <span className={`badge badge-${f.karne_score.toLowerCase()}`}>{f.karne_score} · {f.karne_points}</span>
            </div>
          ))}
        </div>
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 text-red-400">⚠️ Geliştirme Bekleyen 10</h3>
          {bottom.map((f, i) => (
            <div key={f.id} className="flex items-center justify-between p-3 border-b border-[var(--border)]">
              <div className="flex items-center gap-3">
                <div className="text-[var(--text-dim)] font-display text-xl w-6">#{i+1}</div>
                <div><div className="text-sm">{f.full_name}</div><div className="text-xs text-[var(--text-dim)]">{f.village}</div></div>
              </div>
              <span className={`badge badge-${f.karne_score.toLowerCase()}`}>{f.karne_score} · {f.karne_points}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Bildirimler() {
  const [notifs, setNotifs] = useState([]);
  useEffect(() => { api.get("/notifications").then((r) => setNotifs(r.data)); }, []);
  const chBadge = { sms: "badge-b", whatsapp: "badge-a", push: "badge-c", in_app: "badge-neutral" };
  return (
    <div className="p-8" data-testid="bildirimler-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M11 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Bildirim Merkezi</h1>
      <div className="card overflow-hidden">
        {notifs.map((n) => (
          <div key={n.id} className="p-4 border-b border-[var(--border)] flex items-start gap-4">
            <span className={`badge ${chBadge[n.channel]||"badge-neutral"}`}>{n.channel}</span>
            <div className="flex-1">
              <div className="text-sm font-medium">{n.title}</div>
              <div className="text-xs text-[var(--text-dim)] mt-0.5">{n.message}</div>
              <div className="text-[10px] text-[var(--text-dim)] mt-1">{new Date(n.created_at).toLocaleString("tr-TR")}</div>
            </div>
            <span className={`badge ${n.status==="okundu"?"badge-a":"badge-c"}`}>{n.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
