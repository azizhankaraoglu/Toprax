/**
 * HASAT — söküm planı (polar odaklı) + kampanya lojistiği.
 *
 * Backend: backend/harvest_logistics.py. Çizelge CANLI hesaplanır (kaydedilmez);
 * kabul edilen randevular mevcut `appointments` koleksiyonuna yazılır.
 *
 * **2026-08-19 yeniden düzeni (kullanıcı isteği):** *"Hasat kampanya
 * lojistiğinin adını Hasat olarak değiştirip sadece polara uygun olarak söküm
 * tarafını öne çıkaralım. Lojistiği ayrı bir modül yapalım."*
 *
 * Ekran ADI "Hasat" oldu ve İKİ sekmeye bölündü:
 *   - **Söküm Planı** (varsayılan) — polar tahmini merkezde: polar KPI'ları,
 *     polara göre sıralama, düşük/yüksek polar vurgusu.
 *   - **Kampanya Lojistiği** — fabrika kapasitesi, kantar ayarları, haftalık
 *     yük dağılımı ve randevulaştırma.
 *
 * Sekme AYRI BİR SAYFAYA bölünmedi çünkü ikisi de AYNI pahalı `schedule`
 * hesabını (her parsel için uydu + olgunluk analizi) tüketiyor; iki route iki
 * kez hesaplama demekti. Menüde ayrı görünürler (`?view=lojistik`) — IT-41'in
 * "Saha Raporları" için kullandığı AYNI kalıp.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/api";
import {
  Factory, CalendarDays, RefreshCw, Settings, CheckCircle2, AlertTriangle,
  TrendingUp, Truck,
} from "lucide-react";

const fmt = (n) => (n == null ? "—" : new Intl.NumberFormat("tr-TR").format(n));

/** Polar rozeti — şeker pancarında ~%16 ve üzeri iyi, %14 altı zayıf kabul
 *  edilir (fabrika fiyatlandırması bu eşikler etrafında kurulur). */
function PolarBadge({ value }) {
  if (value == null) return <span className="text-[var(--text-dim)]">—</span>;
  const cls = value >= 17 ? "badge-a" : value >= 15.5 ? "badge-b" : value >= 14 ? "badge-c" : "badge-d";
  return <span className={`badge ${cls}`}>%{value}</span>;
}

export default function HasatLojistigi() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view") === "lojistik" ? "lojistik" : "sokum";
  const setView = (v) => setSearchParams(v === "lojistik" ? { view: "lojistik" } : {});

  const [schedule, setSchedule] = useState(null);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [season, setSeason] = useState(new Date().getFullYear());
  const [showSettings, setShowSettings] = useState(false);
  // Söküm sekmesinde varsayılan sıralama: POLARA göre (kullanıcı isteği —
  // "sadece polara uygun olarak söküm tarafını öne çıkaralım").
  const [sortBy, setSortBy] = useState("polar");

  useEffect(() => {
    api.get("/harvest-logistics/settings").then((r) => setSettings(r.data)).catch(() => {});
  }, []);

  const load = () => {
    setBusy(true);
    setMsg("");
    api.get("/harvest-logistics/schedule", { params: { season, limit: 120 } })
      .then((r) => setSchedule(r.data))
      .catch((e) => setMsg(e.response?.data?.detail || "Çizelge hesaplanamadı."))
      .finally(() => setBusy(false));
  };

  // Polar odaklı özet — söküm sekmesinin KPI'ları buradan beslenir.
  const polarStats = useMemo(() => {
    const vals = (schedule?.plan || [])
      .map((r) => r.beklenen_polar)
      .filter((v) => v != null && !Number.isNaN(v));
    if (vals.length === 0) return { ortalama: null, max: null, yuksek: 0, dusuk: 0 };
    return {
      ortalama: Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100,
      max: Math.max(...vals),
      yuksek: vals.filter((v) => v >= 17).length,
      dusuk: vals.filter((v) => v < 14).length,
    };
  }, [schedule]);

  // Söküm sekmesi polara göre sıralar (yüksek şeker oranı önce); lojistik
  // sekmesi backend'in kapasiteye göre kurduğu takvim sırasını KORUR.
  const sortedPlan = useMemo(() => {
    const plan = schedule?.plan || [];
    if (view !== "sokum") return plan;
    const copy = [...plan];
    if (sortBy === "polar") {
      copy.sort((a, b) => (b.beklenen_polar ?? -1) - (a.beklenen_polar ?? -1));
    } else if (sortBy === "olgunluk") {
      copy.sort((a, b) => (b.olgunlasma_endeksi ?? -1) - (a.olgunlasma_endeksi ?? -1));
    } else {
      copy.sort((a, b) => String(a.planlanan_tarih).localeCompare(String(b.planlanan_tarih)));
    }
    return copy;
  }, [schedule, view, sortBy]);

  async function saveSettings() {
    const { data } = await api.put("/harvest-logistics/settings", settings);
    setSettings(data);
    setMsg("Fabrika ayarları kaydedildi.");
  }

  async function makeAppointment(row) {
    try {
      await api.post("/harvest-logistics/appointments", {
        parcel_id: row.parcel_id, tarih: row.planlanan_tarih, tahmini_ton: row.tahmini_ton,
      });
      setMsg(`${row.parsel} için ${row.planlanan_tarih} tarihine kantar randevusu oluşturuldu.`);
    } catch (e) {
      setMsg(e.response?.data?.detail || "Randevu oluşturulamadı.");
    }
  }

  return (
    <div className="p-8 max-w-[1600px]" data-testid="hasat-lojistigi">
      <header className="mb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SÖKÜM & POLAR</div>
          <h1 className="font-display text-4xl">Hasat</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            {view === "sokum"
              ? "Hangi parsel ne zaman sökülmeli? Sıralama polar tahminine göre — en yüksek şeker oranı önce."
              : "Fabrika işleme kapasitesi, kantar ayarları ve haftalık yük dağılımı."}
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-xs text-[var(--text-dim)]">Sezon</label>
            <input className="input" type="number" value={season} style={{ width: 110 }}
                   onChange={(e) => setSeason(Number(e.target.value))} />
          </div>
          <button className="btn btn-primary" onClick={load} disabled={busy} data-testid="schedule-run">
            <RefreshCw size={15} className={busy ? "animate-spin" : ""} /> Çizelgeyi Hesapla
          </button>
        </div>
      </header>

      {/* Sekmeler — söküm (polar) / kampanya lojistiği */}
      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setView("sokum")} data-testid="tab-sokum"
                className={`btn text-sm ${view === "sokum" ? "btn-primary" : "btn-ghost"}`}>
          <Factory size={14} /> Söküm Planı (Polar)
        </button>
        <button onClick={() => setView("lojistik")} data-testid="tab-lojistik"
                className={`btn text-sm ${view === "lojistik" ? "btn-primary" : "btn-ghost"}`}>
          <Truck size={14} /> Kampanya Lojistiği
        </button>
      </div>

      {msg && <div className="card p-3 mb-4 text-sm text-[var(--primary)]">{msg}</div>}

      {view === "lojistik" && settings && !showSettings && (
        <div className="mb-3">
          <button className="btn btn-ghost text-xs" onClick={() => setShowSettings(true)}>
            <Settings size={14} /> Fabrika Ayarlarını Düzenle
          </button>
        </div>
      )}

      {view === "lojistik" && showSettings && settings && (
        <div className="card p-4 mb-4 grid gap-3 sm:grid-cols-3">
          {[["gunluk_isleme_kapasitesi_ton", "Günlük İşleme Kapasitesi (ton)"],
            ["kampanya_baslangic", "Kampanya Başlangıç (AA-GG)"],
            ["kampanya_bitis", "Kampanya Bitiş (AA-GG)"],
            ["kantar_sayisi", "Kantar Sayısı"],
            ["kantar_saatlik_arac", "Kantar Saatlik Araç"]].map(([k, label]) => (
            <div key={k}>
              <label className="text-xs text-[var(--text-dim)]">{label}</label>
              <input className="input" value={settings[k] ?? ""}
                     onChange={(e) => setSettings({ ...settings, [k]: e.target.value })} />
            </div>
          ))}
          <div className="flex items-end">
            <button className="btn btn-primary text-xs" onClick={saveSettings}>Kaydet</button>
          </div>
        </div>
      )}

      {busy && <div className="card p-6 text-center text-sm text-[var(--text-dim)]">
        Parsellerin olgunluk ve polar tahminleri hesaplanıyor…
      </div>}

      {schedule && !busy && (
        <>
          {/* KPI'lar sekmeye göre değişir — söküm sekmesinde POLAR merkezde,
              lojistik sekmesinde kapasite/tonaj merkezde. */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {(view === "sokum"
              ? [["Ortalama Polar", polarStats.ortalama != null ? `%${polarStats.ortalama}` : "—"],
                 ["En Yüksek Polar", polarStats.max != null ? `%${polarStats.max}` : "—"],
                 ["Yüksek Polar (≥%17)", `${polarStats.yuksek} parsel`],
                 ["Düşük Polar (<%14)", `${polarStats.dusuk} parsel`]]
              : [["Planlanan Parsel", schedule.plan?.length],
                 ["Toplam Tonaj", fmt(schedule.toplam_ton)],
                 ["Kampanya", `${schedule.kampanya?.baslangic} → ${schedule.kampanya?.bitis}`],
                 ["Günlük Kapasite", `${fmt(schedule.kampanya?.gunluk_kapasite_ton)} ton`]]
            ).map(([l, v]) => (
              <div key={l} className="card p-4">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{l}</div>
                <div className="font-display text-2xl mt-1">{v}</div>
              </div>
            ))}
          </div>

          {schedule.kapsam?.truncated && (
            <div className="card p-3 mb-4 text-xs text-amber-300 flex items-center gap-2">
              <AlertTriangle size={14} />
              {schedule.kapsam.toplam_sozlesme} sözleşmeden {schedule.kapsam.islenen_sozlesme} tanesi
              işlendi (her parsel için uydu/olgunluk analizi çalıştığından kapsam sınırlıdır).
            </div>
          )}

          {/* Haftalık özet — kapasite planlaması, LOJİSTİK sekmesine ait. */}
          {view === "lojistik" && (
          <div className="card overflow-hidden mb-4">
            <div className="p-3 border-b border-[var(--border)] font-display text-lg flex items-center gap-2">
              <CalendarDays size={16} className="text-[var(--primary)]" /> Haftalık Özet
            </div>
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-3">Hafta</th><th className="p-3">Parsel</th>
                  <th className="p-3">Tonaj</th><th className="p-3">Ortalama Polar</th>
                </tr>
              </thead>
              <tbody>
                {(schedule.haftalik_ozet || []).map((w) => (
                  <tr key={w.hafta} className="border-b border-[var(--border)]">
                    <td className="p-3 font-medium">{w.hafta}. hafta</td>
                    <td className="p-3">{w.parsel_sayisi}</td>
                    <td className="p-3">{fmt(w.toplam_ton)} ton</td>
                    <td className="p-3">{w.ortalama_polar != null ? `%${w.ortalama_polar}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}

          {/* Parsel planı — her iki sekmede de görünür, ama söküm sekmesinde
              polara göre sıralanır ve polar sütunu vurgulanır. */}
          <div className="card overflow-hidden">
            <div className="p-3 border-b border-[var(--border)] font-display text-lg flex items-center justify-between flex-wrap gap-2">
              <span className="flex items-center gap-2">
                <Factory size={16} className="text-[var(--primary)]" /> Söküm Planı
              </span>
              {view === "sokum" && (
                <span className="flex items-center gap-1.5 text-xs font-sans font-normal">
                  <TrendingUp size={13} className="text-[var(--text-dim)]" />
                  Sırala:
                  {[["polar", "Polar (yüksek → düşük)"], ["tarih", "Planlanan tarih"],
                    ["olgunluk", "Olgunluk endeksi"]].map(([k, label]) => (
                    <button key={k} onClick={() => setSortBy(k)}
                            data-testid={`sort-${k}`}
                            className={`px-2 py-0.5 rounded ${
                              sortBy === k ? "bg-[var(--primary)] text-black" : "bg-[var(--surface-2)] text-[var(--text-dim)]"}`}>
                      {label}
                    </button>
                  ))}
                </span>
              )}
            </div>
            <div className="max-h-[520px] overflow-y-auto scrollbar">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)] sticky top-0">
                  <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                    <th className="p-3">Tarih</th><th className="p-3">Parsel</th><th className="p-3">Çiftçi</th>
                    <th className="p-3">Köy</th><th className="p-3">Tonaj</th>
                    <th className="p-3">Polar</th><th className="p-3">Olgunluk</th><th className="p-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPlan.map((r) => (
                    <tr key={r.parcel_id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                      <td className="p-3 font-mono text-xs">{r.planlanan_tarih}</td>
                      <td className="p-3">{r.parsel}</td>
                      <td className="p-3 text-[var(--text-dim)]">{r.ciftci}</td>
                      <td className="p-3 text-[var(--text-dim)]">{r.koy}</td>
                      <td className="p-3">{fmt(r.tahmini_ton)} t</td>
                      <td className="p-3"><PolarBadge value={r.beklenen_polar} /></td>
                      <td className="p-3">{r.olgunlasma_endeksi ?? "—"}</td>
                      <td className="p-3 text-right">
                        {/* Randevu = lojistik eylemi; söküm sekmesinde gizlenir
                            ki bu ekran "ne zaman sökmeliyim" sorusuna odaklansın. */}
                        {view === "lojistik" ? (
                          <button className="btn btn-ghost text-xs" onClick={() => makeAppointment(r)}>
                            <CheckCircle2 size={12} /> Randevu
                          </button>
                        ) : (
                          <a className="btn btn-ghost text-xs" href={`/parseller/${r.parcel_id}`}>Parsel →</a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
