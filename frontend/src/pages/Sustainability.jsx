/**
 * KARBON AYAK İZİ & SÜRDÜRÜLEBİLİRLİK — 2026-08-19
 *
 * Backend: `backend/sustainability.py`. Bu modül bugüne kadar SADECE parsel
 * bazlı iki uç sunuyordu ve yalnızca `ParcelInsightCards` içindeki tek bir
 * kartla tüketiliyordu — "kooperatifin toplam ayak izi ne?" sorusunun cevabı
 * hiçbir ekranda yoktu. Kullanıcının "katma değeri yüksek alanları öne çıkar"
 * isteği kapsamında bu ekran açıldı.
 *
 * Üç blok: işletme geneli özet → nereden kaynaklanıyor (kalem dökümü) →
 * ne yapmalı (iyileştirme fırsatları, tahmini kazançla sıralı).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import {
  Leaf, AlertTriangle, Loader2, TrendingDown, Factory, Droplets, Info, RefreshCw,
} from "lucide-react";

const fmt = (n, d = 1) =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : new Intl.NumberFormat("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);

const KALEM_ICON = {
  "Azotlu gübre": Leaf,
  "Toprak işleme / makine yakıtı": Factory,
  "Sulama enerjisi": Droplets,
};

export default function Sustainability() {
  const nav = useNavigate();
  const [season, setSeason] = useState(new Date().getFullYear());
  const [limit, setLimit] = useState(200);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = () => {
    setBusy(true); setErr(null);
    api.get("/sustainability/summary", { params: { season, limit } })
      .then((r) => setData(r.data))
      .catch((e) => setErr(e.response?.data?.detail || e.message || "Özet hesaplanamadı."))
      .finally(() => setBusy(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <div className="p-8 max-w-[1400px]" data-testid="sustainability-page">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SÜRDÜRÜLEBİLİRLİK</div>
          <h1 className="font-display text-4xl flex items-center gap-2">
            <Leaf size={28} /> Karbon Ayak İzi
          </h1>
          <p className="text-[var(--text-dim)] text-sm mt-1 max-w-3xl">
            Üretimin sera gazı yükü — gerçek sözleşme, sulama ve toprak kayıtlarından
            hesaplanır. Nereden kaynaklandığını ve nasıl azaltılacağını gösterir.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-xs text-[var(--text-dim)]">Sezon</label>
            <input className="input" type="number" value={season} style={{ width: 100 }}
                   onChange={(e) => setSeason(Number(e.target.value))} />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)]">Parsel sayısı</label>
            <select className="input" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
              {[50, 200, 500, 1000].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <button className="btn btn-primary" onClick={load} disabled={busy} data-testid="carbon-run">
            <RefreshCw size={15} className={busy ? "animate-spin" : ""} /> Hesapla
          </button>
        </div>
      </header>

      {err && (
        <div className="card p-3 mb-4 text-sm text-red-400 flex items-center gap-2">
          <AlertTriangle size={15} /> {err}
        </div>
      )}

      {busy && !data && (
        <div className="card p-6 text-center text-sm text-[var(--text-dim)]">
          <Loader2 size={18} className="animate-spin inline mr-2" />
          Parsellerin sözleşme, sulama ve toprak kayıtları taranıyor…
        </div>
      )}

      {data && (
        <>
          {data.kapsam?.truncated && (
            <div className="card p-3 mb-4 text-xs text-amber-300 flex items-center gap-2">
              <AlertTriangle size={14} />
              {data.kapsam.toplam_parsel} parselden {data.kapsam.islenen_parsel} tanesi hesaplandı
              (her parsel için ayrı kayıt sorgusu çalışıyor). Üstteki "Parsel sayısı"
              ile kapsamı genişletebilirsiniz.
            </div>
          )}

          {/* ---- İŞLETME GENELİ ---- */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[["Toplam Ayak İzi", `${fmt(data.toplam_ton_co2e, 2)} ton CO₂e`],
              ["Dekar Başına", `${fmt(data.dekar_basina_kg_co2e)} kg CO₂e`],
              ["Kapsanan Alan", `${fmt(data.toplam_alan_dekar)} dekar`],
              ["Hesaplanan Parsel", fmt(data.kapsam?.islenen_parsel, 0)]].map(([l, v]) => (
              <div key={l} className="card p-4">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{l}</div>
                <div className="font-display text-2xl mt-1">{v}</div>
              </div>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            {/* ---- KAYNAK DÖKÜMÜ ---- */}
            <div className="card p-5">
              <h3 className="font-display text-xl mb-1">Ayak İzi Nereden Geliyor?</h3>
              <p className="text-xs text-[var(--text-dim)] mb-4">
                En büyük kalem, azaltım çalışmasının başlaması gereken yerdir.
              </p>
              <div className="flex flex-col gap-3">
                {(data.kalemler || []).map((k) => {
                  const Icon = KALEM_ICON[k.kalem] || Leaf;
                  return (
                    <div key={k.kalem}>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="flex items-center gap-2">
                          <Icon size={14} className="text-[var(--primary)]" /> {k.kalem}
                        </span>
                        <span className="text-[var(--text-dim)]">
                          {fmt(k.kg_co2e, 0)} kg · %{fmt(k.yuzde)}
                        </span>
                      </div>
                      <div className="h-2 rounded bg-[var(--surface-2)] overflow-hidden">
                        <div className="h-full bg-[var(--primary)]"
                             style={{ width: `${Math.min(100, k.yuzde)}%` }} />
                      </div>
                    </div>
                  );
                })}
                {(data.kalemler || []).length === 0 && (
                  <div className="text-sm text-[var(--text-dim)]">Kalem verisi yok.</div>
                )}
              </div>
            </div>

            {/* ---- İYİLEŞTİRME FIRSATLARI ---- */}
            <div className="card p-5">
              <h3 className="font-display text-xl mb-1 flex items-center gap-2">
                <TrendingDown size={18} className="text-[var(--primary)]" /> İyileştirme Fırsatları
              </h3>
              <p className="text-xs text-[var(--text-dim)] mb-4">
                Tahmini kazanca göre sıralı — en üstteki en çok azaltım sağlar.
              </p>
              <div className="flex flex-col gap-3">
                {(data.iyilestirme_firsatlari || []).map((o, i) => (
                  <div key={i} className="bg-[var(--surface-2)] rounded-lg p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-medium">{o.baslik}</div>
                      <span className="badge badge-a whitespace-nowrap">
                        −{fmt(o.toplam_kazanc_kg_co2e, 0)} kg
                      </span>
                    </div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">
                      {o.parsel_sayisi} parselde uygulanabilir
                      {o.aciklama ? ` · ${o.aciklama}` : ""}
                    </div>
                  </div>
                ))}
                {(data.iyilestirme_firsatlari || []).length === 0 && (
                  <div className="text-sm text-[var(--text-dim)]">
                    Bu kapsamda öneri üretilmedi.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ---- EN YÜKSEK PARSELLER ---- */}
          <div className="card overflow-hidden mt-4">
            <div className="p-3 border-b border-[var(--border)] font-display text-lg">
              En Yüksek Ayak İzli Parseller
            </div>
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-3">Parsel</th><th className="p-3">Alan</th>
                  <th className="p-3">Toplam CO₂e</th><th className="p-3">Dekar Başına</th><th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {(data.en_yuksek_parseller || []).map((p) => (
                  <tr key={p.parcel_id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                    <td className="p-3">{p.parsel || p.parcel_id?.slice(0, 8)}</td>
                    <td className="p-3">{fmt(p.alan_dekar)} da</td>
                    <td className="p-3">{fmt(p.kg_co2e, 0)} kg</td>
                    <td className="p-3">{fmt(p.dekar_basina)} kg/da</td>
                    <td className="p-3 text-right flex justify-end gap-1">
                      <button className="btn btn-ghost text-xs"
                              onClick={() => nav(`/parseller/${p.parcel_id}`)}>Parsel →</button>
                      {/* 2026-08-20 — parsele özel karbon detay sayfası (ParcelCarbonDetail.jsx) */}
                      <button className="btn btn-ghost text-xs"
                              onClick={() => nav(`/parseller/${p.parcel_id}/karbon`)}
                              data-testid={`carbon-detail-${p.parcel_id}`}>Karbon Raporu →</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="text-[11px] text-[var(--text-dim)] mt-3 flex items-start gap-1.5">
            <Info size={12} className="mt-px shrink-0" />
            Hesap IPCC 2019 Refinement ve tarımsal LCA ortalamalarına dayanır —
            <b className="mx-1">tahmindir</b>, ISO 14064 doğrulaması değildir. Gübre miktarı
            sözleşmedeki avans kaydından türetilir (ayrı gübreleme kaydı modülü yok).
          </div>
        </>
      )}
    </div>
  );
}
