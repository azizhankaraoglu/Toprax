/**
 * ÇİFTÇİLER SAYFASI — Liste + Yeni Çiftçi modalı
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "@/api";
import { Search, UserPlus, Phone, X, ShieldCheck, ShieldAlert } from "lucide-react";
import DynamicFieldsSection from "@/components/DynamicFieldsSection";
import FilterPanel from "@/components/FilterPanel";
import AiAssistantBox from "@/components/AiAssistantBox";

export default function Farmers() {
  const nav = useNavigate();
  // KONU 3 (drill-down): Dashboard'ın "A Karne Çiftçi" kartı /ciftciler?karne=A ile
  // gelir; buradaki karne/bölge filtresi URL parametresinden başlatılır (CLAUDE.md Kural 11).
  const [searchParams] = useSearchParams();
  const [farmers, setFarmers] = useState([]);
  const [regions, setRegions] = useState([]);
  const [q, setQ] = useState("");
  const [regionFilter, setRegionFilter] = useState(searchParams.get("region_id") || "");
  const [karneFilter, setKarneFilter] = useState(searchParams.get("karne") || "");
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  // Yeni çiftçi formu (çekirdek/zorunlu alanlar)
  const [form, setForm] = useState({
    full_name: "", tc_no: "", phone: "", email: "",
    village: "", region_id: "", iban: "", notes: ""
  });
  // Form Yönetimi'nden gelen dinamik alanlar (Sprint A1) — key: field_key
  const [extra, setExtra] = useState({});

  // Denetim eklentisi (2026-07-25) — kullanıcı isteği: MERNİS artık sadece
  // FarmerDetail.jsx'te değil, çiftçi EKLEME formunda da mevcut. Çiftçi
  // henüz yaratılmadığı için ÖN doğrulama yapılır (farmer_id GÖNDERİLMEZ —
  // /gov/mernis/verify sadece kontrol eder, yazmaz); kayıt gerçekten
  // oluşturulunca AYNI uç farmer_id İLE tekrar çağrılıp FarmerDetail.jsx'in
  // "MERNİS Doğrulandı" rozetiyle AYNI kalıcı alan (mernis_verified) yazılır.
  const [mernisYear, setMernisYear] = useState("");
  const [mernisBusy, setMernisBusy] = useState(false);
  const [mernisMsg, setMernisMsg] = useState("");
  const [mernisPreVerified, setMernisPreVerified] = useState(false);

  async function verifyMernisQuick() {
    if (!form.tc_no || form.tc_no.length !== 11) {
      setMernisMsg("Önce 11 haneli TC No girin."); return;
    }
    if (!mernisYear || String(mernisYear).length !== 4) {
      setMernisMsg("Doğum yılını 4 haneli girin (ör. 1985)."); return;
    }
    setMernisBusy(true);
    setMernisMsg("");
    const parts = (form.full_name || "").trim().split(/\s+/);
    const ad = parts.slice(0, -1).join(" ") || parts[0] || "";
    const soyad = parts.length > 1 ? parts[parts.length - 1] : "";
    try {
      const { data: r } = await api.post("/gov/mernis/verify", {
        tc_no: form.tc_no, ad, soyad, dogum_yili: Number(mernisYear),
      });
      setMernisMsg(r.detail);
      setMernisPreVerified(!!r.verified);
    } catch (err) {
      setMernisMsg(err.response?.data?.detail || "MERNİS doğrulaması başarısız.");
      setMernisPreVerified(false);
    } finally {
      setMernisBusy(false);
    }
  }

  useEffect(() => { api.get("/regions").then((r) => setRegions(r.data)); }, []);

  const load = () => {
    const params = {};
    if (q) params.q = q;
    if (regionFilter) params.region_id = regionFilter;
    if (karneFilter) params.karne = karneFilter;
    api.get("/farmers", { params }).then((r) => setFarmers(r.data));
  };
  useEffect(load, [q, regionFilter, karneFilter]);

  async function createFarmer(e) {
    e.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post("/farmers", { ...form, ...extra });
      if (mernisPreVerified && mernisYear) {
        // Ön doğrulama zaten geçtiyse (kimlik bilgisi DEĞİŞMEDİ), yeni
        // farmer_id ile AYNI uç tekrar çağrılıp kalıcı olarak işaretlenir.
        const parts = (form.full_name || "").trim().split(/\s+/);
        const ad = parts.slice(0, -1).join(" ") || parts[0] || "";
        const soyad = parts.length > 1 ? parts[parts.length - 1] : "";
        try {
          await api.post("/gov/mernis/verify", {
            tc_no: form.tc_no, ad, soyad, dogum_yili: Number(mernisYear), farmer_id: data.id,
          });
        } catch { /* kayıt zaten oluştu — doğrulama kaydı FarmerDetail.jsx'ten tekrar denenebilir */ }
      }
      setShowCreate(false);
      setForm({ full_name: "", tc_no: "", phone: "", email: "", village: "", region_id: "", iban: "", notes: "" });
      setExtra({});
      setMernisYear(""); setMernisMsg(""); setMernisPreVerified(false);
      load();
      nav(`/ciftciler/${data.id}`);
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || err.message));
    } finally { setCreating(false); }
  }

  return (
    <div className="p-8 max-w-[1600px]" data-testid="farmers-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">ÜYE SİCİLİ</div>
          <h1 className="font-display text-4xl">Çiftçiler</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">{farmers.length} kayıt</p>
        </div>
        <button onClick={() => setShowCreate(true)} data-testid="add-farmer-btn" className="btn btn-primary">
          <UserPlus size={16}/> Yeni Çiftçi
        </button>
      </header>

      {/* Denetim UI düzeltmesi (2026-07-24) — arama + bölge/karne + AI
          Asistanı + Gelişmiş Filtre artık TEK bir esnek (flex-wrap) satırda;
          önceden üç ayrı bloktu (arama+filtre kutuları / AI / Gelişmiş
          Filtre). AiAssistantBox ve FilterPanel kapalıyken zaten kompakt
          bir "btn btn-ghost" pill'i döndürüyor (bkz. o bileşenler), bu
          yüzden aynı satırda doğal olarak yan yana sığarlar; açıldıklarında
          kendi tam genişlikteki kartlarını satırın ALTINDA gösterirler. */}
      <div className="card p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[240px]">
            <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-dim)]"/>
            <input data-testid="farmer-search" className="input pl-11" placeholder="TC, ad, telefon veya üye no ara…"
              value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input w-auto min-w-[160px]" value={regionFilter} onChange={(e) => setRegionFilter(e.target.value)}>
            <option value="">Tüm bölgeler</option>
            {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <select className="input w-auto min-w-[160px]" value={karneFilter} onChange={(e) => setKarneFilter(e.target.value)}>
            <option value="">Tüm karneler</option>
            <option value="A">A — En iyi</option><option value="B">B — İyi</option>
            <option value="C">C — Orta</option><option value="D">D — Zayıf</option>
          </select>
          <AiAssistantBox module="farmers" onResults={(items) => setFarmers(items)}
                          placeholder='Örn: "Konya bölgesindeki A karneli 10 çiftçiyi göster"'
                          testId="farmers-ai" />
          <FilterPanel module="farmers" onResults={(items) => setFarmers(items)} />
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-4">Üye No</th><th className="p-4">Ad Soyad</th>
              <th className="p-4">Köy</th><th className="p-4">Telefon</th>
              <th className="p-4">Karne</th><th className="p-4">Üyelik</th><th className="p-4">Durum</th>
            </tr>
          </thead>
          <tbody>
            {farmers.map((f) => (
              <tr key={f.id} onClick={() => nav(`/ciftciler/${f.id}`)} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] transition-colors cursor-pointer" data-testid={`farmer-row-${f.member_no}`}>
                <td className="p-4 text-[var(--text-dim)] font-mono text-xs">{f.member_no}</td>
                <td className="p-4 font-medium">{f.full_name}</td>
                <td className="p-4">{f.village}</td>
                <td className="p-4 text-[var(--text-dim)] flex items-center gap-2"><Phone size={12}/>{f.phone}</td>
                {/* SON HAL — karne rozeti "neden bu skor?" sayfasına gider */}
                <td className="p-4" onClick={(e) => { e.stopPropagation(); nav(`/karne/${f.id}`); }}>
                  {/* 2026-08-19 — null-güvenli: karne notu henüz hesaplanmamış
                      (ör. dışarıdan içe aktarılmış) bir çiftçide
                      `undefined.toLowerCase()` TÜM LİSTEYİ çökertiyordu. */}
                  <span className={`badge badge-${(f.karne_score || "neutral").toLowerCase()} cursor-pointer`}
                        title="Karne analizini aç" data-testid={`karne-badge-${f.member_no}`}>
                    {f.karne_score || "—"} · {f.karne_points ?? "—"}
                  </span>
                </td>
                <td className="p-4 text-[var(--text-dim)]">{f.membership_year}</td>
                <td className="p-4"><span className={`badge ${f.status === "aktif" ? "badge-a" : "badge-neutral"}`}>{f.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {farmers.length === 0 && <div className="p-8 text-center text-[var(--text-dim)]">Kayıt bulunamadı</div>}
      </div>

      {/* YENİ ÇİFTÇİ MODAL */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowCreate(false)}>
          <div className="card max-w-xl w-full p-6 max-h-[90vh] overflow-y-auto scrollbar" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Yeni Çiftçi</h3>
              <button onClick={() => setShowCreate(false)}><X size={20}/></button>
            </div>
            <form onSubmit={createFarmer} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">AD SOYAD *</label>
                  <input required className="input" value={form.full_name} onChange={(e) => setForm({...form, full_name: e.target.value})} data-testid="new-farmer-name"/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">TC NO *</label>
                  <input required maxLength="11" className="input" value={form.tc_no}
                         onChange={(e) => { setForm({...form, tc_no: e.target.value}); setMernisPreVerified(false); }}/>
                  {/* Denetim eklentisi (2026-07-25) — MERNİS ön doğrulama */}
                  <div className="mt-1.5">
                    {mernisPreVerified ? (
                      <span className="badge badge-a text-[10px] inline-flex items-center gap-1" data-testid="new-farmer-mernis-verified">
                        <ShieldCheck size={11}/> MERNİS Doğrulandı
                      </span>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <input type="number" placeholder="Doğum yılı" className="input text-xs py-1 w-24"
                               value={mernisYear} onChange={(e) => setMernisYear(e.target.value)}
                               data-testid="new-farmer-mernis-year"/>
                        <button type="button" className="btn btn-ghost text-[11px] px-2 py-1 inline-flex items-center gap-1"
                                onClick={verifyMernisQuick} disabled={mernisBusy} data-testid="new-farmer-mernis-verify">
                          <ShieldAlert size={11}/> {mernisBusy ? "Doğrulanıyor…" : "MERNİS ile Doğrula"}
                        </button>
                      </div>
                    )}
                    {mernisMsg && <div className="text-[10px] text-[var(--text-dim)] mt-1">{mernisMsg}</div>}
                  </div>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">TELEFON *</label>
                  <input required className="input" value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value})} placeholder="05XX..."/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">E-POSTA</label>
                  <input className="input" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})}/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">KÖY *</label>
                  <input required className="input" value={form.village} onChange={(e) => setForm({...form, village: e.target.value})}/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">BÖLGE *</label>
                  <select required className="input" value={form.region_id} onChange={(e) => setForm({...form, region_id: e.target.value})}>
                    <option value="">Seç...</option>
                    {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                </div>
                <div className="md:col-span-2">
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">IBAN</label>
                  <input className="input" value={form.iban} onChange={(e) => setForm({...form, iban: e.target.value})} placeholder="TR..."/>
                </div>
                <div className="md:col-span-2">
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">NOTLAR</label>
                  <textarea className="input" rows="2" value={form.notes} onChange={(e) => setForm({...form, notes: e.target.value})}/>
                </div>
              </div>

              <DynamicFieldsSection
                module="farmers"
                values={extra}
                onChange={(key, val) => setExtra((e) => ({ ...e, [key]: val }))}
              />

              <button type="submit" disabled={creating} className="btn btn-primary w-full justify-center" data-testid="submit-farmer">
                {creating ? "Oluşturuluyor..." : "Çiftçiyi Kaydet"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
