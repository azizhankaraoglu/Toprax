/**
 * PARSEL KARAR PANELİ — 2026-08-19
 *
 * Kullanıcı geri bildirimi: *"eklediğim ekim/söküm tahminlerini nereden test
 * edeceğim"*, *"Open-Meteo sanırım UI'a eklenmedi"*, *"polar tahminini ve hangi
 * ürün ekili olduğunu göremedim"*.
 *
 * Üç backend modülü ZATEN VARDI ama hiçbir ekranda tüketilmiyordu:
 *   - `weather.py`        → GET /weather/parcels/{id}            (Open-Meteo)
 *   - `polar_engine.py`   → GET /polar/parcels/{id}              (polar + söküm)
 *   - `polar_engine.py`   → GET /polar/parcels/{id}/sowing-window (ekim penceresi)
 *
 * Bu bileşen üçünü TEK kartta birleştirir. Yeni bir backend ucu YAZILMADI —
 * IT-13'ün "yeni endpoint icat etme, mevcut olanı bağlamla çağır" kalıbı.
 *
 * Her blok bağımsız yüklenir ve bağımsız hata verir: hava servisi
 * erişilemezse polar bloğu yine de görünür (extras.py'nin "bir kaynak yoksa
 * diğerleri çalışmaya devam eder" dürüstlük deseni).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import {
  CloudSun, Sprout, Factory, AlertTriangle, Loader2, TrendingUp, Info, RefreshCw,
} from "lucide-react";

const fmt = (n, d = 1) =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : Number(n).toFixed(d);

const trDate = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
};

/** Sınıf → rozet rengi (mevcut badge-a..d dili). */
const MATURITY_BADGE = {
  olgun: "badge-a", "olgunlaşıyor": "badge-b", gelişme: "badge-c", erken: "badge-neutral",
};

function Stat({ label, value, unit, hint }) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-wider text-[var(--text-dim)]">{label}</div>
      <div className="text-lg font-display">
        {value}{unit && <span className="text-xs text-[var(--text-dim)] ml-0.5">{unit}</span>}
      </div>
    </div>
  );
}

function Block({ icon: Icon, title, subtitle, loading, error, children }) {
  return (
    <div className="border-t border-[var(--border)] pt-3 mt-3 first:border-0 first:pt-0 first:mt-0">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={15} className="text-[var(--primary)]" />
        <div className="font-medium text-sm">{title}</div>
        {subtitle && <span className="text-xs text-[var(--text-dim)]">· {subtitle}</span>}
        {loading && <Loader2 size={13} className="animate-spin text-[var(--text-dim)]" />}
      </div>
      {error ? (
        <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1.5 flex items-start gap-1.5">
          <AlertTriangle size={13} className="mt-px shrink-0" /> {error}
        </div>
      ) : children}
    </div>
  );
}

export default function ParcelDecisionPanel({ parcelId, crop = "pancar", planting = null }) {
  const [weather, setWeather] = useState({ loading: true });
  const [polar, setPolar] = useState({ loading: true });
  const [sowing, setSowing] = useState({ loading: true });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!parcelId) return;
    let alive = true;
    const fail = (e) => e?.response?.data?.detail || e?.message || "Veri alınamadı";

    setWeather({ loading: true }); setPolar({ loading: true }); setSowing({ loading: true });

    api.get(`/weather/parcels/${parcelId}`, { params: { crop } })
      .then((r) => alive && setWeather({ loading: false, data: r.data }))
      .catch((e) => alive && setWeather({ loading: false, error: fail(e) }));

    api.get(`/polar/parcels/${parcelId}`, { params: { crop } })
      .then((r) => alive && setPolar({ loading: false, data: r.data }))
      .catch((e) => alive && setPolar({ loading: false, error: fail(e) }));

    api.get(`/polar/parcels/${parcelId}/sowing-window`, { params: { crop } })
      .then((r) => alive && setSowing({ loading: false, data: r.data }))
      .catch((e) => alive && setSowing({ loading: false, error: fail(e) }));

    return () => { alive = false; };
  }, [parcelId, crop, reloadKey]);

  const w = weather.data;
  const wSum = w?.summary || {};
  const p = polar.data;
  const pol = p?.polar_tahmini;
  const mat = p?.olgunlasma;
  const win = p?.sokum_penceresi;
  const sw = sowing.data;

  return (
    <div className="card p-5" data-testid="parcel-decision-panel">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <div>
          <h3 className="font-display text-xl">Karar Paneli</h3>
          <p className="text-xs text-[var(--text-dim)]">
            Hava (Open-Meteo), ekim penceresi ve polar/söküm tahmini — canlı hesaplanır.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* "Hangi ürün ekili" — kullanıcının göremediğini söylediği bilgi. */}
          <span className="badge badge-neutral" data-testid="decision-crop">
            <Sprout size={11} className="inline mr-1" />
            {planting?.crop || planting?.urun || crop || "ürün bilinmiyor"}
            {planting?.planting_date ? ` · ekim ${trDate(planting.planting_date)}` : ""}
          </span>
          <button className="btn btn-ghost text-xs" onClick={() => setReloadKey((k) => k + 1)}>
            <RefreshCw size={13} /> Yenile
          </button>
        </div>
      </div>

      {/* ---------------- HAVA (Open-Meteo) ---------------- */}
      <Block icon={CloudSun} title="Hava & Su Dengesi"
             subtitle={w?.source ? `${w.source}${w.stale ? " (bayat)" : ""}` : null}
             loading={weather.loading} error={weather.error}>
        {w?.available === false ? (
          <div className="text-xs text-[var(--text-dim)]">{w.reason || "Hava verisi yok."}</div>
        ) : w ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="GDD (son 30 gün)" value={fmt(wSum.gdd_son_30_gun, 0)}
                    hint={`Taban sıcaklık ${w.base_temp_c} °C`} />
              <Stat label="GDD tahmin (16 gün)" value={fmt(wSum.gdd_tahmin_16_gun, 0)} />
              <Stat label="Etkili yağış (30 gün)" value={fmt(wSum.etkili_yagis_son_30_gun_mm)} unit="mm" />
              <Stat label="ET₀ (30 gün)" value={fmt(wSum.et0_son_30_gun_mm)} unit="mm" />
              <Stat label="Yağış tahmini" value={fmt(wSum.yagis_tahmin_mm)} unit="mm" />
              <Stat label="ET₀ tahmini" value={fmt(wSum.et0_tahmin_mm)} unit="mm" />
              <Stat label="En düşük (tahmin)" value={fmt(wSum.en_dusuk_sicaklik_tahmin)} unit="°C" />
              <Stat label="Don riskli gün" value={fmt(wSum.don_riski_gun_sayisi, 0)} />
            </div>
            {/* Su dengesi = etkili yağış − ET₀. Negatifse açık sulama ihtiyacı. */}
            {wSum.et0_son_30_gun_mm != null && wSum.etkili_yagis_son_30_gun_mm != null && (
              <div className="mt-2 text-xs">
                Son 30 gün su dengesi:{" "}
                <b className={wSum.etkili_yagis_son_30_gun_mm - wSum.et0_son_30_gun_mm < 0 ? "text-amber-300" : "text-[var(--primary)]"}>
                  {fmt(wSum.etkili_yagis_son_30_gun_mm - wSum.et0_son_30_gun_mm)} mm
                </b>
                <span className="text-[var(--text-dim)]"> (etkili yağış − ET₀; negatif = sulama açığı)</span>
              </div>
            )}
            {wSum.don_riski_gun_sayisi > 0 && (
              <div className="mt-2 text-xs text-amber-300 flex items-center gap-1.5">
                <AlertTriangle size={13} /> Önümüzdeki 16 günde {wSum.don_riski_gun_sayisi} gün don riski.
              </div>
            )}
          </>
        ) : null}
      </Block>

      {/* ---------------- EKİM PENCERESİ ---------------- */}
      <Block icon={Sprout} title="Ne Zaman Ekmeliyim?" subtitle="ekim penceresi"
             loading={sowing.loading} error={sowing.error}>
        {sw?.available === false ? (
          <div className="text-xs text-[var(--text-dim)]">{sw.reason || "Hava verisi olmadan hesaplanamaz."}</div>
        ) : sw ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Stat label="İlk uygun gün" value={trDate(sw.ilk_uygun_gun)} />
              <Stat label="En iyi gün (puan)" value={trDate(sw.en_iyi_gun)} />
              <Stat label="Uygun gün sayısı" value={fmt(sw.uygun_gun_sayisi, 0)} />
            </div>
            <div className="text-xs text-[var(--text-dim)] mt-2">{sw.oneri}</div>
            {/* İlk 10 günün uygunluk şeridi — neden uygun/uygun değil görünsün. */}
            {(sw.gunler || []).length > 0 && (
              <div className="flex gap-1 mt-2 flex-wrap">
                {sw.gunler.slice(0, 12).map((g) => (
                  <span key={g.tarih}
                        title={`${g.tarih} · toprak ${g.toprak_sicakligi_c} °C · 2 günlük yağış ${g.yagis_2gun_mm} mm${g.engeller.length ? "\n" + g.engeller.join("\n") : ""}`}
                        className={`px-1.5 py-0.5 rounded text-[10px] ${
                          g.uygun ? "bg-[var(--primary)] text-black" : "bg-[var(--surface-2)] text-[var(--text-dim)]"}`}>
                    {g.tarih.slice(5)}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : null}
      </Block>

      {/* ---------------- POLAR + SÖKÜM ---------------- */}
      <Block icon={Factory} title="Ne Zaman Sökmeliyim?" subtitle="polar & söküm penceresi"
             loading={polar.loading} error={polar.error}>
        {p?.available === false ? (
          <div className="text-xs text-[var(--text-dim)]">{p.reason || "Hesaplanamadı."}</div>
        ) : p ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="Beklenen polar" value={fmt(pol?.tahmin_polar, 2)} unit="%"
                    hint="Açıklanabilir ağırlıklı model" />
              <Stat label="Güven aralığı"
                    value={pol ? `${fmt(pol.alt_sinir, 1)}–${fmt(pol.ust_sinir, 1)}` : "—"} unit="%" />
              <Stat label="Olgunlaşma endeksi" value={fmt(mat?.endeks, 0)} unit="/100" />
              <Stat label="Söküme kalan" value={fmt(win?.kalan_gun, 0)} unit="gün" />
            </div>

            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {mat?.sinif && (
                <span className={`badge ${MATURITY_BADGE[mat.sinif] || "badge-neutral"}`}>{mat.sinif}</span>
              )}
              {win?.onerilen_baslangic && (
                <span className="text-xs">
                  Önerilen söküm: <b>{trDate(win.onerilen_baslangic)} – {trDate(win.onerilen_bitis)}</b>
                </span>
              )}
              {pol?.guven != null && (
                <span className="text-xs text-[var(--text-dim)]">model güveni %{Math.round(pol.guven * 100)}</span>
              )}
            </div>

            {win?.oneri && <div className="text-xs text-[var(--text-dim)] mt-1">{win.oneri}</div>}
            {win?.sebep && <div className="text-xs text-[var(--text-dim)] mt-1">{win.sebep}</div>}

            {(win?.engeller || []).length > 0 && (
              <div className="mt-2 text-xs text-amber-300">
                {win.engeller.map((e, i) => (
                  <div key={i} className="flex items-center gap-1.5"><AlertTriangle size={12} /> {e}</div>
                ))}
              </div>
            )}

            {/* Modelin AÇIKLANABİLİRLİĞİ — hangi girdi poları ne yönde etkiledi.
                Kara kutu bir tahmin göstermek yerine katkı dökümü veriliyor. */}
            {(pol?.katkilar || []).length > 0 && (
              <details className="mt-3">
                <summary className="text-xs cursor-pointer text-[var(--text-dim)] hover:text-[var(--text)] flex items-center gap-1.5">
                  <TrendingUp size={12} /> Tahmin nasıl oluştu? ({pol.katkilar.length} katkı)
                </summary>
                <div className="mt-2 flex flex-col gap-1">
                  {pol.katkilar.map((k, i) => (
                    <div key={i} className="flex items-center justify-between text-xs bg-[var(--surface-2)] rounded px-2 py-1">
                      <span>{k.etken || k.ad || k.kaynak || `Katkı ${i + 1}`}</span>
                      <span className={(k.katki ?? k.deger ?? 0) >= 0 ? "text-[var(--primary)]" : "text-amber-300"}>
                        {(k.katki ?? k.deger ?? 0) >= 0 ? "+" : ""}{fmt(k.katki ?? k.deger, 2)}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {(pol?.veri_bosluklari || []).length > 0 && (
              <div className="mt-2 text-[11px] text-[var(--text-dim)] flex items-start gap-1.5">
                <Info size={12} className="mt-px shrink-0" />
                Eksik girdiler tahmin aralığını genişletiyor: {pol.veri_bosluklari.join(", ")}
              </div>
            )}
          </>
        ) : null}
      </Block>
    </div>
  );
}
