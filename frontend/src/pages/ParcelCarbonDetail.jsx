/**
 * PARSEL KARBON AYAK İZİ DETAYI — 2026-08-20 (OTURUM-DEVAM madde 12).
 *
 * "Parsel altındaki alana tıkladığında ya da ana menüden Karbon Ayak İzi
 * modülü altından parsele özel karbon ayak izi sayfası" isteği. Backend
 * ZATEN TAM HAZIRDI (`sustainability.py` — parcel_carbon() + improvement_
 * suggestions() + benefit-report), sadece bu sayfa hiç yazılmamıştı;
 * `ParcelInsightCards.jsx`'teki küçük kart bunun sadece ilk 3 kalemini
 * gösteriyordu. Yeni bir backend YOK — üç mevcut ucu (özet, kalemler,
 * öneriler, sezon karşılaştırması) tüketen ayrı bir sayfa.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import Breadcrumb from "@/components/Breadcrumb";
import { Leaf, TrendingDown, TrendingUp, Minus, Wind, Sparkles } from "lucide-react";

const KALEM_COLORS = [
  "#4ade80", "#60a5fa", "#fbbf24", "#a78bfa", "#fb923c", "#f472b6", "#2dd4bf",
];

export default function ParcelCarbonDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [parcel, setParcel] = useState(null);
  const [season, setSeason] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [compareSeason, setCompareSeason] = useState(new Date().getFullYear() - 1);
  const [benefit, setBenefit] = useState(null);
  const [benefitBusy, setBenefitBusy] = useState(false);
  const [benefitError, setBenefitError] = useState("");

  useEffect(() => {
    api.get(`/parcels/${id}`).then((r) => setParcel(r.data.parcel || r.data)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    setLoading(true);
    setError("");
    api.get(`/sustainability/parcels/${id}`, { params: { season } })
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Karbon hesabı alınamadı"))
      .finally(() => setLoading(false));
  }, [id, season]);

  async function runBenefit() {
    setBenefitBusy(true);
    setBenefitError("");
    setBenefit(null);
    try {
      const r = await api.get(`/sustainability/parcels/${id}/benefit-report`, {
        params: { onceki_sezon: compareSeason, sonraki_sezon: season },
      });
      setBenefit(r.data);
    } catch (e) {
      setBenefitError(e.response?.data?.detail || "Karşılaştırma hesaplanamadı");
    } finally {
      setBenefitBusy(false);
    }
  }

  const fp = data?.ayak_izi;
  const maxKalem = fp?.kalemler?.length ? Math.max(...fp.kalemler.map((k) => k.kg_co2e)) : 1;

  return (
    <div className="p-8 max-w-[1100px]" data-testid="parcel-carbon-page">
      <Breadcrumb items={[
        { label: "Parseller", to: "/parseller" },
        { label: parcel?.name || "Parsel", to: `/parseller/${id}` },
        { label: "Karbon Ayak İzi" },
      ]} />

      <div className="flex items-end justify-between flex-wrap gap-3 mb-6 mt-2">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1 flex items-center gap-1.5">
            <Leaf size={13} /> KARBON AYAK İZİ
          </div>
          <h1 className="font-display text-4xl">{parcel?.name || "Parsel"}</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            IPCC 2019 Refinement + tarımsal LCA ortalamaları — tahmindir, ISO 14064 doğrulaması değildir.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-[var(--text-dim)]">Sezon</label>
          <select className="input w-28" value={season} onChange={(e) => setSeason(Number(e.target.value))}
                  data-testid="carbon-season-select">
            {[2023, 2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button className="btn btn-ghost text-xs" onClick={() => nav(`/parseller/${id}`)}>Parsel Detayına Dön</button>
        </div>
      </div>

      {loading && <div className="text-[var(--text-dim)]">Yükleniyor…</div>}
      {error && <div className="card p-4 text-red-400 text-sm">{error}</div>}

      {fp && (
        <>
          {/* ÜST — büyük özet kartlar */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="card p-5">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-1">Toplam Ayak İzi</div>
              <div className="font-display text-4xl">{fp.toplam_kg_co2e?.toLocaleString("tr-TR")}</div>
              <div className="text-sm text-[var(--text-dim)]">kg CO₂e ({(fp.toplam_kg_co2e / 1000).toFixed(2)} ton)</div>
            </div>
            <div className="card p-5">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-1">Dekar Başına</div>
              <div className="font-display text-4xl">{fp.dekar_basina_kg_co2e ?? "—"}</div>
              <div className="text-sm text-[var(--text-dim)]">kg CO₂e / dekar</div>
            </div>
            <div className="card p-5">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-1">Ton Ürün Başına</div>
              <div className="font-display text-4xl">{fp.ton_urun_basina_kg_co2e ?? "—"}</div>
              <div className="text-sm text-[var(--text-dim)]">{fp.ton_urun_basina_kg_co2e == null ? "hasat verisi yok" : "kg CO₂e / ton"}</div>
            </div>
          </div>

          {/* KALEM DÖKÜMÜ */}
          <div className="card p-5 mb-6">
            <h3 className="font-display text-lg mb-4 flex items-center gap-2"><Wind size={16} className="text-[var(--primary)]" /> Kalem Dökümü</h3>
            <div className="space-y-3">
              {fp.kalemler.map((k, i) => (
                <div key={k.kalem}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span>{k.kalem} <span className="text-[var(--text-dim)] text-xs">({k.miktar} {k.birim})</span></span>
                    <b>{k.kg_co2e.toLocaleString("tr-TR")} kg CO₂e</b>
                  </div>
                  <div className="w-full h-2.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
                    <div style={{
                      width: `${Math.max(2, (k.kg_co2e / maxKalem) * 100)}%`,
                      height: "100%", background: KALEM_COLORS[i % KALEM_COLORS.length],
                    }} />
                  </div>
                </div>
              ))}
            </div>
            {data.varsayimlar?.length > 0 && (
              <div className="mt-4 pt-3 border-t border-[var(--border)] text-[11px] text-[var(--text-dim)]">
                <div className="uppercase tracking-wider mb-1">Varsayımlar</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {data.varsayimlar.map((v, i) => <li key={i}>{v}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* İYİLEŞTİRME ÖNERİLERİ */}
          <div className="card p-5 mb-6">
            <h3 className="font-display text-lg mb-4 flex items-center gap-2">
              <Sparkles size={16} className="text-[var(--primary)]" /> İyileştirme Önerileri
              {data.oneriler?.length > 0 && <span className="badge badge-a text-xs">{data.oneriler.length}</span>}
            </h3>
            {(!data.oneriler || data.oneriler.length === 0) ? (
              <p className="text-sm text-[var(--text-dim)]">Bu sezon için ölçülmüş veriden çıkan bir iyileştirme önerisi yok.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {data.oneriler.map((o, i) => (
                  <div key={i} className="p-4 rounded-lg border border-[var(--border)] bg-[var(--surface-2)]">
                    <div className="font-medium text-sm mb-1">{o.baslik}</div>
                    <p className="text-xs text-[var(--text-dim)] mb-2">{o.gerekce}</p>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="badge badge-a">−{o.kazanc_kg_co2e.toLocaleString("tr-TR")} kg CO₂e</span>
                      {o.kazanc_tl_tahmini != null && (
                        <span className="text-[var(--text-dim)]">~{o.kazanc_tl_tahmini.toLocaleString("tr-TR")} TL tasarruf</span>
                      )}
                    </div>
                    {o.ek_fayda && <p className="text-[11px] text-[var(--primary)] mt-1.5">+ {o.ek_fayda}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* FAYDA RAPORU — sezon karşılaştırması */}
          <div className="card p-5">
            <h3 className="font-display text-lg mb-3">Ne Kadar İyileşme Sağlandı?</h3>
            <p className="text-xs text-[var(--text-dim)] mb-3">
              İki sezonun ayak izini karşılaştırıp gerçekleşen (veya beklenen) iyileşmeyi tahmin eder.
            </p>
            <div className="flex items-end gap-3 flex-wrap mb-4">
              <div>
                <label className="text-[11px] text-[var(--text-dim)] block mb-1">Önceki Sezon</label>
                <select className="input w-28" value={compareSeason} onChange={(e) => setCompareSeason(Number(e.target.value))}>
                  {[2023, 2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div className="text-[var(--text-dim)] pb-2">→</div>
              <div>
                <label className="text-[11px] text-[var(--text-dim)] block mb-1">Sonraki Sezon</label>
                <input className="input w-28" value={season} disabled />
              </div>
              <button className="btn btn-primary text-sm" onClick={runBenefit} disabled={benefitBusy}
                      data-testid="carbon-benefit-run">
                {benefitBusy ? "Hesaplanıyor…" : "Karşılaştır"}
              </button>
            </div>
            {benefitError && <div className="text-red-400 text-sm mb-2">{benefitError}</div>}
            {benefit && (
              <div className="p-4 rounded-lg bg-[var(--surface-2)]">
                <div className="flex items-center gap-3 mb-3">
                  {benefit.degisim_kg_co2e < 0 ? (
                    <span className="flex items-center gap-1.5 text-lg font-display text-green-400">
                      <TrendingDown size={20} /> {Math.abs(benefit.degisim_kg_co2e).toLocaleString("tr-TR")} kg CO₂e azaldı
                    </span>
                  ) : benefit.degisim_kg_co2e > 0 ? (
                    <span className="flex items-center gap-1.5 text-lg font-display text-red-400">
                      <TrendingUp size={20} /> {benefit.degisim_kg_co2e.toLocaleString("tr-TR")} kg CO₂e arttı
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-lg font-display text-[var(--text-dim)]">
                      <Minus size={20} /> Değişim yok
                    </span>
                  )}
                  {benefit.degisim_yuzde != null && (
                    <span className="badge badge-neutral">{benefit.degisim_yuzde > 0 ? "+" : ""}{benefit.degisim_yuzde}%</span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm mb-3">
                  <div><span className="text-[var(--text-dim)]">{benefit.onceki.sezon}:</span> <b>{benefit.onceki.kg_co2e?.toLocaleString("tr-TR")} kg CO₂e</b></div>
                  <div><span className="text-[var(--text-dim)]">{benefit.sonraki.sezon}:</span> <b>{benefit.sonraki.kg_co2e?.toLocaleString("tr-TR")} kg CO₂e</b></div>
                </div>
                <div className="space-y-1.5">
                  {Object.entries(benefit.kalem_karsilastirma).map(([kalem, v]) => (
                    <div key={kalem} className="flex items-center justify-between text-xs">
                      <span className="text-[var(--text-dim)]">{kalem}</span>
                      <span>{v.onceki} → <b>{v.sonraki ?? "—"}</b> kg CO₂e</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
