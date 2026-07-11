/**
 * UFYD DASHBOARD (IT-21 / FAZ 7 — UFYD son parçası)
 *
 * Ledger/SupportRequest/Entitlement'tan CANLI hesaplanır (bkz.
 * backend/reconciliation.py GET /ufyd/dashboard) — statik/önbelleklenmiş
 * bir rapor değildir, kabul kriteri bunu açıkça ister.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Wallet, HandCoins, Clock, Users, ListChecks, Landmark } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

function KPI({ icon: Icon, label, value, suffix, accent }) {
  return (
    <div className="card card-hover p-5 fade-in">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${accent || "bg-[var(--primary)]/10 text-[var(--primary)]"}`}>
        <Icon size={20} />
      </div>
      <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">{label}</div>
      <div className="font-display text-3xl mt-1">{value}{suffix && <span className="text-base text-[var(--text-dim)] ml-1">{suffix}</span>}</div>
    </div>
  );
}

export default function UfydDashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/ufyd/dashboard").then((r) => setData(r.data));
  }, []);

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[1600px]" data-testid="ufyd-dashboard-page">
      <header className="mb-8">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">UFYD — ÜRETİM FİNANS YAŞAM DÖNGÜSÜ</div>
        <h1 className="font-display text-4xl">UFYD Dashboard</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Ledger/Destek/Hakediş verilerinden canlı hesaplanır</p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI icon={Wallet} label="Toplam Hakediş" value={fmt(data.total_hakedis)} suffix="₺" accent="bg-emerald-500/10 text-emerald-400" />
        <KPI icon={HandCoins} label="Toplam Destek" value={fmt(data.total_destek)} suffix="₺" accent="bg-amber-500/10 text-amber-400" />
        <KPI icon={Clock} label="Bekleyen Ödemeler" value={fmt(data.pending_payments)} suffix="₺" accent="bg-blue-500/10 text-blue-400" />
        <KPI icon={Landmark} label="Nakit İhtiyacı" value={fmt(data.cash_need)} suffix="₺" accent="bg-red-500/10 text-red-400" />
        <KPI icon={ListChecks} label="Bekleyen Destek Talebi" value={fmt(data.pending_support_requests)} accent="bg-violet-500/10 text-violet-400" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 flex items-center gap-2"><Users size={16} className="text-[var(--primary)]"/>En Çok Destek Alan Çiftçiler</h3>
          <div className="space-y-2">
            {data.top_destek_farmers.map((f) => (
              <div key={f.farmer_id} className="flex justify-between items-center text-sm border-b border-[var(--border)] pb-2">
                <div>
                  <div>{f.full_name}</div>
                  <div className="text-xs text-[var(--text-dim)]">{f.member_no}</div>
                </div>
                <div className="font-mono text-[var(--primary)]">{fmt(f.total_destek)} ₺</div>
              </div>
            ))}
            {data.top_destek_farmers.length === 0 && (
              <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz destek verisi yok</div>
            )}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 flex items-center gap-2"><Landmark size={16} className="text-[var(--primary)]"/>Bölgesel Destek Dağılımı</h3>
          <div className="space-y-2">
            {Object.entries(data.destek_by_region).map(([region, amount]) => (
              <div key={region} className="flex justify-between items-center text-sm border-b border-[var(--border)] pb-2">
                <div className="font-mono text-xs text-[var(--text-dim)]">{region}</div>
                <div className="font-mono text-[var(--primary)]">{fmt(amount)} ₺</div>
              </div>
            ))}
            {Object.keys(data.destek_by_region).length === 0 && (
              <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz destek verisi yok</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
