/**
 * ÇİFTÇİLER SAYFASI — Liste + Yeni Çiftçi modalı
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { Search, UserPlus, Phone, X } from "lucide-react";
import DynamicFieldsSection from "@/components/DynamicFieldsSection";
import FilterPanel from "@/components/FilterPanel";

export default function Farmers() {
  const nav = useNavigate();
  const [farmers, setFarmers] = useState([]);
  const [regions, setRegions] = useState([]);
  const [q, setQ] = useState("");
  const [regionFilter, setRegionFilter] = useState("");
  const [karneFilter, setKarneFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  // Yeni çiftçi formu (çekirdek/zorunlu alanlar)
  const [form, setForm] = useState({
    full_name: "", tc_no: "", phone: "", email: "",
    village: "", region_id: "", iban: "", notes: ""
  });
  // Form Yönetimi'nden gelen dinamik alanlar (Sprint A1) — key: field_key
  const [extra, setExtra] = useState({});

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
      setShowCreate(false);
      setForm({ full_name: "", tc_no: "", phone: "", email: "", village: "", region_id: "", iban: "", notes: "" });
      setExtra({});
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

      <div className="card p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="relative md:col-span-2">
            <Search size={16} className="absolute left-4 top-3.5 text-[var(--text-dim)]"/>
            <input data-testid="farmer-search" className="input pl-11" placeholder="TC, ad, telefon veya üye no ara…"
              value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="input" value={regionFilter} onChange={(e) => setRegionFilter(e.target.value)}>
            <option value="">Tüm bölgeler</option>
            {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <select className="input" value={karneFilter} onChange={(e) => setKarneFilter(e.target.value)}>
            <option value="">Tüm karneler</option>
            <option value="A">A — En iyi</option><option value="B">B — İyi</option>
            <option value="C">C — Orta</option><option value="D">D — Zayıf</option>
          </select>
        </div>
      </div>

      <FilterPanel module="farmers" onResults={(items) => setFarmers(items)} />

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
                <td className="p-4"><span className={`badge badge-${f.karne_score.toLowerCase()}`}>{f.karne_score} · {f.karne_points}</span></td>
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
                  <input required maxLength="11" className="input" value={form.tc_no} onChange={(e) => setForm({...form, tc_no: e.target.value})}/>
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
