/**
 * Demo Senaryo Oynatıcı — OTURUM-DEVAM-19082026.md madde 10.
 *
 * backend/demo_scenario.py'nin `GET /demo-scenario/steps` ucundan gelen
 * sabit adım listesini (gerçek ekranlara giden narrasyon turu) oynatır.
 * Sahte veri GÖSTERMEZ — sistemdeki en dolu çiftçi/parsel/sezon zincirine
 * göre adımları doldurur, örnek yoksa adım "atlanabilir" işaretlenir.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { ChevronLeft, ChevronRight, ExternalLink, Info } from "lucide-react";

export default function DemoScenario() {
  const nav = useNavigate();
  const [steps, setSteps] = useState([]);
  const [showcase, setShowcase] = useState(null);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/demo-scenario/steps").then((r) => {
      setSteps(r.data.steps || []);
      setShowcase(r.data.showcase || null);
    }).finally(() => setLoading(false));
  }, []);

  const step = steps[idx];

  function goTo(route) {
    if (!route) return;
    nav(route);
  }

  if (loading) return <div className="p-8 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="p-8 max-w-[800px]" data-testid="demo-scenario-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SUNUM MODU</div>
      <h1 className="font-display text-4xl mb-1">Senaryoyu Oynat</h1>
      <p className="text-sm text-[var(--text-dim)] mb-6">
        Platformun uçtan uca hikayesini gerçek ekranlar üzerinden anlatan bir sunum turu.
        {showcase?.farmer_name && (
          <> Bu turda örnek çiftçi: <b>{showcase.farmer_name}</b>{showcase.parcel_name ? `, parsel: ${showcase.parcel_name}` : ""}.</>
        )}
      </p>

      {steps.length === 0 ? (
        <div className="card p-6 text-center text-[var(--text-dim)] text-sm">Senaryo adımı bulunamadı.</div>
      ) : (
        <div className="card p-6" data-testid="demo-scenario-step">
          <div className="flex items-center justify-between mb-4">
            <div className="text-xs text-[var(--text-dim)]">Adım {idx + 1} / {steps.length}</div>
            <div className="flex gap-1">
              {steps.map((s, i) => (
                <button key={s.id} onClick={() => setIdx(i)}
                        className={`w-2 h-2 rounded-full ${i === idx ? "bg-[var(--primary)]" : "bg-[var(--border)]"}`}
                        title={s.title} data-testid={`demo-scenario-dot-${i}`} />
              ))}
            </div>
          </div>

          <h2 className="text-xl font-display mb-2">{step.title}</h2>
          <p className="text-sm text-[var(--text-secondary,var(--text))] mb-4 leading-relaxed">{step.narration}</p>

          {!step.available && (
            <div className="flex items-center gap-2 text-xs text-[var(--text-dim)] bg-[var(--surface-2)] rounded-lg p-2.5 mb-4">
              <Info size={14} /> Bu adım için sistemde henüz örnek kayıt yok — atlayabilirsiniz.
            </div>
          )}

          <div className="flex items-center justify-between mt-6">
            <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx === 0}
                    className="btn btn-ghost text-sm" data-testid="demo-scenario-prev">
              <ChevronLeft size={15} /> Geri
            </button>

            <button onClick={() => goTo(step.route)} disabled={!step.available}
                    className="btn btn-primary text-sm" data-testid="demo-scenario-goto">
              Bu Ekrana Git <ExternalLink size={14} />
            </button>

            <button onClick={() => setIdx((i) => Math.min(steps.length - 1, i + 1))} disabled={idx === steps.length - 1}
                    className="btn btn-ghost text-sm" data-testid="demo-scenario-next">
              İleri <ChevronRight size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
