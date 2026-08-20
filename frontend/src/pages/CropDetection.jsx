/**
 * UYDU İLE ÜRÜN TANIMA — 2026-08-19
 *
 * Backend: `backend/crop_classification.py`. Kullanıcının iki somut sorusuna
 * birebir karşılık gelen iki sekme + bir eğitim sekmesi:
 *
 *   1. "il/ilçe/mahalle verdiğimde buradaki tarlalarda hangi bitkiler ekili?"
 *   2. "bölge sınırı çizdiğim alanlarda buğday ekili tarlaları işaretle"
 *   3. "manuel olarak eğitebilirim — uydu görüntüsü ve etiketi ekleyebilirim"
 *
 * Yöntem fenolojik NDVI imza eşleştirmesidir; eğitilmiş bir ML modeli DEĞİLDİR
 * ve ekran bunu açıkça yazar. Güven yüzdesi ve alternatif ürünler HER ZAMAN
 * gösterilir — "kesin ürün" iddiası edilmez.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, Polygon, Popup } from "react-leaflet";
import api from "@/api";
import { MapDrawTools } from "@/components/MapDrawTools";
import { BASEMAPS, getStoredBasemap, storeBasemap } from "@/lib/basemaps";
import {
  Sprout, Search, MapIcon, GraduationCap, Loader2, AlertTriangle, Info,
  Trash2, RefreshCw, Target, CheckCircle2, Wand2,
} from "lucide-react";

const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(", ");
  return e?.message || "Bilinmeyen hata";
};

const pct = (v) => (v === null || v === undefined ? "—" : `%${Math.round(v * 100)}`);

/** Güven rozeti — düşük güveni gizlemek yerine görünür kılar. */
function ConfidenceBadge({ value }) {
  if (value === null || value === undefined) return <span className="badge badge-neutral">—</span>;
  const cls = value >= 0.7 ? "badge-a" : value >= 0.45 ? "badge-b" : value >= 0.25 ? "badge-c" : "badge-d";
  return <span className={`badge ${cls}`}>{pct(value)}</span>;
}

export default function CropDetection() {
  const [tab, setTab] = useState("bolge");
  const [meta, setMeta] = useState(null);
  const [msg, setMsg] = useState(null);
  const flash = (kind, text) => { setMsg({ kind, text }); setTimeout(() => setMsg(null), 7000); };

  useEffect(() => {
    api.get("/crop-classification/crops").then((r) => setMeta(r.data)).catch(() => {});
  }, []);

  return (
    <div className="p-8 max-w-[1500px]" data-testid="crop-detection-page">
      <header className="mb-5">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">UYDU ANALİZİ</div>
        <h1 className="font-display text-4xl flex items-center gap-2">
          <Sprout size={28} /> Ürün Tanıma
        </h1>
        <p className="text-[var(--text-dim)] text-sm mt-1 max-w-3xl">
          Uydu NDVI zaman serisinden hangi tarlada ne ekili olduğunu tahmin eder.
          Her ürünün kendine özgü bir yeşerme/hasat takvimi (fenolojik imza) vardır;
          motor gözlenen eğriyi bu imzalarla karşılaştırır.
        </p>
      </header>

      {msg && (
        <div className={`card p-3 mb-4 text-sm ${msg.kind === "ok" ? "text-[var(--primary)]" : "text-red-400"}`}>
          {msg.text}
        </div>
      )}

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <button onClick={() => setTab("bolge")} data-testid="tab-bolge"
                className={`btn text-sm ${tab === "bolge" ? "btn-primary" : "btn-ghost"}`}>
          <Search size={14} /> Bölgede Ne Ekili?
        </button>
        <button onClick={() => setTab("alan")} data-testid="tab-alan"
                className={`btn text-sm ${tab === "alan" ? "btn-primary" : "btn-ghost"}`}>
          <MapIcon size={14} /> Alanı Tara
        </button>
        <button onClick={() => setTab("egitim")} data-testid="tab-egitim"
                className={`btn text-sm ${tab === "egitim" ? "btn-primary" : "btn-ghost"}`}>
          <GraduationCap size={14} /> Eğitim & Doğruluk
        </button>
      </div>

      {tab === "bolge" && <BolgeTab meta={meta} flash={flash} />}
      {tab === "alan" && <AlanTab meta={meta} flash={flash} />}
      {tab === "egitim" && <EgitimTab meta={meta} flash={flash} />}

      <div className="text-[11px] text-[var(--text-dim)] mt-4 flex items-start gap-1.5">
        <Info size={12} className="mt-px shrink-0" />
        Bu bir <b className="mx-1">kural tabanlı imza eşleştirmesidir</b>, eğitilmiş bir
        ML modeli değildir. Güven düşükse alternatif ürünler gösterilir — kararı
        siz verirsiniz. İmzalar bölgeye göre kayar; "Eğitim &amp; Doğruluk" sekmesinden
        kendi verinizle kalibre edebilirsiniz.
      </div>
    </div>
  );
}

/* =====================================================================
   SEKME 1 — BÖLGEDE NE EKİLİ
   ===================================================================== */
function BolgeTab({ meta, flash }) {
  const nav = useNavigate();
  const [il, setIl] = useState("");
  const [ilce, setIlce] = useState("");
  const [mahalle, setMahalle] = useState("");
  const [limit, setLimit] = useState(25);
  const [opts, setOpts] = useState({ il: [], ilce: [], mahalle: [] });
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState(null);

  // Parsellerin GERÇEK il/ilçe/mahalle değerleri — Parcels.jsx'in kullandığı
  // aynı uç (yeni bir kaynak icat edilmedi).
  useEffect(() => {
    api.get("/parcels/filter-options")
      .then((r) => setOpts({
        il: r.data.il || [], ilce: r.data.ilce || [], mahalle: r.data.mahalle || [],
        ilceByIl: r.data.ilceByIl, mahalleByIlce: r.data.mahalleByIlce,
      }))
      .catch(() => {});
  }, []);

  const ilceList = useMemo(() => {
    if (il && opts.ilceByIl) return opts.ilceByIl[il] || [];
    return opts.ilce;
  }, [il, opts]);
  const mahalleList = useMemo(() => {
    if (ilce && opts.mahalleByIlce) return opts.mahalleByIlce[ilce] || [];
    return opts.mahalle;
  }, [ilce, opts]);

  async function run() {
    if (!il && !ilce && !mahalle) return flash("err", "En az il, ilçe veya mahalle seçin.");
    setBusy(true); setData(null);
    try {
      const r = await api.post("/crop-classification/parcels", {
        il: il || null, ilce: ilce || null, mahalle: mahalle || null, limit,
      });
      setData(r.data);
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  return (
    <>
      <div className="card p-4 mb-4">
        <div className="grid md:grid-cols-5 gap-3 items-end">
          <label className="text-xs">İl
            <select className="input w-full mt-1" value={il}
                    onChange={(e) => { setIl(e.target.value); setIlce(""); setMahalle(""); }}>
              <option value="">Seçin…</option>
              {opts.il.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="text-xs">İlçe
            <select className="input w-full mt-1" value={ilce}
                    onChange={(e) => { setIlce(e.target.value); setMahalle(""); }}>
              <option value="">Tümü</option>
              {ilceList.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="text-xs">Mahalle / Köy
            <select className="input w-full mt-1" value={mahalle}
                    onChange={(e) => setMahalle(e.target.value)}>
              <option value="">Tümü</option>
              {mahalleList.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="text-xs">Parsel sayısı
            <select className="input w-full mt-1" value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}>
              {[10, 25, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={run} disabled={busy} data-testid="bolge-run">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />} Analiz Et
          </button>
        </div>
        <p className="text-[11px] text-[var(--text-dim)] mt-2">
          Her parsel için uydu zaman serisi işlenir — parsel sayısı arttıkça süre uzar.
        </p>
      </div>

      {busy && (
        <div className="card p-6 text-center text-sm text-[var(--text-dim)]">
          <Loader2 size={18} className="animate-spin inline mr-2" />
          Uydu serileri çekiliyor ve fenolojik imzalarla karşılaştırılıyor…
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[["İncelenen Parsel", `${data.kapsam.islenen} / ${data.kapsam.toplam}`],
              ["Tespit Edilen Ürün", data.dagilim.length],
              ["Beyan Uyuşmazlığı", data.uyusmazlik_sayisi],
              ["Sezon", data.season]].map(([l, v]) => (
              <div key={l} className="card p-4">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{l}</div>
                <div className="font-display text-2xl mt-1">{v}</div>
              </div>
            ))}
          </div>

          {data.dagilim.length > 0 && (
            <div className="card p-5 mb-4">
              <h3 className="font-display text-lg mb-3">Ürün Dağılımı</h3>
              <div className="flex flex-col gap-2">
                {data.dagilim.map((d) => {
                  const total = data.dagilim.reduce((a, b) => a + b.parsel_sayisi, 0);
                  const w = (d.parsel_sayisi / total) * 100;
                  return (
                    <div key={d.urun}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-sm inline-block"
                                style={{ background: d.renk || "#888" }} />
                          {d.label}
                        </span>
                        <span className="text-[var(--text-dim)]">{d.parsel_sayisi} parsel</span>
                      </div>
                      <div className="h-2 rounded bg-[var(--surface-2)] overflow-hidden">
                        <div className="h-full" style={{ width: `${w}%`, background: d.renk || "#888" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {data.uyusmazlik_sayisi > 0 && (
            <div className="card p-3 mb-4 text-xs text-amber-300 flex items-start gap-2">
              <AlertTriangle size={14} className="mt-px shrink-0" />
              <span>
                <b>{data.uyusmazlik_sayisi} parselde beyan ile uydu tahmini uyuşmuyor.</b>{" "}
                Bu bir denetim sinyalidir — ama düşük güvenli tahminler yanılabilir,
                sahada doğrulanmadan işlem yapmayın.
              </span>
            </div>
          )}

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-3">Parsel</th><th className="p-3">Konum</th>
                  <th className="p-3">Uydu Tahmini</th><th className="p-3">Güven</th>
                  <th className="p-3">Beyan</th><th className="p-3">Alternatif</th><th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {data.sonuclar.map((s) => (
                  <tr key={s.parcel_id}
                      className={`border-b border-[var(--border)] ${s.uyusmazlik ? "bg-amber-500/5" : ""}`}>
                    <td className="p-3">{s.parsel || s.parcel_id?.slice(0, 8)}</td>
                    <td className="p-3 text-[var(--text-dim)] text-xs">
                      {[s.ilce, s.mahalle].filter(Boolean).join(" / ") || "—"}
                    </td>
                    <td className="p-3">
                      {s.yetersiz_veri ? (
                        <span className="text-xs text-[var(--text-dim)]" title={s.sebep}>
                          uydu verisi yetersiz
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5">
                          <span className="w-2.5 h-2.5 rounded-sm inline-block"
                                style={{ background: s.renk || "#888" }} />
                          {s.tahmin_label}
                        </span>
                      )}
                    </td>
                    <td className="p-3"><ConfidenceBadge value={s.yetersiz_veri ? null : s.guven} /></td>
                    <td className="p-3 text-xs">
                      {s.beyan || "—"}
                      {s.uyusmazlik && <AlertTriangle size={12} className="inline ml-1 text-amber-400" />}
                    </td>
                    <td className="p-3 text-xs text-[var(--text-dim)]">
                      {(s.alternatifler || []).map((a) => a.label).join(", ") || "—"}
                    </td>
                    <td className="p-3 text-right">
                      <button className="btn btn-ghost text-xs"
                              onClick={() => nav(`/parseller/${s.parcel_id}`)}>Parsel →</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

/* =====================================================================
   SEKME 2 — ALANI TARA (kayıtsız alanlar)
   ===================================================================== */
function AlanTab({ meta, flash }) {
  const [geometry, setGeometry] = useState(null);
  const [crop, setCrop] = useState("");
  const [cellM, setCellM] = useState(200);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState(null);
  const [basemapKey, setBasemapKey] = useState(() => getStoredBasemap("crop"));

  const base = BASEMAPS[basemapKey] || BASEMAPS.hibrit;

  async function run() {
    if (!geometry) return flash("err", "Önce haritada bir alan çizin.");
    setBusy(true); setData(null);
    try {
      const r = await api.post("/crop-classification/area",
                               { geometry, crop: crop || null, cell_m: cellM });
      setData(r.data);
      if (r.data.uyari) flash("err", r.data.uyari);
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  return (
    <>
      <div className="card p-4 mb-4">
        <div className="grid md:grid-cols-4 gap-3 items-end">
          <label className="text-xs">Aranan Ürün
            <select className="input w-full mt-1" value={crop} onChange={(e) => setCrop(e.target.value)}>
              <option value="">Tümünü göster</option>
              {(meta?.crops || []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </label>
          <label className="text-xs">Hücre Boyutu
            <select className="input w-full mt-1" value={cellM} onChange={(e) => setCellM(Number(e.target.value))}>
              {[100, 200, 300, 500].map((n) => <option key={n} value={n}>{n} m</option>)}
            </select>
          </label>
          <label className="text-xs">Harita Altlığı
            <select className="input w-full mt-1" value={basemapKey}
                    onChange={(e) => { setBasemapKey(e.target.value); storeBasemap("crop", e.target.value); }}>
              {Object.entries(BASEMAPS).map(([k, b]) => <option key={k} value={k}>{b.label}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={run} disabled={busy || !geometry}
                  data-testid="alan-run">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Target size={15} />} Alanı Tara
          </button>
        </div>
        <p className="text-[11px] text-[var(--text-dim)] mt-2">
          Haritadaki çizim aracıyla bir alan belirleyin — kayıtlı parsel olması
          <b> gerekmez</b>. Alan ızgaraya bölünüp her hücre ayrı sınıflandırılır.
          {geometry && <span className="text-[var(--primary)]"> · Alan çizildi ✓</span>}
        </p>
      </div>

      <div className="card overflow-hidden relative mb-4" style={{ height: 520 }}>
        <MapContainer center={[38.0, 32.7]} zoom={11} style={{ height: "100%", width: "100%" }}>
          <TileLayer key={basemapKey} url={base.url} attribution={base.attribution} />
          {base.overlay && <TileLayer key={`${basemapKey}-ov`} url={base.overlay} />}
          <MapDrawTools mode="select" onCreated={(g) => setGeometry(g)} />

          {/* Sınıflandırılan hücreler */}
          {(data?.hucreler || []).map((c, i) => (
            <Polygon key={i}
                     positions={c.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                     pathOptions={{
                       color: c.renk || "#888",
                       fillColor: c.renk || "#888",
                       fillOpacity: c.yetersiz_veri ? 0.06 : 0.15 + 0.45 * (c.guven || 0),
                       weight: 1,
                     }}>
              <Popup>
                <div style={{ minWidth: 160 }}>
                  <b>{c.tahmin_label || "Belirlenemedi"}</b><br />
                  {c.yetersiz_veri
                    ? <span style={{ fontSize: 11 }}>Yeterli uydu gözlemi yok</span>
                    : <span style={{ fontSize: 11 }}>Güven: {pct(c.guven)}</span>}
                </div>
              </Popup>
            </Polygon>
          ))}
        </MapContainer>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[["Üretilen Hücre", data.kapsam.hucre_sayisi],
              ["İşaretlenen", data.kapsam.isaretlenen],
              ["Veri Yetersiz", data.kapsam.yetersiz_veri_hucre],
              ["Hücre Boyutu", `${data.kapsam.hucre_metre} m`]].map(([l, v]) => (
              <div key={l} className="card p-4">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{l}</div>
                <div className="font-display text-2xl mt-1">{v}</div>
              </div>
            ))}
          </div>

          {data.kapsam.truncated && (
            <div className="card p-3 mb-4 text-xs text-amber-300 flex items-center gap-2">
              <AlertTriangle size={14} />
              Alan çok büyük — hücre sayısı {data.kapsam.ust_sinir} ile sınırlandı
              (uydu kotası koruması). Daha küçük bir alan çizin veya hücre boyutunu büyütün.
            </div>
          )}

          {data.uyari && (
            <div className="card p-3 mb-4 text-xs text-amber-300 flex items-start gap-2">
              <AlertTriangle size={14} className="mt-px shrink-0" /> {data.uyari}
            </div>
          )}

          {data.dagilim.length > 0 && (
            <div className="card p-5">
              <h3 className="font-display text-lg mb-3">
                Bulunan Ürünler {data.filtre_urun && <span className="text-sm text-[var(--text-dim)]">(filtre: {data.filtre_urun})</span>}
              </h3>
              <div className="flex flex-wrap gap-2">
                {data.dagilim.map((d) => (
                  <span key={d.urun} className="flex items-center gap-1.5 text-sm bg-[var(--surface-2)] rounded px-2.5 py-1">
                    <span className="w-3 h-3 rounded-sm inline-block" style={{ background: d.renk || "#888" }} />
                    {d.label}: <b>{d.hucre_sayisi}</b> hücre
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-[var(--text-dim)] mt-3">{data.not}</p>
            </div>
          )}
        </>
      )}
    </>
  );
}

/* =====================================================================
   SEKME 3 — EĞİTİM & DOĞRULUK
   ===================================================================== */
function EgitimTab({ meta, flash }) {
  const [samples, setSamples] = useState([]);
  const [acc, setAcc] = useState(null);
  const [accBefore, setAccBefore] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ parcel_id: "", crop_label: "", season: new Date().getFullYear(), note: "" });

  const load = () => {
    api.get("/crop-classification/samples", { params: { limit: 500 } })
      .then((r) => setSamples(r.data || [])).catch(() => {});
    api.get("/crop-classification/accuracy").then((r) => setAcc(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function addSample() {
    if (!form.parcel_id.trim() || !form.crop_label) return flash("err", "Parsel ID ve ürün zorunlu.");
    setBusy(true);
    try {
      await api.post("/crop-classification/samples", {
        parcel_id: form.parcel_id.trim(), crop_label: form.crop_label,
        season: Number(form.season), note: form.note || null,
      });
      flash("ok", "Etiketli örnek eklendi.");
      setForm({ ...form, parcel_id: "", note: "" });
      load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function fromPlantings() {
    setBusy(true);
    try {
      const r = await api.post("/crop-classification/samples/from-plantings", null,
                               { params: { season: form.season, limit: 500 } });
      flash("ok", `${r.data.created} örnek üretildi · ${r.data.skipped_no_series} parsel uydu serisi olmadığı için atlandı · ${r.data.skipped_existing} zaten vardı.`);
      load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function calibrate() {
    setBusy(true);
    setAccBefore(acc);                       // öncesi/sonrası kıyaslaması için
    try {
      const r = await api.post("/crop-classification/calibrate");
      const g = r.data.guncellenen || [];
      const a = r.data.atlanan || [];
      flash(g.length ? "ok" : "err",
            g.length
              ? `${g.length} ürünün imzası kalibre edildi: ${g.map((x) => x.urun).join(", ")}`
              : `Hiçbir ürün kalibre edilemedi. ${a.map((x) => `${x.urun}: ${x.sebep}`).join(" · ")}`);
      load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function removeSample(s) {
    if (!window.confirm("Bu etiketli örnek silinsin mi?")) return;
    try { await api.delete(`/crop-classification/samples/${s.id}`); load(); }
    catch (e) { flash("err", errText(e)); }
  }

  return (
    <>
      <div className="card p-4 mb-4">
        <h3 className="font-display text-lg mb-1">Modeli Eğit</h3>
        <p className="text-xs text-[var(--text-dim)] mb-3">
          İmzalar bölgeye göre kayar. Gerçek, doğrulanmış örnekler ekledikçe motor
          sizin koşullarınıza uyum sağlar. Kod varsayılanları korunur — kalibrasyon
          <b> geri alınabilir</b> (Form Yönetimi &gt; Sabit Katalogları &gt; Varsayılana Döndür).
        </p>
        <div className="grid md:grid-cols-5 gap-3 items-end">
          <label className="text-xs md:col-span-2">Parsel ID
            <input className="input w-full mt-1" value={form.parcel_id}
                   placeholder="parsel kimliği"
                   onChange={(e) => setForm({ ...form, parcel_id: e.target.value })} />
          </label>
          <label className="text-xs">Gerçek Ürün
            <select className="input w-full mt-1" value={form.crop_label}
                    onChange={(e) => setForm({ ...form, crop_label: e.target.value })}>
              <option value="">Seçin…</option>
              {(meta?.crops || []).map((c) => <option key={c.key} value={c.label}>{c.label}</option>)}
            </select>
          </label>
          <label className="text-xs">Sezon
            <input className="input w-full mt-1" type="number" value={form.season}
                   onChange={(e) => setForm({ ...form, season: e.target.value })} />
          </label>
          <button className="btn btn-primary" onClick={addSample} disabled={busy}>
            <CheckCircle2 size={14} /> Örnek Ekle
          </button>
        </div>
        <div className="flex gap-2 mt-3 flex-wrap">
          <button className="btn btn-ghost text-xs" onClick={fromPlantings} disabled={busy}>
            <RefreshCw size={14} /> Beyanlardan Örnek Üret
          </button>
          <button className="btn btn-ghost text-xs" onClick={calibrate} disabled={busy}>
            <Wand2 size={14} /> İmzaları Kalibre Et
          </button>
          {busy && <Loader2 size={16} className="animate-spin text-[var(--text-dim)] self-center" />}
        </div>
      </div>

      {/* ---- DOĞRULUK ---- */}
      {acc && (
        <div className="card p-5 mb-4">
          <h3 className="font-display text-lg mb-3">Doğruluk</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
            {[["Doğruluk", acc.dogruluk_yuzde !== null ? `%${acc.dogruluk_yuzde}` : "—"],
              ["Değerlendirilen", acc.degerlendirilen],
              ["Doğru / Yanlış", `${acc.dogru} / ${acc.yanlis}`],
              ["Atlanan", acc.atlanan]].map(([l, v]) => (
              <div key={l}>
                <div className="text-[10px] uppercase tracking-wider text-[var(--text-dim)]">{l}</div>
                <div className="font-display text-2xl">{v}</div>
              </div>
            ))}
          </div>
          {accBefore && accBefore.dogruluk_yuzde !== null && acc.dogruluk_yuzde !== null && (
            <div className="text-sm mb-2">
              Kalibrasyon öncesi: <b>%{accBefore.dogruluk_yuzde}</b> → sonrası:{" "}
              <b>%{acc.dogruluk_yuzde}</b>{" "}
              <span className={acc.dogruluk_yuzde >= accBefore.dogruluk_yuzde ? "text-[var(--primary)]" : "text-amber-300"}>
                ({(acc.dogruluk_yuzde - accBefore.dogruluk_yuzde >= 0 ? "+" : "")}
                {(acc.dogruluk_yuzde - accBefore.dogruluk_yuzde).toFixed(1)} puan)
              </span>
            </div>
          )}
          <p className="text-[11px] text-[var(--text-dim)]">{acc.not}</p>

          {Object.keys(acc.karisiklik_matrisi || {}).length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
                Karışıklık Matrisi (gerçek → tahmin)
              </div>
              <table className="text-xs">
                <tbody>
                  {Object.entries(acc.karisiklik_matrisi).map(([gercek, tahminler]) => (
                    <tr key={gercek}>
                      <td className="p-1.5 font-medium pr-3">{gercek}</td>
                      {Object.entries(tahminler).map(([t, n]) => (
                        <td key={t} className={`p-1.5 ${t === gercek ? "text-[var(--primary)]" : "text-amber-300"}`}>
                          {t}: {n}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ---- ÖRNEK LİSTESİ ---- */}
      <div className="card overflow-x-auto">
        <div className="p-3 border-b border-[var(--border)] font-display text-lg">
          Etiketli Örnekler ({samples.length})
        </div>
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)]">
            <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
              <th className="p-3">Ürün</th><th className="p-3">Sezon</th>
              <th className="p-3">Parsel</th><th className="p-3">Gözlem</th>
              <th className="p-3">Kaynak</th><th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {samples.length === 0 && (
              <tr><td colSpan={6} className="p-5 text-sm text-[var(--text-dim)]">
                Henüz etiketli örnek yok. "Beyanlardan Örnek Üret" ile mevcut ekim
                kayıtlarınızdan toplu üretebilirsiniz.
              </td></tr>
            )}
            {samples.map((s) => (
              <tr key={s.id} className="border-b border-[var(--border)]">
                <td className="p-3">{s.crop_label}</td>
                <td className="p-3">{s.season}</td>
                <td className="p-3 text-xs text-[var(--text-dim)]">
                  {s.parcel_id ? s.parcel_id.slice(0, 8) : "çizilen alan"}
                </td>
                <td className="p-3">{(s.ndvi_series || []).length}</td>
                <td className="p-3">
                  <span className={`badge ${s.kaynak === "manuel" ? "badge-a" : "badge-neutral"}`}>
                    {s.kaynak}
                  </span>
                </td>
                <td className="p-3 text-right">
                  <button className="btn btn-ghost text-xs text-red-400" onClick={() => removeSample(s)}>
                    <Trash2 size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
