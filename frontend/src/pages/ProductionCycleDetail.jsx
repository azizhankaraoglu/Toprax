/**
 * ÜRETİM SEZONU (ProductionCycle) DETAY / ÇALIŞMA EKRANI — IT-06
 *
 * Sprint A2 ikinci omurga: Farmer → Parcel → ProductionCycle → burada
 * sezon altında sözleşme/ekim/toprak zincirini tek ekranda gösterir ve
 * yeni kayıtların bu sezon bağlamında (production_cycle_id otomatik
 * dolu) açılmasını sağlar (parcel_id/farmer_id/sezon alanları formda
 * TEKRAR SORULMAZ — cycle'dan miras alınır).
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import { ArrowLeft, MapPin, FileText, Sprout, FlaskConical, Check, Wallet, Landmark, Undo2, Receipt } from "lucide-react";
import { QuickAddPanel } from "@/components/QuickAdd";
import VisitHistory from "@/components/VisitHistory";

// IT-21 — İcmal/Mutabakat Belgesi durumları (backend/reconciliation.py ile birebir).
const RECONCILIATION_STATUS_LABELS = { beklemede: "Beklemede", onaylandi: "Onaylandı", itiraz_edildi: "İtiraz Edildi" };
const RECONCILIATION_STATUS_BADGE = { beklemede: "badge-b", onaylandi: "badge-a", itiraz_edildi: "badge-d" };

// IT-19 — LedgerEntry entry_type'ları (backend/ledger.py ile birebir).
const ENTRY_TYPE_LABELS = {
  destek_talebi: "Destek Talebi", destek_teslimi: "Destek Teslimi", avans: "Avans",
  cari_hareket: "Cari Hareket", hakedis: "Hakediş", mahsup: "Mahsup", prim: "Prim",
  kesinti: "Kesinti", odeme: "Ödeme", iade: "İade",
};

// IT-18 — SupportRequest 9 durumlu akış (backend/support.py ile birebir).
const SUPPORT_STATUS_LABELS = {
  taslak: "Taslak", gonderildi: "Gönderildi", inceleniyor: "İnceleniyor",
  onaylandi: "Onaylandı", hazirlaniyor: "Hazırlanıyor", teslim_edildi: "Teslim Edildi",
  ciftci_onayladi: "Çiftçi Onayladı", muhasebelesti: "Muhasebeleşti", tamamlandi: "Tamamlandı",
  reddedildi: "Reddedildi", iptal_edildi: "İptal Edildi",
};
const SUPPORT_STATUS_BADGE = {
  taslak: "badge-neutral", gonderildi: "badge-b", inceleniyor: "badge-b", onaylandi: "badge-c",
  hazirlaniyor: "badge-c", teslim_edildi: "badge-c", ciftci_onayladi: "badge-a", muhasebelesti: "badge-a",
  tamamlandi: "badge-a", reddedildi: "badge-d", iptal_edildi: "badge-d",
};
const SUPPORT_ALLOWED_NEXT = {
  taslak: ["gonderildi", "iptal_edildi"],
  gonderildi: ["inceleniyor", "reddedildi", "iptal_edildi"],
  inceleniyor: ["onaylandi", "reddedildi", "iptal_edildi"],
  onaylandi: ["hazirlaniyor", "reddedildi", "iptal_edildi"],
  hazirlaniyor: ["teslim_edildi", "reddedildi", "iptal_edildi"],
  teslim_edildi: ["ciftci_onayladi", "reddedildi", "iptal_edildi"],
  ciftci_onayladi: ["muhasebelesti", "reddedildi", "iptal_edildi"],
  muhasebelesti: ["tamamlandi", "reddedildi", "iptal_edildi"],
  tamamlandi: [], reddedildi: [], iptal_edildi: [],
};

const STATUS_LABELS = {
  planning: "Planlama", active: "Aktif", harvesting: "Hasat",
  completed: "Tamamlandı", cancelled: "İptal",
};
const STATUS_BADGE = {
  planning: "badge-neutral", active: "badge-b", harvesting: "badge-c",
  completed: "badge-a", cancelled: "badge-d",
};
// Backend'deki ALLOWED_TRANSITIONS ile birebir aynı — sunucu zaten
// doğrular, burası sadece hangi butonların gösterileceğini belirler.
const ALLOWED_NEXT = {
  planning: ["active", "cancelled"],
  active: ["harvesting", "cancelled"],
  harvesting: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
};

export default function ProductionCycleDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [changingStatus, setChangingStatus] = useState(false);
  const [error, setError] = useState("");
  const [supportTypes, setSupportTypes] = useState([]);
  const [supportRequests, setSupportRequests] = useState([]);
  const [confirmMethod, setConfirmMethod] = useState({}); // requestId -> "mobil_onay"|"fotograf"
  const [account, setAccount] = useState(null); // IT-19 — { balance, by_type, entries }
  const [entitlement, setEntitlement] = useState(null); // IT-20
  const [reconciliation, setReconciliation] = useState(null); // IT-21
  const [reconciliationBusy, setReconciliationBusy] = useState(false);

  const load = () => api.get(`/production-cycles/${id}`).then((r) => setData(r.data));
  const loadSupport = () => {
    api.get("/support-requests", { params: { production_cycle_id: id } }).then((r) => setSupportRequests(r.data));
  };
  const loadAccount = () => {
    api.get(`/production-cycles/${id}/current-account`).then((r) => setAccount(r.data)).catch(() => setAccount(null));
  };
  const loadEntitlement = () => {
    api.get(`/entitlement/${id}`).then((r) => setEntitlement(r.data)).catch(() => setEntitlement(null));
  };
  const loadReconciliation = () => {
    api.get(`/reconciliation/${id}`).then((r) => setReconciliation(r.data)).catch(() => setReconciliation(null));
  };
  useEffect(() => {
    load();
    loadSupport();
    loadAccount();
    loadEntitlement();
    loadReconciliation();
    api.get("/support-types").then((r) => setSupportTypes(r.data)).catch(() => setSupportTypes([]));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function generateReconciliation() {
    setReconciliationBusy(true);
    try {
      await api.post(`/reconciliation/${id}`);
      loadReconciliation();
    } catch (err) {
      alert(err.response?.data?.detail || "İcmal belgesi oluşturulamadı");
    } finally { setReconciliationBusy(false); }
  }

  function viewReconciliationPdf() {
    if (!reconciliation) return;
    api.get(`/reconciliation/${reconciliation.id}/pdf`, { responseType: "blob" }).then((r) => {
      const url = URL.createObjectURL(r.data);
      window.open(url, "_blank");
    });
  }

  async function reverseLedgerEntry(entryId) {
    const reason = window.prompt("Ters kayıt sebebi (opsiyonel):") || undefined;
    try {
      await api.post(`/ledger/${entryId}/reverse`, { reason });
      loadAccount();
    } catch (err) {
      alert(err.response?.data?.detail || "Ters kayıt oluşturulamadı");
    }
  }

  async function transitionSupportRequest(reqId, status) {
    try {
      const body = { status };
      if (status === "ciftci_onayladi") body.confirmation_method = confirmMethod[reqId] || "mobil_onay";
      if (status === "reddedildi" || status === "iptal_edildi") {
        body.reason = window.prompt("Sebep (opsiyonel):") || undefined;
      }
      await api.put(`/support-requests/${reqId}/transition`, body);
      loadSupport();
      loadAccount(); // "muhasebelesti" geçişi otomatik bir Ledger kaydı açabilir (IT-19)
    } catch (err) {
      alert(err.response?.data?.detail || "Durum değiştirilemedi");
    }
  }

  async function changeStatus(next) {
    setChangingStatus(true);
    setError("");
    try {
      await api.put(`/production-cycles/${id}/status`, { status: next });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Durum değiştirilemedi");
    } finally {
      setChangingStatus(false);
    }
  }

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;
  const { cycle, farmer, parcel, contracts, plantings, soil_samples } = data;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="production-cycle-detail-page">
      <button onClick={() => nav(parcel ? `/parseller/${parcel.id}` : "/parseller")} className="btn btn-ghost mb-4 text-sm">
        <ArrowLeft size={14}/> {parcel ? parcel.name : "Parsel"} sayfasına dön
      </button>

      {/* ÜST KART — sezon özeti + durum */}
      <div className="card p-6 mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">ÜRETİM SEZONU</div>
            <h1 className="font-display text-3xl">{cycle.year} — {cycle.season}</h1>
            <div className="text-sm text-[var(--text-dim)] mt-2 flex items-center gap-4 flex-wrap">
              <span>{cycle.crop}</span>
              {parcel && (
                <button onClick={() => nav(`/parseller/${parcel.id}`)} className="flex items-center gap-1 hover:text-[var(--primary)]">
                  <MapPin size={13}/> {parcel.name} ({parcel.parcel_code})
                </button>
              )}
              {farmer && (
                <button onClick={() => nav(`/ciftciler/${farmer.id}`)} className="hover:text-[var(--primary)]">
                  {farmer.full_name} ({farmer.member_no})
                </button>
              )}
            </div>
          </div>
          <span className={`badge ${STATUS_BADGE[cycle.status] || "badge-neutral"} text-sm px-3 py-1.5`}>
            {STATUS_LABELS[cycle.status] || cycle.status}
          </span>
        </div>

        {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mt-3">{error}</div>}

        {(ALLOWED_NEXT[cycle.status] || []).length > 0 && (
          <div className="flex items-center gap-2 mt-4 pt-4 border-t border-[var(--border)]">
            <span className="text-xs text-[var(--text-dim)] mr-1">Durum değiştir:</span>
            {ALLOWED_NEXT[cycle.status].map((next) => (
              <button
                key={next}
                onClick={() => changeStatus(next)}
                disabled={changingStatus}
                className={`btn text-xs ${next === "cancelled" ? "btn-ghost text-red-400" : "btn-primary"}`}
                data-testid={`cycle-status-${next}`}
              >
                <Check size={13}/> {STATUS_LABELS[next]}
              </button>
            ))}
          </div>
        )}

        {cycle.notes && (
          <div className="text-xs text-[var(--text-dim)] mt-3 pt-3 border-t border-[var(--border)]">{cycle.notes}</div>
        )}
      </div>

      {/* SÖZLEŞMELER */}
      <div className="card overflow-hidden mb-6">
        <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
          <FileText size={16} className="text-[var(--primary)]"/>
          <h3 className="font-display text-lg">Sözleşmeler ({contracts.length})</h3>
        </div>
        <div className="p-4">
          <QuickAddPanel
            title="Yeni Sözleşme"
            testId="cycle-contract-add"
            fields={[
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
                parcel_id: cycle.parcel_id,
                farmer_id: cycle.farmer_id,
                season: cycle.year,
                production_cycle_id: cycle.id,
                kota_dekar: Number(v.kota_dekar),
                kota_ton: Number(v.kota_ton),
                advance_seed_kg: v.advance_seed_kg ? Number(v.advance_seed_kg) : null,
                advance_fertilizer_kg: v.advance_fertilizer_kg ? Number(v.advance_fertilizer_kg) : null,
              });
              load();
            }}
          />
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-3">Sözleşme No</th><th className="p-3">Çeşit</th><th className="p-3">Kota (da)</th><th className="p-3">Kota (ton)</th><th className="p-3">Durum</th>
          </tr></thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={c.id} className="border-b border-[var(--border)]">
                <td className="p-3 font-mono text-xs text-[var(--text-dim)]">{c.contract_no}</td>
                <td className="p-3">{c.variety}</td>
                <td className="p-3">{c.kota_dekar}</td>
                <td className="p-3">{c.kota_ton}</td>
                <td className="p-3"><span className={`badge ${c.status === "imzalı" ? "badge-a" : "badge-c"}`}>{c.status}</span></td>
              </tr>
            ))}
            {contracts.length === 0 && <tr><td colSpan="5" className="p-6 text-center text-[var(--text-dim)]">Bu sezonda sözleşme yok</td></tr>}
          </tbody>
        </table>
      </div>

      {/* EKİM KAYITLARI */}
      <div className="card overflow-hidden mb-6">
        <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
          <Sprout size={16} className="text-emerald-400"/>
          <h3 className="font-display text-lg">Ekim Kayıtları ({plantings.length})</h3>
        </div>
        <div className="p-4">
          <QuickAddPanel
            title="Yeni Ekim Kaydı"
            testId="cycle-planting-add"
            fields={[
              { name: "variety", label: "Çeşit", required: true },
              { name: "planting_date", label: "Ekim Tarihi", type: "date", required: true },
              { name: "expected_harvest_date", label: "Beklenen Hasat", type: "date", required: true },
              { name: "stage", label: "Aşama", type: "select", default: "ekim",
                options: [
                  { value: "ekim", label: "Ekim" }, { value: "gelişim", label: "Gelişim" },
                  { value: "olgunlaşma", label: "Olgunlaşma" }, { value: "hasat", label: "Hasat" },
                ] },
            ]}
            onSubmit={async (v) => {
              await api.post("/plantings", {
                ...v,
                parcel_id: cycle.parcel_id,
                farmer_id: cycle.farmer_id,
                season: cycle.year,
                production_cycle_id: cycle.id,
              });
              load();
            }}
          />
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-3">Çeşit</th><th className="p-3">Ekim Tarihi</th><th className="p-3">Beklenen Hasat</th><th className="p-3">Aşama</th>
          </tr></thead>
          <tbody>
            {plantings.map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)]">
                <td className="p-3">{p.variety}</td>
                <td className="p-3 text-[var(--text-dim)]">{p.planting_date}</td>
                <td className="p-3 text-[var(--text-dim)]">{p.expected_harvest_date}</td>
                <td className="p-3"><span className="badge badge-b">{p.stage}</span></td>
              </tr>
            ))}
            {plantings.length === 0 && <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Bu sezonda ekim kaydı yok</td></tr>}
          </tbody>
        </table>
      </div>

      {/* TOPRAK ANALİZLERİ */}
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
          <FlaskConical size={16} className="text-[var(--primary)]"/>
          <h3 className="font-display text-lg">Toprak Analizleri ({soil_samples.length})</h3>
        </div>
        <div className="p-4">
          <QuickAddPanel
            title="Yeni Toprak Analizi"
            testId="cycle-soil-add"
            fields={[
              { name: "date", label: "Tarih", type: "date", required: true },
              { name: "lab_name", label: "Laboratuvar", required: true },
              { name: "ph", label: "pH", type: "number", step: "0.01", required: true },
              { name: "ec", label: "EC (dS/m)", type: "number", step: "0.01", required: true },
              { name: "organic_matter_pct", label: "Organik Madde (%)", type: "number", step: "0.01", required: true },
              { name: "n_ppm", label: "N (ppm)", type: "number", required: true },
              { name: "p_ppm", label: "P (ppm)", type: "number", required: true },
              { name: "k_ppm", label: "K (ppm)", type: "number", required: true },
            ]}
            onSubmit={async (v) => {
              await api.post("/soil-samples", {
                ...v,
                parcel_id: cycle.parcel_id,
                production_cycle_id: cycle.id,
                ph: Number(v.ph), ec: Number(v.ec), organic_matter_pct: Number(v.organic_matter_pct),
                n_ppm: Number(v.n_ppm), p_ppm: Number(v.p_ppm), k_ppm: Number(v.k_ppm),
              });
              load();
            }}
          />
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-3">Tarih</th><th className="p-3">Lab</th><th className="p-3">pH</th><th className="p-3">EC</th><th className="p-3">N/P/K</th><th className="p-3">Öneri</th>
          </tr></thead>
          <tbody>
            {soil_samples.map((s) => (
              <tr key={s.id} className="border-b border-[var(--border)]">
                <td className="p-3 text-xs">{s.date}</td>
                <td className="p-3 text-xs text-[var(--text-dim)]">{s.lab_name}</td>
                <td className="p-3">{s.ph}</td>
                <td className="p-3">{s.ec}</td>
                <td className="p-3 text-xs">{s.n_ppm}/{s.p_ppm}/{s.k_ppm}</td>
                <td className="p-3 text-xs text-[var(--primary)]">{s.recommendation}</td>
              </tr>
            ))}
            {soil_samples.length === 0 && <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Bu sezonda toprak analizi yok</td></tr>}
          </tbody>
        </table>
      </div>

      {/* DESTEK TALEPLERİ — IT-18 / FAZ 7 UFYD */}
      <div className="card overflow-hidden mt-6">
        <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
          <Wallet size={16} className="text-amber-400"/>
          <h3 className="font-display text-lg">Destek Talepleri ({supportRequests.length})</h3>
        </div>
        <div className="p-4">
          <QuickAddPanel
            title="Yeni Destek Talebi"
            testId="cycle-support-request-add"
            fields={[
              { name: "support_type_id", label: "Destek Tipi", type: "select", required: true,
                options: supportTypes.map((t) => ({ value: t.id, label: `${t.name} (${t.unit})` })) },
              { name: "requested_amount", label: "Talep Edilen Miktar", type: "number", step: "0.01", required: true },
              { name: "note", label: "Not", type: "textarea", span2: true },
            ]}
            onSubmit={async (v) => {
              await api.post("/support-requests", {
                farmer_id: cycle.farmer_id,
                production_cycle_id: cycle.id,
                support_type_id: v.support_type_id,
                requested_amount: Number(v.requested_amount),
                note: v.note || null,
              });
              loadSupport();
            }}
          />
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-3">Destek Tipi</th><th className="p-3">Miktar</th><th className="p-3">Kanal</th>
            <th className="p-3">Durum</th><th className="p-3">Talep Tarihi</th><th className="p-3">İlerlet</th>
          </tr></thead>
          <tbody>
            {supportRequests.map((r) => {
              const stype = supportTypes.find((t) => t.id === r.support_type_id);
              const nextOptions = SUPPORT_ALLOWED_NEXT[r.status] || [];
              return (
                <tr key={r.id} className="border-b border-[var(--border)]">
                  <td className="p-3">{stype ? stype.name : r.support_type_id}</td>
                  <td className="p-3">{r.requested_amount} {r.unit}</td>
                  <td className="p-3 text-xs text-[var(--text-dim)] capitalize">{r.channel}</td>
                  <td className="p-3"><span className={`badge ${SUPPORT_STATUS_BADGE[r.status] || "badge-neutral"}`}>{SUPPORT_STATUS_LABELS[r.status] || r.status}</span></td>
                  <td className="p-3 text-xs text-[var(--text-dim)]">{(r.requested_at || "").slice(0, 10)}</td>
                  <td className="p-3">
                    {nextOptions.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {r.status === "teslim_edildi" && (
                          <select
                            className="input py-1 text-xs w-auto"
                            value={confirmMethod[r.id] || "mobil_onay"}
                            onChange={(e) => setConfirmMethod((m) => ({ ...m, [r.id]: e.target.value }))}
                          >
                            <option value="mobil_onay">Mobil Onay</option>
                            <option value="fotograf">Fotoğraf</option>
                          </select>
                        )}
                        {nextOptions.map((next) => (
                          <button
                            key={next}
                            onClick={() => transitionSupportRequest(r.id, next)}
                            className={`btn text-xs ${next === "reddedildi" || next === "iptal_edildi" ? "btn-ghost text-red-400" : "btn-primary"}`}
                            data-testid={`support-request-${next}`}
                          >
                            {SUPPORT_STATUS_LABELS[next]}
                          </button>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {supportRequests.length === 0 && <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Bu sezonda destek talebi yok</td></tr>}
          </tbody>
        </table>
      </div>

      {/* CARİ HESAP — IT-19 / FAZ 7 UFYD */}
      <div className="card overflow-hidden mt-6">
        <div className="p-4 border-b border-[var(--border)] flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Landmark size={16} className="text-[var(--primary)]"/>
            <h3 className="font-display text-lg">Cari Hesap ({account?.entries?.length || 0})</h3>
          </div>
          {account && (
            <span className={`font-display text-xl ${account.balance >= 0 ? "text-[var(--primary)]" : "text-red-400"}`}>
              {account.balance.toLocaleString("tr-TR")} ₺
            </span>
          )}
        </div>

        {account && Object.keys(account.by_type).length > 0 && (
          <div className="p-4 flex flex-wrap gap-2 border-b border-[var(--border)]">
            {Object.entries(account.by_type).map(([type, sum]) => (
              <span key={type} className="badge badge-neutral text-xs">
                {ENTRY_TYPE_LABELS[type] || type}: {sum.toLocaleString("tr-TR")} ₺
              </span>
            ))}
          </div>
        )}

        <div className="p-4">
          <QuickAddPanel
            title="Yeni Hareket Ekle"
            testId="cycle-ledger-add"
            fields={[
              { name: "entry_type", label: "Hareket Tipi", type: "select", required: true,
                options: Object.entries(ENTRY_TYPE_LABELS).map(([value, label]) => ({ value, label })) },
              { name: "amount", label: "Tutar (+ / -)", type: "number", step: "0.01", required: true },
              { name: "description", label: "Açıklama", type: "textarea", span2: true },
            ]}
            onSubmit={async (v) => {
              await api.post("/ledger", {
                production_cycle_id: cycle.id,
                farmer_id: cycle.farmer_id,
                entry_type: v.entry_type,
                amount: Number(v.amount),
                description: v.description || null,
              });
              loadAccount();
            }}
          />
        </div>

        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-3">Tarih</th><th className="p-3">Tip</th><th className="p-3">Tutar</th>
            <th className="p-3">Açıklama</th><th className="p-3">Kaynak</th><th className="p-3"></th>
          </tr></thead>
          <tbody>
            {(account?.entries || []).map((e) => (
              <tr key={e.id} className="border-b border-[var(--border)]">
                <td className="p-3 text-xs text-[var(--text-dim)]">{(e.created_at || "").slice(0, 10)}</td>
                <td className="p-3">
                  <span className="badge badge-neutral">{ENTRY_TYPE_LABELS[e.entry_type] || e.entry_type}</span>
                  {e.is_reversal && <span className="badge badge-d ml-1 text-[10px]">TERS KAYIT</span>}
                </td>
                <td className={`p-3 font-mono ${e.amount >= 0 ? "text-[var(--primary)]" : "text-red-400"}`}>
                  {e.amount.toLocaleString("tr-TR")} {e.currency}
                </td>
                <td className="p-3 text-xs text-[var(--text-dim)]">{e.description || "—"}</td>
                <td className="p-3 text-xs text-[var(--text-dim)]">{e.reference_type || "—"}</td>
                <td className="p-3">
                  <button onClick={() => reverseLedgerEntry(e.id)} className="btn btn-ghost text-xs" data-testid={`ledger-reverse-${e.id}`}>
                    <Undo2 size={12}/> Ters Kayıt
                  </button>
                </td>
              </tr>
            ))}
            {(!account || account.entries.length === 0) && (
              <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Bu sezonda hareket yok</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* İCMAL BELGESİ — IT-21 / FAZ 7 UFYD */}
      <div className="card p-5 mt-6">
        <div className="flex items-center gap-2 mb-3">
          <Receipt size={16} className="text-[var(--primary)]"/>
          <h3 className="font-display text-lg">İcmal Belgesi</h3>
        </div>
        {!entitlement ? (
          <div className="text-sm text-[var(--text-dim)]">
            Bu sezon için henüz hakediş sonuçlandırılmamış (icmal belgesi hakediş finalize edildikten sonra üretilebilir).
          </div>
        ) : !reconciliation ? (
          <div className="flex items-center justify-between">
            <div className="text-sm text-[var(--text-dim)]">
              Hakediş sonuçlandırılmış (ödenecek tutar: {entitlement.payable_amount.toLocaleString("tr-TR")} ₺) — icmal belgesi henüz oluşturulmamış.
            </div>
            <button onClick={generateReconciliation} disabled={reconciliationBusy} className="btn btn-primary text-sm" data-testid="generate-reconciliation">
              {reconciliationBusy ? "Oluşturuluyor…" : "İcmal Belgesi Oluştur"}
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3">
              <span className={`badge ${RECONCILIATION_STATUS_BADGE[reconciliation.status] || "badge-neutral"}`}>
                {RECONCILIATION_STATUS_LABELS[reconciliation.status] || reconciliation.status}
              </span>
              <span className="text-sm text-[var(--text-dim)]">{(reconciliation.generated_at || "").slice(0, 10)} tarihinde üretildi</span>
              {reconciliation.objection_reason && (
                <span className="text-sm text-red-400">İtiraz: {reconciliation.objection_reason}</span>
              )}
            </div>
            <button onClick={viewReconciliationPdf} className="btn btn-ghost text-sm" data-testid="view-reconciliation-pdf">
              <FileText size={14}/> PDF Görüntüle
            </button>
          </div>
        )}
      </div>

      {/* ZİYARET GEÇMİŞİ — IT-23 */}
      <div className="mt-6">
        <VisitHistory productionCycleId={cycle.id} />
      </div>
    </div>
  );
}
