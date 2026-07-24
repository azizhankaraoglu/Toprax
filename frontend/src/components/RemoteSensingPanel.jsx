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

  const [s2Busy, setS2Busy] = useState(false);
  const [s2Msg, setS2Msg] = useState("");

  const load = () => {
    api.get("/remote-sensing/providers/status").then((r) => setStatus(r.data)).catch(() => {});
    // Denetim Faz 5 — birincil NDVI grafiği/slider'ı EOSDA istatistiğine
    // dayanır (bilinçli tercih: iki farklı sağlayıcının NDVI serisini
    // birleştirmek yerine, mevcut çalışan grafik AYNEN korunur; Sentinel-2
    // sadece kendi görüntüsünü aynı zaman çizgisine "son bilinen görüntü"
    // deseniyle ekler — bkz. curImgS2 aşağıda).
    api.get(`/remote-sensing/parcels/${parcelId}/timeseries`).then((r) =>
      setStats((r.data.statistics || []).filter((s) => s.provider !== "sentinel2"))
    ).catch(() => setStats([]));
    api.get(`/remote-sensing/parcels/${parcelId}/images`).then((r) => setImages(r.data || [])).catch(() => setImages([]));
  };
  useEffect(load, [parcelId]);

  // En güncel istatistik dokümanının serisi (tarih artan sıralı).
  const series = useMemo(() => {
    const latest = stats[0];
    return (latest?.series || []).slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  }, [stats]);

  // Görüntüler tarihe göre sıralı — seçili tarihte görüntü YOKSA o tarihten
  // ÖNCEKİ en yeni görüntü gösterilir ("son bilinen görüntü"), aksi halde tek
  // bir tarih dışında hep "görüntü yok" görünürdü. EOSDA (sol) ve Sentinel-2
  // (sağ) görüntüleri `provider` alanına göre AYRI listelerdir.
  const sortedImages = useMemo(
    () => images.filter((im) => im.capture_date && im.stored_name && im.provider !== "sentinel2")
                .slice().sort((a, b) => (a.capture_date || "").localeCompare(b.capture_date || "")),
    [images]
  );
  const sortedImagesS2 = useMemo(
    () => images.filter((im) => im.capture_date && im.stored_name && im.provider === "sentinel2")
                .slice().sort((a, b) => (a.capture_date || "").localeCompare(b.capture_date || "")),
    [images]
  );

  const dates = series.map((s) => s.date);
  const cur = series[Math.min(idx, Math.max(0, series.length - 1))] || null;
  const curImg = useMemo(() => {
    if (!cur?.date) return null;
    let found = null;
    for (const im of sortedImages) {
      if ((im.capture_date || "") <= cur.date) found = im; else break;
    }
    return found || null;
  }, [cur, sortedImages]);
  const curImgS2 = useMemo(() => {
    if (!cur?.date) return null;
    let found = null;
    for (const im of sortedImagesS2) {
      if ((im.capture_date || "") <= cur.date) found = im; else break;
    }
    return found || null;
  }, [cur, sortedImagesS2]);
  const imgIsExact = curImg && curImg.capture_date === cur?.date;
  const imgIsExactS2 = curImgS2 && curImgS2.capture_date === cur?.date;

  // Slider EN GÜNCEL tarihte açılsın (uydu görüntüsü de en yeni tarihte olur).
  useEffect(() => {
    setIdx(Math.max(0, series.length - 1));
    setImgError(false); setInterp(null);
  }, [stats, series.length]);

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

  async function runSentinel2Fetch() {
    setS2Busy(true);
    setS2Msg("");
    try {
      const { data } = await api.post("/remote-sensing/sentinel2/fetch", { parcel_id: parcelId });
      setS2Msg(`Sentinel-2 görüntüsü güncellendi: ${data.queued ?? 0} görev kuyruğa alındı, ${data.processed ?? 0} işlendi.`);
      load();
    } catch (err) {
      setS2Msg(err.response?.data?.detail || "Sentinel-2 görüntüsü alınamadı.");
    } finally {
      setS2Busy(false);
    }
  }

  // Yerel diske kaydedilmiş PNG'yi (stored_name) kendi güvenli ucumuzdan sun.
  // (EOSDA'nın imzalı result_url'i geçici/çapraz-köken olduğundan doğrudan
  // kullanılmaz.)
  const imgSrc = curImg?.stored_name
    ? `${BACKEND_URL || ""}/api/remote-sensing/images/file/${curImg.stored_name}?token=${localStorage.getItem("token") || ""}`
    : null;
  const imgSrcS2 = curImgS2?.stored_name
    ? `${BACKEND_URL || ""}/api/remote-sensing/images/file/${curImgS2.stored_name}?token=${localStorage.getItem("token") || ""}`
    : null;

  return (
    <div className="card p-5 mb-4" data-testid="remote-sensing-panel">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Satellite size={18} className="text-[var(--primary)]" />
          <h3 className="font-display text-lg">Uzaktan Algılama (EOSDA + Sentinel-2)</h3>
          {status && (
            <span className={`badge ${status.is_real ? "badge-a" : "badge-neutral"}`}>
              {status.is_real ? "GERÇEK" : "MOCK"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runUpdate} disabled={busy} className="btn btn-primary text-xs" data-testid="rs-update">
            <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> {busy ? "Çalışıyor…" : "Uydu Analizini Güncelle"}
          </button>
          <button onClick={runSentinel2Fetch} disabled={s2Busy} className="btn btn-ghost text-xs" data-testid="rs-s2-fetch"
                  title="Sentinel-2 (Copernicus) — ücretsiz, ~5 günde bir yeni görüntü">
            <RefreshCw size={14} className={s2Busy ? "animate-spin" : ""} /> {s2Busy ? "Çalışıyor…" : "Yeni Görüntü Getir (Sentinel-2)"}
          </button>
        </div>
      </div>

      {status && !status.enabled && (
        <div className="text-[11px] text-amber-400 mb-3">
          EOSDA entegrasyonu pasif — Ayarlar › Entegrasyonlar › EOSDA'dan anahtar girip aktive edin (aktif olana kadar MOCK veriyle çalışır).
        </div>
      )}
      {msg && <div className="text-xs text-[var(--text-dim)] mb-3">{msg}</div>}
      {s2Msg && <div className="text-xs text-[var(--text-dim)] mb-3">{s2Msg}</div>}

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
              {/* Sol: EOSDA görüntüsü */}
              <div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider mb-1">EOSDA</div>
                <div className="aspect-video rounded-lg overflow-hidden border border-[var(--border)] flex items-center justify-center relative"
                     style={{ background: `${ndviColor(cur?.ndvi)}22` }}>
                  {imgSrc && !imgError ? (
                    <>
                      <img src={imgSrc} alt={curImg?.capture_date} className="w-full h-full object-cover" onError={() => setImgError(true)} />
                      <div className="absolute bottom-0 left-0 right-0 text-[10px] px-2 py-1 bg-black/60 text-white">
                        {imgIsExact ? `Uydu görüntüsü · ${curImg.capture_date}`
                                    : `Son bilinen görüntü · ${curImg.capture_date} (seçili tarih: ${cur?.date})`}
                        {curImg?.cloud_pct != null && ` · bulut %${curImg.cloud_pct}`}
                      </div>
                    </>
                  ) : (
                    <div className="text-center p-4">
                      <ImageIcon size={28} className="mx-auto mb-1" style={{ color: ndviColor(cur?.ndvi) }} />
                      <div className="text-xs text-[var(--text-dim)]">
                        {status && !status.is_real
                          ? "MOCK modda gerçek raster gelmez — EOSDA gerçek moda alınmalı"
                          : images.length === 0
                            ? "Bu parsel için henüz uydu görüntüsü indirilmedi — “Uydu Analizini Güncelle”ye basın (render ~1-2 dk sürer)."
                            : "Seçili tarihten önce görüntü yok — slider'ı sağa (daha yeni tarihe) çekin."}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Sağ: Sentinel-2 (Copernicus, ücretsiz, ~5 günde bir yenilenir) — NDVI renk haritası, 30 m tampon ile kırpılmış */}
              <div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider mb-1">Sentinel-2 · Copernicus</div>
                <div className="aspect-video rounded-lg overflow-hidden border border-[var(--border)] flex items-center justify-center relative bg-[var(--surface)]">
                  {imgSrcS2 ? (
                    <>
                      <img src={imgSrcS2} alt={curImgS2?.capture_date} className="w-full h-full object-cover" />
                      <div className="absolute bottom-0 left-0 right-0 text-[10px] px-2 py-1 bg-black/60 text-white">
                        {imgIsExactS2 ? `Sentinel-2 · ${curImgS2.capture_date}`
                                      : `Son bilinen görüntü · ${curImgS2.capture_date} (seçili tarih: ${cur?.date})`}
                        {curImgS2?.cloud_pct != null && ` · bulut %${curImgS2.cloud_pct}`}
                      </div>
                    </>
                  ) : (
                    <div className="text-center p-4">
                      <ImageIcon size={28} className="mx-auto mb-1 text-[var(--text-dim)]" />
                      <div className="text-xs text-[var(--text-dim)]">
                        Bu parsel için henüz Sentinel-2 görüntüsü yok — "Yeni Görüntü Getir (Sentinel-2)"ye basın.
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* O günkü değerler — Denetim Faz 5: grafiğin/görüntülerin ALTINA bilgi satırı olarak taşındı */}
            <div className="flex flex-wrap items-center gap-4 mt-3 pt-3 border-t border-[var(--border)]">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ background: ndviColor(cur?.ndvi) }} />
                <div className="font-display text-xl">NDVI {cur?.ndvi ?? "—"}</div>
                <span className="text-xs" style={{ color: ndviColor(cur?.ndvi) }}>{ndviLabel(cur?.ndvi)}</span>
              </div>
              {cur?.ndre != null && <div className="text-xs text-[var(--text-dim)]">NDRE: {cur.ndre}</div>}
              <div className="text-xs text-[var(--text-dim)] flex items-center gap-1">
                <CloudSun size={13} /> Bulut: %{cur?.cloud_pct ?? "—"}
              </div>
              {curImg?.satellite && <div className="text-xs text-[var(--text-dim)]">Uydu: {curImg.satellite}</div>}
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
