/**
 * RemoteSensingPanel — tekil parsel için Uzaktan Algılama (EOSDA) kartı.
 *
 * - Sağlayıcı durumu (GERÇEK/MOCK) + "Uydu Analizini Güncelle" (manuel sync:
 *   NDVI istatistiği + uydu görüntüsü tek çağrıda kuyruğa alınır).
 * - NDVI zaman serisi grafiği (tarih bazlı — geçmiş veriler saklanır).
 * - Gün-gün ZAMAN SLIDER'ı: her tarihteki NDVI (renk kodlu) + uydu görüntüsü
 *   (varsa) + bulut oranı; Oynat/Duraklat ile otomatik ilerler.
 * - Geçmiş analizler (güncelleme tarihleriyle).
 *
 * Backend: backend/remote_sensing/services.py (manual-sync / timeseries / images).
 */
import { useEffect, useMemo, useState } from "react";
import api, { BACKEND_URL } from "@/api";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Satellite, RefreshCw, Play, Pause, Image as ImageIcon, CloudSun, Brain } from "lucide-react";

const ndviColor = (v) => (v == null ? "#97a8a0" : v > 0.65 ? "#4ade80" : v > 0.45 ? "#fbbf24" : "#ef4444");
const ndviLabel = (v) => (v == null ? "—" : v > 0.65 ? "Sağlıklı gelişim" : v > 0.45 ? "İzlemeye değer" : "Stres altında");

export default function RemoteSensingPanel({ parcelId }) {
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState([]);
  const [images, setImages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [interp, setInterp] = useState(null);
  const [interpBusy, setInterpBusy] = useState(false);

  const load = () => {
    api.get("/remote-sensing/providers/status").then((r) => setStatus(r.data)).catch(() => {});
    api.get(`/remote-sensing/parcels/${parcelId}/timeseries`).then((r) => setStats(r.data.statistics || [])).catch(() => setStats([]));
    api.get(`/remote-sensing/parcels/${parcelId}/images`).then((r) => setImages(r.data || [])).catch(() => setImages([]));
  };
  useEffect(load, [parcelId]);

  // En güncel istatistik dokümanının serisi (tarih artan sıralı).
  const series = useMemo(() => {
    const latest = stats[0];
    return (latest?.series || []).slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  }, [stats]);

  const imageByDate = useMemo(() => {
    const m = {};
    images.forEach((im) => { if (im.capture_date) m[im.capture_date] = im; });
    return m;
  }, [images]);

  const dates = series.map((s) => s.date);
  const cur = series[Math.min(idx, Math.max(0, series.length - 1))] || null;
  const curImg = cur ? imageByDate[cur.date] : null;

  useEffect(() => { setIdx(0); setImgError(false); setInterp(null); }, [stats]);

  async function runInterpret() {
    setInterpBusy(true);
    setInterp(null);
    try {
      const { data } = await api.post(`/remote-sensing/parcels/${parcelId}/interpret`);
      setInterp(data);
    } catch (err) {
      setInterp({ error: err.response?.data?.detail || "Yorum üretilemedi." });
    } finally {
      setInterpBusy(false);
    }
  }
  useEffect(() => { setImgError(false); }, [idx]);

  useEffect(() => {
    if (!playing || dates.length < 2) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % dates.length), 1200);
    return () => clearInterval(t);
  }, [playing, dates.length]);

  async function runUpdate() {
    setBusy(true);
    setMsg("");
    try {
      const { data } = await api.post("/remote-sensing/manual-sync", {
        parcel_id: parcelId,
        task_types: ["statistics", "download"],   // NDVI istatistiği + true-color uydu görüntüsü (gerçek EOSDA)
        indices: ["ndvi"],
      });
      setMsg(`Analiz çalıştırıldı: ${data.queued ?? 0} görev kuyruğa alındı, ${data.processed ?? 0} işlendi.`);
      load();
    } catch (err) {
      setMsg(err.response?.data?.detail || "Analiz başlatılamadı (EOSDA yetkisi/entegrasyonu gerekli).");
    } finally {
      setBusy(false);
    }
  }

  // Yerel diske kaydedilmiş PNG'yi (stored_name) kendi güvenli ucumuzdan sun.
  // (EOSDA'nın imzalı result_url'i geçici/çapraz-köken olduğundan doğrudan
  // kullanılmaz.)
  const imgSrc = curImg?.stored_name
    ? `${BACKEND_URL || ""}/api/remote-sensing/images/file/${curImg.stored_name}?token=${localStorage.getItem("token") || ""}`
    : null;

  return (
    <div className="card p-5 mb-4" data-testid="remote-sensing-panel">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Satellite size={18} className="text-[var(--primary)]" />
          <h3 className="font-display text-lg">Uzaktan Algılama (EOSDA)</h3>
          {status && (
            <span className={`badge ${status.is_real ? "badge-a" : "badge-neutral"}`}>
              {status.is_real ? "GERÇEK" : "MOCK"}
            </span>
          )}
        </div>
        <button onClick={runUpdate} disabled={busy} className="btn btn-primary text-xs" data-testid="rs-update">
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> {busy ? "Çalışıyor…" : "Uydu Analizini Güncelle"}
        </button>
      </div>

      {status && !status.enabled && (
        <div className="text-[11px] text-amber-400 mb-3">
          EOSDA entegrasyonu pasif — Ayarlar › Entegrasyonlar › EOSDA'dan anahtar girip aktive edin (aktif olana kadar MOCK veriyle çalışır).
        </div>
      )}
      {msg && <div className="text-xs text-[var(--text-dim)] mb-3">{msg}</div>}

      {series.length === 0 ? (
        <div className="text-sm text-[var(--text-dim)] py-6 text-center border border-dashed border-[var(--border)] rounded-lg">
          Bu parsel için henüz uzaktan algılama verisi yok.<br />
          <span className="text-xs">"Uydu Analizini Güncelle" ile NDVI istatistiği ve uydu görüntüsü çekin.</span>
        </div>
      ) : (
        <>
          {/* NDVI zaman serisi grafiği */}
          <div className="mb-4">
            <div className="text-xs text-[var(--text-dim)] mb-1">NDVI Zaman Serisi ({series.length} tarih)</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={series} onClick={(e) => { if (e && e.activeTooltipIndex != null) setIdx(e.activeTooltipIndex); }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2326" />
                <XAxis dataKey="date" stroke="#97a8a0" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 1]} stroke="#97a8a0" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }} />
                <Line type="monotone" dataKey="ndvi" stroke="#4ade80" strokeWidth={2} dot={{ r: 2 }} name="NDVI" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Gün-gün zaman slider'ı */}
          <div className="bg-[var(--surface-2)] rounded-lg p-4">
            <div className="flex items-center gap-3 mb-3">
              <button onClick={() => setPlaying((p) => !p)} className="btn btn-ghost text-xs px-2" data-testid="rs-play">
                {playing ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <input
                type="range" min={0} max={Math.max(0, series.length - 1)} value={idx}
                onChange={(e) => { setIdx(Number(e.target.value)); setPlaying(false); }}
                className="flex-1" data-testid="rs-slider"
              />
              <div className="text-xs font-mono text-[var(--text-dim)] w-24 text-right">{cur?.date}</div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Görüntü / placeholder */}
              <div className="aspect-video rounded-lg overflow-hidden border border-[var(--border)] flex items-center justify-center relative"
                   style={{ background: `${ndviColor(cur?.ndvi)}22` }}>
                {imgSrc && !imgError ? (
                  <img src={imgSrc} alt={cur?.date} className="w-full h-full object-cover" onError={() => setImgError(true)} />
                ) : (
                  <div className="text-center p-4">
                    <ImageIcon size={28} className="mx-auto mb-1" style={{ color: ndviColor(cur?.ndvi) }} />
                    <div className="text-xs text-[var(--text-dim)]">
                      {curImg
                        ? (status && !status.is_real
                            ? "MOCK modda gerçek raster gelmez — EOSDA gerçek moda alınmalı"
                            : "Bu tarih için görüntü indirilemedi")
                        : "Bu tarihte kayıtlı uydu görüntüsü yok"}
                    </div>
                  </div>
                )}
              </div>

              {/* O günkü değerler */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: ndviColor(cur?.ndvi) }} />
                  <div className="font-display text-2xl">NDVI {cur?.ndvi ?? "—"}</div>
                  <span className="text-xs" style={{ color: ndviColor(cur?.ndvi) }}>{ndviLabel(cur?.ndvi)}</span>
                </div>
                {cur?.ndre != null && <div className="text-xs text-[var(--text-dim)]">NDRE: {cur.ndre}</div>}
                <div className="text-xs text-[var(--text-dim)] flex items-center gap-1">
                  <CloudSun size={13} /> Bulut: %{cur?.cloud_pct ?? "—"}
                </div>
                {curImg?.satellite && <div className="text-xs text-[var(--text-dim)]">Uydu: {curImg.satellite}</div>}
              </div>
            </div>
          </div>

          {/* AI Yorumu — NDVI ne anlama geliyor + gerekçeli durum */}
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-[var(--text-dim)] flex items-center gap-1"><Brain size={13}/> AI Yorumu</div>
              <button onClick={runInterpret} disabled={interpBusy} className="btn btn-primary text-xs" data-testid="rs-interpret">
                <Brain size={13}/> {interpBusy ? "Yorumlanıyor…" : "AI ile Yorumla"}
              </button>
            </div>
            {interp && !interp.error && (
              <div className="bg-[var(--surface-2)] rounded-lg p-3 text-sm leading-relaxed">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`badge ${interp.ai_powered ? "badge-a" : "badge-neutral"}`}>
                    {interp.ai_powered ? "AI" : "Kural-bazlı"}
                  </span>
                  {interp.metrics && (
                    <span className="text-xs text-[var(--text-dim)]">
                      ort NDVI {interp.metrics.avg} · son {interp.metrics.latest_ndvi} · {interp.metrics.points} tarih
                    </span>
                  )}
                </div>
                <p className="whitespace-pre-line">{interp.interpretation}</p>
                {!interp.ai_powered && interp.ai_error && (
                  <p className="text-[10px] text-amber-400 mt-2">
                    AI yanıtı alınamadı ({interp.ai_error}) — kural-bazlı yorum gösteriliyor.
                  </p>
                )}
              </div>
            )}
            {interp?.error && <div className="text-xs text-red-400">{interp.error}</div>}
          </div>

          {/* Geçmiş analizler — güncelleme tarihleriyle */}
          <div className="mt-4">
            <div className="text-xs text-[var(--text-dim)] mb-1">Geçmiş Analizler ({stats.length})</div>
            <div className="space-y-1 max-h-32 overflow-y-auto scrollbar">
              {stats.map((s) => (
                <div key={s.id} className="flex items-center justify-between text-xs p-2 bg-[var(--surface-2)] rounded">
                  <span>{new Date(s.created_at).toLocaleString("tr-TR")}</span>
                  <span className="text-[var(--text-dim)]">
                    {s.index?.toUpperCase() || "NDVI"} · ort {s.avg} · {s.count} nokta
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
