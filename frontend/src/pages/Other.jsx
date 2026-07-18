import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import RowActions from "@/components/RowActions";
import { useFetch } from "@/hooks/use-fetch";

// #7 — Sezon kota→alan kuralı parametreleri (ton/dekar + sapma%). Pancara özel.
function SeasonParamsPanel({ season }) {
  const paramsQ = useFetch("/season-parameters", { params: { season }, initialData: [] });
  const pancar = (paramsQ.data || []).find((p) => (p.crop || "").toLowerCase().includes("pancar"));
  const [tpd, setTpd] = useState("");
  const [sapma, setSapma] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => { if (pancar) { setTpd(pancar.ton_per_dekar); setSapma(pancar.sapma_yuzde); } }, [pancar]);

  async function save() {
    setMsg("");
    await api.post("/season-parameters", {
      season, crop: "Şeker Pancarı",
      ton_per_dekar: Number(tpd), sapma_yuzde: Number(sapma),
      ndvi_ekili_esigi: pancar?.ndvi_ekili_esigi ?? 0.55,
      ndvi_sokum_esigi: pancar?.ndvi_sokum_esigi ?? 0.25,
    });
    setMsg("Kaydedildi."); paramsQ.reload();
  }
  async function seed() { await api.post(`/season-parameters/seed-defaults?season=${season}`); paramsQ.reload(); }

  return (
    <div className="card p-4 mb-4" data-testid="season-params-panel">
      <div className="text-sm font-medium mb-1">Kota → Ekilebilir Alan Kuralı ({season} · Şeker Pancarı)</div>
      <p className="text-[11px] text-[var(--text-dim)] mb-3">
        Gereken alan = kota (ton) ÷ (ton/dekar). Ekilebilir alan yetersizse: sapma içindeyse sözleşme
        <b> onaya düşer</b>, dışındaysa <b>yapılamaz</b>. (Parametresi olmayan ürünlerde kural uygulanmaz.)
      </p>
      {pancar ? (
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-[11px] text-[var(--text-dim)] block">Ton / Dekar</label>
            <input className="input w-28" type="number" step="0.1" value={tpd}
                   onChange={(e) => setTpd(e.target.value)} data-testid="sp-tpd" />
          </div>
          <div>
            <label className="text-[11px] text-[var(--text-dim)] block">Sapma (%)</label>
            <input className="input w-28" type="number" step="1" value={sapma}
                   onChange={(e) => setSapma(e.target.value)} data-testid="sp-sapma" />
          </div>
          <button onClick={save} className="btn btn-primary text-xs" data-testid="sp-save">Kaydet</button>
          {msg && <span className="text-xs text-[var(--primary)]">{msg}</span>}
        </div>
      ) : (
        <button onClick={seed} className="btn btn-ghost text-xs" data-testid="sp-seed">
          Varsayılanları Yükle (4 ton/dekar, %10 sapma)
        </button>
      )}
    </div>
  );
}

const STATUS_OPTS = [
  { value: "taslak", label: "Taslak" }, { value: "imzalı", label: "İmzalı" }, { value: "iptal", label: "İptal" },
];

// Refactoring notu (2026-07-11): bu dosyadaki 6 bileşenin her biri ayrı
// ayrı useState+useEffect+api.get tekrarlıyordu — useFetch hook'una
// taşındı (bkz. hooks/use-fetch.js). DAVRANIŞ AYNI: mount'ta bir kere
// fetch, mutasyon sonrası ilgili reload() çağrılır (öncekiyle birebir).

export function Sozlesmeler() {
  const nav = useNavigate();
  const contractsQ = useFetch("/contracts", { params: { season: 2025 }, initialData: [] });
  const parcelsQ = useFetch("/parcels", { params: { limit: 500 }, initialData: [] });
  const contracts = contractsQ.data;
  const parcels = parcelsQ.data;
  const parcelsById = new Map(parcels.map((p) => [p.id, p]));

  return (
    <div className="p-8" data-testid="sozlesmeler-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M04 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Sözleşme & Kota — 2025</h1>

      <SeasonParamsPanel season={2025} />

      <QuickAddPanel
        title="Yeni Sözleşme"
        testId="contract-add"
        extraModule="contracts"
        fields={[
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "season", label: "Sezon", type: "number", required: true, default: 2025 },
          { name: "variety", label: "Çeşit", required: true },
          { name: "kota_dekar", label: "Kota (dekar)", type: "number", step: "0.1", required: true },
          { name: "kota_ton", label: "Kota (ton)", type: "number", step: "0.1", required: true },
          { name: "advance_seed_kg", label: "Tohum Avansı (kg)", type: "number", step: "0.1" },
          { name: "advance_fertilizer_kg", label: "Gübre Avansı (kg)", type: "number", step: "0.1" },
          { name: "status", label: "Durum", type: "select", default: "taslak",
            options: [{ value: "taslak", label: "Taslak" }, { value: "imzalı", label: "İmzalı" }, { value: "iptal", label: "İptal" }] },
        ]}
        onSubmit={async (v) => {
          await api.post("/contracts", {
            ...v,
            season: Number(v.season),
            kota_dekar: Number(v.kota_dekar),
            kota_ton: Number(v.kota_ton),
            advance_seed_kg: v.advance_seed_kg ? Number(v.advance_seed_kg) : null,
            advance_fertilizer_kg: v.advance_fertilizer_kg ? Number(v.advance_fertilizer_kg) : null,
          });
          contractsQ.reload();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Sözleşme No</th><th className="p-4">Parsel</th><th className="p-4">Çeşit</th><th className="p-4">Kota (da)</th><th className="p-4">Kota (ton)</th><th className="p-4">Durum</th><th className="p-4 text-right">İşlem</th>
          </tr></thead>
          <tbody>
            {contracts.slice(0,50).map((c) => (
              <tr key={c.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer"
                  onClick={() => nav(`/sozlesmeler/${c.id}`)}
                  data-testid="contract-row" title="Sözleşme detayına git">
                <td className="p-4 font-mono text-xs text-[var(--text-dim)]">{c.contract_no}</td>
                <td className="p-4 text-[var(--text-dim)]">{parcelsById.get(c.parcel_id)?.name || "—"}</td>
                <td className="p-4">{c.variety}</td>
                <td className="p-4">{c.kota_dekar}</td>
                <td className="p-4">{c.kota_ton}</td>
                <td className="p-4">
                  <span className={`badge ${c.status==="imzalı"?"badge-a":c.status==="onay_bekliyor"?"badge-d":c.status==="iptal"?"badge-neutral":"badge-c"}`}
                        title={c.deviation?.aciklama || ""}>
                    {c.status==="onay_bekliyor" ? "onay bekliyor" : c.status}
                  </span>
                </td>
                <td className="p-4" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end items-center gap-1">
                    {c.status === "onay_bekliyor" && (
                      <>
                        <button data-testid="contract-dev-approve"
                          onClick={async () => { await api.post(`/contracts/${c.id}/deviation-decision`, { decision: "onayla" }); contractsQ.reload(); }}
                          className="btn btn-ghost text-xs text-green-400" title={c.deviation?.aciklama || "Sapma onayı"}>Onayla</button>
                        <button data-testid="contract-dev-reject"
                          onClick={async () => { const note = window.prompt("Red sebebi (opsiyonel):") || ""; await api.post(`/contracts/${c.id}/deviation-decision`, { decision: "reddet", note }); contractsQ.reload(); }}
                          className="btn btn-ghost text-xs text-red-400">Reddet</button>
                      </>
                    )}
                    <RowActions
                      entityLabel="sözleşme"
                      values={c}
                      fields={[
                        { name: "variety", label: "Çeşit" },
                        { name: "kota_ton", label: "Kota (ton)", type: "number", step: "0.1" },
                        { name: "advance_seed_kg", label: "Tohum Avansı (kg)", type: "number", step: "0.1" },
                        { name: "advance_fertilizer_kg", label: "Gübre Avansı (kg)", type: "number", step: "0.1" },
                        { name: "status", label: "Durum", type: "select", options: STATUS_OPTS },
                      ]}
                      onSave={async (v) => {
                        await api.put(`/contracts/${c.id}`, {
                          variety: v.variety,
                          kota_ton: v.kota_ton === "" ? null : Number(v.kota_ton),
                          advance_seed_kg: v.advance_seed_kg === "" ? null : Number(v.advance_seed_kg),
                          advance_fertilizer_kg: v.advance_fertilizer_kg === "" ? null : Number(v.advance_fertilizer_kg),
                          status: v.status,
                        });
                        contractsQ.reload();
                      }}
                      onDelete={async () => { await api.delete(`/contracts/${c.id}`); contractsQ.reload(); }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// (SON HAL) Eski `Ekim` export'u kaldırıldı — /ekim rotası artık kendi
// dosyasında yaşayan, toplu işlem destekli EkimKaydi.jsx'e gidiyor.

export function Lojistik() {
  const apptsQ = useFetch("/logistics/appointments", { initialData: [] });
  const farmersQ = useFetch("/farmers", { params: { limit: 500 }, initialData: [] });
  const appts = apptsQ.data;
  const farmers = farmersQ.data;
  return (
    <div className="p-8" data-testid="lojistik-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M08 · MODÜL</div>
      <h1 className="font-display text-4xl mb-6">Lojistik & Kantar</h1>

      <QuickAddPanel
        title="Yeni Randevu"
        testId="appointment-add"
        fields={[
          { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
            options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
          { name: "scheduled_at", label: "Tarih/Saat", type: "datetime-local", required: true },
          { name: "truck_plate", label: "Plaka", required: true },
          { name: "estimated_ton", label: "Tahmini Ton", type: "number", step: "0.1", required: true },
        ]}
        onSubmit={async (v) => {
          await api.post("/logistics/appointments", {
            ...v,
            estimated_ton: Number(v.estimated_ton),
            scheduled_at: new Date(v.scheduled_at).toISOString(),
          });
          apptsQ.reload();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Tarih</th><th className="p-4">Plaka</th><th className="p-4">Tahmini Ton</th><th className="p-4">Gerçek Ton</th><th className="p-4">Polar</th><th className="p-4">Durum</th><th className="p-4 text-right">İşlem</th>
          </tr></thead>
          <tbody>
            {appts.map((a) => (
              <tr key={a.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 text-[var(--text-dim)]">{new Date(a.scheduled_at).toLocaleString("tr-TR")}</td>
                <td className="p-4 font-mono">{a.truck_plate}</td>
                <td className="p-4">{a.estimated_ton} t</td>
                <td className="p-4">{a.actual_ton ? `${a.actual_ton} t` : "-"}</td>
                <td className="p-4">{a.polar_oran ? `%${a.polar_oran}` : "-"}</td>
                <td className="p-4"><span className="badge badge-b">{a.status}</span></td>
                <td className="p-4">
                  <div className="flex justify-end">
                    <RowActions
                      entityLabel="randevu"
                      values={a}
                      fields={[
                        { name: "status", label: "Durum", type: "select", options: [
                          { value: "planlı", label: "Planlı" }, { value: "geldi", label: "Geldi" },
                          { value: "tartıldı", label: "Tartıldı" }, { value: "tamamlandı", label: "Tamamlandı" } ] },
                        { name: "actual_ton", label: "Gerçek Ton", type: "number", step: "0.1" },
                        { name: "polar_oran", label: "Polar Oranı (%)", type: "number", step: "0.1" },
                      ]}
                      onSave={async (v) => {
                        await api.put(`/logistics/appointments/${a.id}`, {
                          status: v.status || null,
                          actual_ton: v.actual_ton === "" ? null : Number(v.actual_ton),
                          polar_oran: v.polar_oran === "" ? null : Number(v.polar_oran),
                        });
                        apptsQ.reload();
                      }}
                      onDelete={async () => { await api.delete(`/logistics/appointments/${a.id}`); apptsQ.reload(); }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Karne() {
  const nav = useNavigate();
  const topQ = useFetch("/karne/top", { initialData: [] });
  const bottomQ = useFetch("/karne/bottom", { initialData: [] });
  const top = topQ.data;
  const bottom = bottomQ.data;
  // SON HAL — satıra tıklayınca "neden bu skor?" analiz sayfası (/karne/:id)
  const Row = ({ f, i }) => (
    <div key={f.id}
         className="flex items-center justify-between p-3 border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer rounded-lg"
         onClick={() => nav(`/karne/${f.id}`)}
         title="Karne analizini aç — neden bu skor?" data-testid="karne-leaderboard-row">
      <div className="flex items-center gap-3">
        <div className="text-[var(--text-dim)] font-display text-xl w-6">#{i + 1}</div>
        <div><div className="text-sm">{f.full_name}</div><div className="text-xs text-[var(--text-dim)]">{f.village}</div></div>
      </div>
      <span className={`badge badge-${f.karne_score.toLowerCase()}`}>{f.karne_score} · {f.karne_points}</span>
    </div>
  );
  return (
    <div className="p-8" data-testid="karne-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M12 · MODÜL</div>
      <h1 className="font-display text-4xl mb-2">Çiftçi Karne / Performans Skoru</h1>
      <p className="text-[var(--text-dim)] text-sm mb-6">İsimlere tıklayın — skorun bileşen bileşen açıklamasını görün.</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 text-[var(--primary)]">🏆 En Yüksek 10</h3>
          {top.map((f, i) => <Row key={f.id} f={f} i={i} />)}
        </div>
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4 text-red-400">⚠️ Geliştirme Bekleyen 10</h3>
          {bottom.map((f, i) => <Row key={f.id} f={f} i={i} />)}
        </div>
      </div>
    </div>
  );
}

export function Bildirimler() {
  // SON HAL — sayfa TÜM bildirimleri limitsiz basıyordu ("ekrana sığmıyor"):
  // artık 30'ar gösterir ("Daha fazla" ile açılır), okunmamış filtresi ve
  // tek tık / toplu okundu işaretleme eklendi.
  const notifsQ = useFetch("/notifications", { initialData: [] });
  const notifs = notifsQ.data;
  const [shown, setShown] = useState(30);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const chBadge = { sms: "badge-b", whatsapp: "badge-a", push: "badge-c", in_app: "badge-neutral" };

  const filtered = onlyUnread ? notifs.filter((n) => n.status !== "okundu") : notifs;
  const visible = filtered.slice(0, shown);
  const unreadCount = notifs.filter((n) => n.status !== "okundu").length;

  async function markRead(n) {
    if (n.status === "okundu") return;
    await api.put(`/notifications/${n.id}/read`);
    notifsQ.reload();
  }
  async function markAllRead() {
    await api.post("/notifications/mark-all-read");
    notifsQ.reload();
  }

  return (
    <div className="p-8 max-w-[1000px]" data-testid="bildirimler-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M11 · MODÜL</div>
      <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
        <h1 className="font-display text-4xl">Bildirim Merkezi</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => { setOnlyUnread(!onlyUnread); setShown(30); }}
                  className={`btn ${onlyUnread ? "btn-primary" : "btn-ghost"} text-xs`}
                  data-testid="notif-unread-filter">
            Okunmamışlar ({unreadCount})
          </button>
          {unreadCount > 0 && (
            <button onClick={markAllRead} className="btn btn-ghost text-xs" data-testid="notif-mark-all">
              Tümünü okundu işaretle
            </button>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        {visible.length === 0 && (
          <div className="p-6 text-center text-[var(--text-dim)] text-sm">
            {onlyUnread ? "Okunmamış bildirim yok." : "Bildirim yok."}
          </div>
        )}
        {visible.map((n) => (
          <div key={n.id}
               className={`p-4 border-b border-[var(--border)] flex items-start gap-4 ${n.status !== "okundu" ? "bg-[var(--primary)]/5 cursor-pointer hover:bg-[var(--primary)]/10" : ""}`}
               onClick={() => markRead(n)}
               title={n.status !== "okundu" ? "Okundu işaretlemek için tıklayın" : undefined}>
            <span className={`badge ${chBadge[n.channel]||"badge-neutral"}`}>{n.channel}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{n.title}</div>
              <div className="text-xs text-[var(--text-dim)] mt-0.5 break-words">{n.message}</div>
              <div className="text-[10px] text-[var(--text-dim)] mt-1">{new Date(n.created_at).toLocaleString("tr-TR")}</div>
            </div>
            <span className={`badge ${n.status==="okundu"?"badge-a":"badge-c"} shrink-0`}>{n.status}</span>
          </div>
        ))}
      </div>

      {filtered.length > shown && (
        <div className="mt-3 flex justify-center">
          <button onClick={() => setShown((s) => s + 30)} className="btn btn-ghost text-xs"
                  data-testid="notif-load-more">
            Daha fazla göster ({filtered.length - shown} kaldı)
          </button>
        </div>
      )}
    </div>
  );
}
