/**
 * HASAT & KAMPANYA LOJİSTİĞİ (fabrika rolü) — haftalık söküm/teslim çizelgesi.
 *
 * Backend: backend/harvest_logistics.py. Çizelge CANLI hesaplanır (kaydedilmez);
 * kabul edilen randevular mevcut `appointments` koleksiyonuna yazılır.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Factory, CalendarDays, RefreshCw, Settings, CheckCircle2, AlertTriangle } from "lucide-react";

const fmt = (n) => (n == null ? "—" : new Intl.NumberFormat("tr-TR").format(n));

export default function HasatLojistigi() {
  const [schedule, setSchedule] = useState(null);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [season, setSeason] = useState(new Date().getFullYear());
  const [showSettings, setShowSettings] = useState(false);

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
      <header className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FABRİKA</div>
          <h1 className="font-display text-4xl">Hasat & Kampanya Lojistiği</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Olgunlaşma endeksi, polar tahmini ve günlük işleme kapasitesine göre
            haftalık söküm/teslim çizelgesi.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-xs text-[var(--text-dim)]">Sezon</label>
            <input className="input" type="number" value={season} style={{ width: 110 }}
                   onChange={(e) => setSeason(Number(e.target.value))} />
          </div>
          <button className="btn btn-ghost text-xs" onClick={() => setShowSettings((s) => !s)}>
            <Settings size={14} /> Fabrika Ayarları
          </button>
          <button className="btn btn-primary" onClick={load} disabled={busy} data-testid="schedule-run">
            <RefreshCw size={15} className={busy ? "animate-spin" : ""} /> Çizelgeyi Hesapla
          </button>
        </div>
      </header>

      {msg && <div className="card p-3 mb-4 text-sm text-[var(--primary)]">{msg}</div>}

      {showSettings && settings && (
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {[["Planlanan Parsel", schedule.plan?.length],
              ["Toplam Tonaj", fmt(schedule.toplam_ton)],
              ["Kampanya", `${schedule.kampanya?.baslangic} → ${schedule.kampanya?.bitis}`],
              ["Günlük Kapasite", `${fmt(schedule.kampanya?.gunluk_kapasite_ton)} ton`]].map(([l, v]) => (
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

          {/* Haftalık özet */}
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

          {/* Parsel planı */}
          <div className="card overflow-hidden">
            <div className="p-3 border-b border-[var(--border)] font-display text-lg flex items-center gap-2">
              <Factory size={16} className="text-[var(--primary)]" /> Söküm Planı
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
                  {(schedule.plan || []).map((r) => (
                    <tr key={r.parcel_id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                      <td className="p-3 font-mono text-xs">{r.planlanan_tarih}</td>
                      <td className="p-3">{r.parsel}</td>
                      <td className="p-3 text-[var(--text-dim)]">{r.ciftci}</td>
                      <td className="p-3 text-[var(--text-dim)]">{r.koy}</td>
                      <td className="p-3">{fmt(r.tahmini_ton)} t</td>
                      <td className="p-3">{r.beklenen_polar != null ? `%${r.beklenen_polar}` : "—"}</td>
                      <td className="p-3">{r.olgunlasma_endeksi ?? "—"}</td>
                      <td className="p-3 text-right">
                        <button className="btn btn-ghost text-xs" onClick={() => makeAppointment(r)}>
                          <CheckCircle2 size={12} /> Randevu
                        </button>
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
