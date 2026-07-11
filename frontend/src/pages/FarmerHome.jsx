/**
 * ÇİFTÇİ SELF-SERVİS DASHBOARD'U
 *
 * Çiftçi kendi hesabıyla (ts-00001@ciftci.tr vb.) giriş yaptığında bu sayfayı görür.
 * Sadece KENDİ verilerini görür ve sulama olayı ekleyebilir.
 *
 * Veri eklediğinde:
 * 1. Kendi dashboard'u güncellenir
 * 2. Admin dashboard'unda toplam rakamlar değişir (sulama m³, vb.)
 * 3. Kantar randevuları & finansal bilgilerini görür
 */

import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { LogOut, Droplets, FileText, Wallet, Award, MapPin, Plus, Wheat, X, User, FlaskConical, Brain, Download, Upload, Camera, Loader2, HandCoins, Check, AlertTriangle, Bell, GraduationCap, PlayCircle, CheckCircle2 } from "lucide-react";

// IT-27 — Tercih Merkezi: kanal etiketleri (backend/channel_providers.py CHANNELS ile birebir).
const PREF_CHANNEL_LABELS = { sms: "SMS", email: "E-Posta", whatsapp: "WhatsApp", push: "Mobil Bildirim", voice: "Sesli Arama" };

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

// IT-21 — İcmal/Mutabakat Belgesi durumları (backend/reconciliation.py ile birebir).
const RECONCILIATION_STATUS_LABELS = { beklemede: "Beklemede", onaylandi: "Onaylandı", itiraz_edildi: "İtiraz Edildi" };
const RECONCILIATION_STATUS_BADGE = { beklemede: "badge-b", onaylandi: "badge-a", itiraz_edildi: "badge-d" };

// IT-29 — user_course_status 5 saklı durum (backend/lms.py ile birebir).
const LMS_STATUS_LABELS = {
  atandi: "Atandı", devam_ediyor: "Devam Ediyor", tamamlandi: "Tamamlandı",
  basarisiz: "Başarısız", suresi_doldu: "Süresi Doldu",
};

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

const API_BASE = process.env.REACT_APP_BACKEND_URL + "/api";

export default function FarmerHome() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [showIrrigation, setShowIrrigation] = useState(false);
  const [showSoil, setShowSoil] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [showAI, setShowAI] = useState(false);
  const [showSupport, setShowSupport] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef();

  // Destek Talebi (IT-18)
  const [myCycles, setMyCycles] = useState([]);
  const [supportTypes, setSupportTypes] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [supportForm, setSupportForm] = useState({ production_cycle_id: "", support_type_id: "", requested_amount: "", note: "" });

  // İcmal Belgesi (IT-21)
  const [myReconciliations, setMyReconciliations] = useState([]);
  const [reconciliationBusyId, setReconciliationBusyId] = useState(null);

  function loadReconciliations() {
    api.get("/portal/reconciliations").then((r) => setMyReconciliations(r.data));
  }

  function viewReconciliationPdf(id) {
    const token = localStorage.getItem("token");
    fetch(`${API_BASE}/reconciliation/${id}/pdf`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
      });
  }

  async function approveReconciliation(id) {
    setReconciliationBusyId(id);
    try {
      await api.post(`/reconciliation/${id}/approve`);
      loadReconciliations();
    } catch (err) {
      alert(err.response?.data?.detail || "Onaylanamadı");
    } finally { setReconciliationBusyId(null); }
  }

  async function objectReconciliation(id) {
    const reason = window.prompt("İtiraz sebebinizi yazın:");
    if (!reason) return;
    setReconciliationBusyId(id);
    try {
      await api.post(`/reconciliation/${id}/object`, { reason });
      loadReconciliations();
    } catch (err) {
      alert(err.response?.data?.detail || "İtiraz kaydedilemedi");
    } finally { setReconciliationBusyId(null); }
  }

  // Sulama formu
  const [form, setForm] = useState({
    parcel_id: "", date: new Date().toISOString().split("T")[0],
    method: "damla", water_m3: "", moisture_before: "", moisture_after: ""
  });

  // Toprak formu
  const [soilForm, setSoilForm] = useState({
    parcel_id: "", date: new Date().toISOString().split("T")[0],
    lab_name: "Konya Tarım Lab", ph: "7.0", ec: "0.8",
    organic_matter_pct: "2.5", n_ppm: "40", p_ppm: "20", k_ppm: "250",
    recommendation: ""
  });

  // Profil formu
  const [profileForm, setProfileForm] = useState({ phone: "", email: "", iban: "", village: "" });

  // AI Hastalık tespiti
  const [photo, setPhoto] = useState(null);
  const [aiResult, setAiResult] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  // Atanan formlar
  const [myForms, setMyForms] = useState([]);

  // İletişim Tercihlerim (IT-27 — Tercih Merkezi self-servisi)
  const [prefs, setPrefs] = useState(null);
  const [prefsSaving, setPrefsSaving] = useState(false);
  const loadPrefs = () => api.get("/portal/communication-preferences").then((r) => setPrefs(r.data));

  // Eğitimlerim (IT-29 — Farmer LMS)
  const [myCourses, setMyCourses] = useState([]);
  const [openCourseId, setOpenCourseId] = useState(null);
  const loadMyCourses = () => api.get("/lms/my-courses").then((r) => setMyCourses(r.data));
  async function startCourse(statusId) {
    await api.post(`/lms/my-courses/${statusId}/start`);
    loadMyCourses();
  }
  async function toggleCourseContent(statusId, contentId, completed) {
    await api.post(`/lms/my-courses/${statusId}/contents/${contentId}/complete`, { completed: !completed });
    loadMyCourses();
  }
  async function togglePrefChannel(channel) {
    const updated = { ...prefs.channels_enabled, [channel]: !prefs.channels_enabled[channel] };
    setPrefs((p) => ({ ...p, channels_enabled: updated }));
    setPrefsSaving(true);
    try {
      await api.put("/portal/communication-preferences", { channels_enabled: updated });
    } finally {
      setPrefsSaving(false);
    }
  }
  async function togglePrefFlag(key) {
    const value = !prefs[key];
    setPrefs((p) => ({ ...p, [key]: value }));
    setPrefsSaving(true);
    try {
      await api.put("/portal/communication-preferences", { [key]: value });
    } finally {
      setPrefsSaving(false);
    }
  }

  const loadData = () => {
    api.get("/farmer/my-dashboard").then((r) => {
      setData(r.data);
      if (r.data.parcels.length > 0 && !form.parcel_id) {
        setForm((f) => ({ ...f, parcel_id: r.data.parcels[0].id }));
        setSoilForm((f) => ({ ...f, parcel_id: r.data.parcels[0].id }));
      }
      setProfileForm({
        phone: r.data.farmer.phone || "", email: r.data.farmer.email || "",
        iban: r.data.farmer.iban || "", village: r.data.farmer.village || ""
      });
    }).catch((err) => { if (err.response?.status === 403) nav("/login"); });
    api.get("/farmer/my-forms").then((r) => setMyForms(r.data));
    api.get("/portal/production-cycles").then((r) => {
      setMyCycles(r.data);
      if (r.data.length > 0) setSupportForm((f) => ({ ...f, production_cycle_id: f.production_cycle_id || r.data[0].id }));
    });
    api.get("/portal/support-types").then((r) => {
      setSupportTypes(r.data);
      if (r.data.length > 0) setSupportForm((f) => ({ ...f, support_type_id: f.support_type_id || r.data[0].id }));
    });
    api.get("/portal/support-requests").then((r) => setMyRequests(r.data));
  };

  useEffect(() => { loadData(); loadReconciliations(); loadPrefs(); loadMyCourses(); }, []);

  function logout() { localStorage.clear(); nav("/login"); }

  async function submitIrrigation(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/farmer/irrigation", {
        parcel_id: form.parcel_id, date: form.date, method: form.method,
        water_m3: parseFloat(form.water_m3),
        moisture_before: form.moisture_before ? parseInt(form.moisture_before) : null,
        moisture_after: form.moisture_after ? parseInt(form.moisture_after) : null
      });
      await loadData();
      setShowIrrigation(false);
      setForm({ ...form, water_m3: "", moisture_before: "", moisture_after: "" });
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || "Kayıt yapılamadı"));
    } finally { setSubmitting(false); }
  }

  async function submitSoil(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/farmer/soil-sample", {
        parcel_id: soilForm.parcel_id, date: soilForm.date, lab_name: soilForm.lab_name,
        ph: parseFloat(soilForm.ph), ec: parseFloat(soilForm.ec),
        organic_matter_pct: parseFloat(soilForm.organic_matter_pct),
        n_ppm: parseInt(soilForm.n_ppm), p_ppm: parseInt(soilForm.p_ppm),
        k_ppm: parseInt(soilForm.k_ppm), recommendation: soilForm.recommendation || null
      });
      await loadData();
      setShowSoil(false);
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || "Kayıt yapılamadı"));
    } finally { setSubmitting(false); }
  }

  async function submitSupport(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/portal/support-requests", {
        production_cycle_id: supportForm.production_cycle_id,
        support_type_id: supportForm.support_type_id,
        requested_amount: parseFloat(supportForm.requested_amount),
        note: supportForm.note || null,
      });
      await loadData();
      setShowSupport(false);
      setSupportForm((f) => ({ ...f, requested_amount: "", note: "" }));
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || "Talep oluşturulamadı"));
    } finally { setSubmitting(false); }
  }

  async function submitProfile(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.put("/farmer/my-profile", profileForm);
      await loadData();
      setShowProfile(false);
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || err.message));
    } finally { setSubmitting(false); }
  }

  function onPhotoSelect(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => setPhoto(ev.target.result);
    reader.readAsDataURL(f);
  }

  async function analyzeAI() {
    if (!photo) return;
    setAiLoading(true);
    setAiResult(null);
    try {
      const { data: res } = await api.post("/ai/disease-detect", {
        image_base64: photo, parcel_id: form.parcel_id || null
      });
      let parsed = null;
      try {
        const m = res.result.match(/\{[\s\S]*\}/);
        if (m) parsed = JSON.parse(m[0]);
      } catch {}
      setAiResult(parsed || { raw: res.result });
    } catch (err) {
      alert("AI hatası: " + (err.response?.data?.detail || err.message));
    } finally { setAiLoading(false); }
  }

  function downloadMustahsil() {
    if (!data) return;
    const token = localStorage.getItem("token");
    // Token'la birlikte yeni sekmede aç
    fetch(`${API_BASE}/musthsil/${data.farmer.id}/2025`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(r => r.blob()).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mustahsil-${data.farmer.member_no}-2025.pdf`;
      a.click();
    });
  }

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const { farmer, stats, parcels, contracts, yields, irrigation_events, soil_samples, finance, appointments } = data;

  // Verim trend datası (yıl × ton)
  const yieldTrend = yields.reduce((acc, y) => {
    const ex = acc.find((x) => x.year === y.season);
    if (ex) { ex.actual += y.actual_ton; ex.expected += y.expected_ton; }
    else acc.push({ year: y.season, actual: y.actual_ton, expected: y.expected_ton });
    return acc;
  }, []).sort((a, b) => a.year - b.year);

  return (
    <div className="min-h-screen bg-[var(--bg)] grain" data-testid="farmer-home">
      {/* TOP BAR */}
      <header className="border-b border-[var(--border)] bg-[#070b09] sticky top-0 z-30">
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <Wheat size={18} className="text-[#052e16]"/>
            </div>
            <div>
              <div className="font-display text-lg leading-none">Çiftçi Portalı</div>
              <div className="text-[10px] text-[var(--text-dim)] tracking-widest mt-0.5">{farmer.member_no}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right hidden md:block">
              <div className="text-sm font-medium">{farmer.full_name}</div>
              <div className="text-xs text-[var(--text-dim)]">{farmer.village}</div>
            </div>
            <button onClick={logout} data-testid="farmer-logout" className="btn btn-ghost text-sm">
              <LogOut size={14}/> Çıkış
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto p-6">
        {/* HOŞGELDİN */}
        <div className="mb-6">
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">2025 SEZONU</div>
          <h1 className="font-display text-3xl">Hoş geldin, {farmer.full_name.split(" ")[0]}</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">Üyelik karne notunuz: <span className={`badge badge-${farmer.karne_score.toLowerCase()}`}>{farmer.karne_score} · {farmer.karne_points} puan</span></p>
        </div>

        {/* KPI KARTLARI */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="card p-4">
            <MapPin className="text-[var(--primary)] mb-2" size={20}/>
            <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase">Parsel</div>
            <div className="font-display text-2xl">{stats.parcels_count}</div>
            <div className="text-xs text-[var(--text-dim)]">{fmt(stats.total_area_dekar)} dekar</div>
          </div>
          <div className="card p-4">
            <FileText className="text-blue-400 mb-2" size={20}/>
            <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase">Sözleşme 2025</div>
            <div className="font-display text-2xl">{stats.active_contracts}</div>
            <div className="text-xs text-[var(--text-dim)]">{fmt(stats.expected_ton_2025)} ton hedef</div>
          </div>
          <div className="card p-4">
            <Droplets className="text-cyan-400 mb-2" size={20}/>
            <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase">Su Kullanımı</div>
            <div className="font-display text-2xl">{fmt(stats.total_water_m3)}</div>
            <div className="text-xs text-[var(--text-dim)]">{stats.irrigation_events_count} sulama</div>
          </div>
          <div className="card p-4">
            <Wallet className={stats.balance >= 0 ? "text-[var(--primary)]" : "text-red-400"} size={20}/>
            <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase mt-2">Bakiye</div>
            <div className={`font-display text-2xl ${stats.balance >= 0 ? "text-[var(--primary)]" : "text-red-400"}`}>
              {fmt(stats.balance)} ₺
            </div>
          </div>
        </div>

        {/* GÖREVLERİM (atanmış formlar) */}
        {myForms.length > 0 && (
          <div className="card p-5 mb-6 border-amber-400/30 bg-amber-400/5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-lg flex items-center gap-2">
                <span className="text-amber-400">📋</span> Görevlerim
                <span className="text-xs bg-amber-400/20 text-amber-400 px-2 py-0.5 rounded-full">{myForms.filter(f => f.status === "atandı").length} bekleyen</span>
              </h3>
            </div>
            <div className="space-y-2">
              {myForms.slice(0, 5).map((m) => (
                <div key={m.id} className="flex items-center justify-between p-3 bg-[var(--surface-2)] rounded-lg">
                  <div className="flex-1">
                    <div className="text-sm font-medium">{m.form?.title}</div>
                    <div className="text-xs text-[var(--text-dim)]">{m.form?.description}</div>
                  </div>
                  {m.status === "tamamlandı" ? (
                    <span className="badge badge-a">✓ Tamamlandı</span>
                  ) : (
                    <button onClick={() => nav(`/ciftci/form/${m.form_id}`)} className="btn btn-primary text-xs" data-testid={`fill-form-${m.form_id}`}>
                      Formu Doldur
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AKSİYON BUTONLARI */}
        <div className="card p-5 mb-6 bg-gradient-to-r from-[var(--primary)]/10 to-transparent border-[var(--primary)]/30">
          <h3 className="font-display text-lg mb-3">Hızlı Aksiyonlar</h3>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setShowIrrigation(true)} className="btn btn-primary text-sm" data-testid="add-irrigation-btn">
              <Droplets size={14}/> Sulama Ekle
            </button>
            <button onClick={() => setShowSoil(true)} className="btn btn-ghost text-sm" data-testid="add-soil-btn">
              <FlaskConical size={14}/> Toprak Analizi
            </button>
            <button onClick={() => setShowSupport(true)} className="btn btn-ghost text-sm" data-testid="add-support-request-btn">
              <HandCoins size={14}/> Destek Talebi
            </button>
            <button onClick={() => setShowAI(true)} className="btn btn-ghost text-sm" data-testid="open-ai-btn">
              <Brain size={14}/> AI Hastalık Tespiti
            </button>
            <button onClick={() => setShowProfile(true)} className="btn btn-ghost text-sm" data-testid="edit-profile-btn">
              <User size={14}/> Profilimi Düzenle
            </button>
            <button onClick={downloadMustahsil} className="btn btn-ghost text-sm" data-testid="download-mustahsil-btn">
              <Download size={14}/> Müstahsil Makbuzu (PDF)
            </button>
          </div>
        </div>

        {/* VERİM TRENDİ + PARSELLER */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div className="card p-5 lg:col-span-2">
            <h3 className="font-display text-lg mb-4">Yıllık Verim Karşılaştırması</h3>
            {yieldTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={yieldTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
                  <XAxis dataKey="year" stroke="#97a8a0"/>
                  <YAxis stroke="#97a8a0"/>
                  <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
                  <Bar dataKey="expected" fill="#fbbf24" name="Beklenen (ton)" radius={[6,6,0,0]}/>
                  <Bar dataKey="actual" fill="#4ade80" name="Gerçekleşen (ton)" radius={[6,6,0,0]}/>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="py-12 text-center text-[var(--text-dim)]">Henüz verim verisi yok</div>}
          </div>

          <div className="card p-5">
            <h3 className="font-display text-lg mb-3">Parsellerim</h3>
            <div className="space-y-2 max-h-[260px] overflow-y-auto scrollbar">
              {parcels.map((p) => (
                <div key={p.id} className="p-3 bg-[var(--surface-2)] rounded-lg">
                  <div className="flex items-start justify-between">
                    <div className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</div>
                    <div className="text-xs text-[var(--primary)]">{p.area_dekar} da</div>
                  </div>
                  <div className="text-sm mt-1">{p.name}</div>
                  <div className="text-xs text-[var(--text-dim)] mt-0.5">{p.irrigation} · {p.soil_type}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* SON KAYITLAR — Sulama + Finans + Randevular */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="card p-5">
            <h3 className="font-display text-base mb-3 flex items-center gap-2"><Droplets size={16} className="text-cyan-400"/>Son Sulama Kayıtları</h3>
            <div className="space-y-2">
              {irrigation_events.slice(0, 6).map((e) => (
                <div key={e.id} className="flex justify-between text-sm border-b border-[var(--border)] pb-2">
                  <div>
                    <div>{e.date}</div>
                    <div className="text-xs text-[var(--text-dim)] capitalize">{e.method}</div>
                  </div>
                  <div className="text-[var(--primary)] font-medium">{e.water_m3} m³</div>
                </div>
              ))}
              {irrigation_events.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz kayıt yok</div>}
            </div>
          </div>

          <div className="card p-5">
            <h3 className="font-display text-base mb-3 flex items-center gap-2"><Wallet size={16} className="text-amber-400"/>Finansal Hareketler</h3>
            <div className="space-y-2">
              {finance.slice(0, 6).map((f) => (
                <div key={f.id} className="flex justify-between text-sm border-b border-[var(--border)] pb-2">
                  <div>
                    <div>{f.type}</div>
                    <div className="text-xs text-[var(--text-dim)]">{f.date}</div>
                  </div>
                  <div className={`font-mono ${f.amount > 0 ? "text-[var(--primary)]" : "text-red-400"}`}>{fmt(f.amount)} ₺</div>
                </div>
              ))}
              {finance.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Hareket yok</div>}
            </div>
          </div>

          <div className="card p-5">
            <h3 className="font-display text-base mb-3 flex items-center gap-2"><Award size={16} className="text-emerald-400"/>Kantar Randevularım</h3>
            <div className="space-y-2">
              {appointments.slice(0, 6).map((a) => (
                <div key={a.id} className="text-sm border-b border-[var(--border)] pb-2">
                  <div className="flex justify-between">
                    <div className="font-mono text-xs">{a.truck_plate}</div>
                    <span className="badge badge-b text-[10px]">{a.status}</span>
                  </div>
                  <div className="text-xs text-[var(--text-dim)] mt-1">{new Date(a.scheduled_at).toLocaleString("tr-TR")}</div>
                </div>
              ))}
              {appointments.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Randevu yok</div>}
            </div>
          </div>
        </div>

        {/* DESTEK TALEPLERİM (IT-18) */}
        <div className="card p-5 mt-4">
          <h3 className="font-display text-base mb-3 flex items-center gap-2"><HandCoins size={16} className="text-amber-400"/>Destek Taleplerim</h3>
          <div className="space-y-2">
            {myRequests.slice(0, 8).map((r) => {
              const stype = supportTypes.find((t) => t.id === r.support_type_id);
              return (
                <div key={r.id} className="flex justify-between items-center text-sm border-b border-[var(--border)] pb-2">
                  <div>
                    <div>{stype ? stype.name : r.support_type_id} — {r.requested_amount} {r.unit}</div>
                    <div className="text-xs text-[var(--text-dim)]">{(r.requested_at || "").slice(0, 10)}</div>
                  </div>
                  <span className={`badge ${SUPPORT_STATUS_BADGE[r.status] || "badge-neutral"}`}>{SUPPORT_STATUS_LABELS[r.status] || r.status}</span>
                </div>
              );
            })}
            {myRequests.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz destek talebiniz yok</div>}
          </div>
        </div>

        {/* İCMAL BELGELERİM (IT-21) */}
        <div className="card p-5 mt-4">
          <h3 className="font-display text-base mb-3 flex items-center gap-2"><FileText size={16} className="text-[var(--primary)]"/>İcmal Belgelerim</h3>
          <div className="space-y-3">
            {myReconciliations.map((rc) => (
              <div key={rc.id} className="p-3 bg-[var(--surface-2)] rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm">{(rc.generated_at || "").slice(0, 10)}</div>
                  <span className={`badge ${RECONCILIATION_STATUS_BADGE[rc.status] || "badge-neutral"}`}>
                    {RECONCILIATION_STATUS_LABELS[rc.status] || rc.status}
                  </span>
                </div>
                {rc.objection_reason && (
                  <div className="text-xs text-red-400 mb-2">İtiraz: {rc.objection_reason}</div>
                )}
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => viewReconciliationPdf(rc.id)} className="btn btn-ghost text-xs" data-testid={`reconciliation-pdf-${rc.id}`}>
                    <FileText size={12}/> PDF Görüntüle
                  </button>
                  {rc.status === "beklemede" && (
                    <>
                      <button onClick={() => approveReconciliation(rc.id)} disabled={reconciliationBusyId === rc.id}
                              className="btn btn-primary text-xs" data-testid={`reconciliation-approve-${rc.id}`}>
                        <Check size={12}/> Onayla
                      </button>
                      <button onClick={() => objectReconciliation(rc.id)} disabled={reconciliationBusyId === rc.id}
                              className="btn btn-ghost text-red-400 text-xs" data-testid={`reconciliation-object-${rc.id}`}>
                        <AlertTriangle size={12}/> İtiraz Et
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {myReconciliations.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz icmal belgeniz yok</div>}
          </div>
        </div>

        {/* İLETİŞİM TERCİHLERİM (IT-27 — Tercih Merkezi self-servisi) */}
        {prefs && (
          <div className="card p-5 mt-4" data-testid="communication-preferences-card">
            <h3 className="font-display text-base mb-3 flex items-center gap-2">
              <Bell size={16} className="text-[var(--primary)]"/>İletişim Tercihlerim{prefsSaving && <Loader2 size={12} className="animate-spin text-[var(--text-dim)]"/>}
            </h3>
            <div className="text-xs text-[var(--text-dim)] mb-3">
              Hangi kanaldan bilgilendirme almak istediğinizi seçin. Kapattığınız bir kanaldan size mesaj gönderilmez.
            </div>
            <div className="flex flex-wrap gap-2 mb-4">
              {Object.entries(PREF_CHANNEL_LABELS).map(([key, label]) => (
                <button key={key} onClick={() => togglePrefChannel(key)}
                        className={`badge ${prefs.channels_enabled?.[key] !== false ? "badge-a" : "badge-d"}`}
                        data-testid={`pref-channel-${key}`}>
                  {label}: {prefs.channels_enabled?.[key] !== false ? "Açık" : "Kapalı"}
                </button>
              ))}
            </div>
            <div className="space-y-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prefs.allow_operational_messages !== false}
                       onChange={() => togglePrefFlag("allow_operational_messages")}/>
                Operasyonel bildirimler (hakediş, görev, sözleşme vb.)
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prefs.allow_campaign_messages !== false}
                       onChange={() => togglePrefFlag("allow_campaign_messages")}/>
                Kampanya mesajları
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={prefs.allow_weekend !== false}
                       onChange={() => togglePrefFlag("allow_weekend")}/>
                Hafta sonu iletişime izin ver
              </label>
            </div>
          </div>
        )}

        {/* EĞİTİMLERİM (IT-29 — Farmer LMS) */}
        <div className="card p-5 mt-4" data-testid="my-courses-card">
          <h3 className="font-display text-base mb-3 flex items-center gap-2">
            <GraduationCap size={16} className="text-[var(--primary)]"/>Eğitimlerim
          </h3>
          <div className="space-y-3">
            {myCourses.map((s) => (
              <div key={s.id} className="p-3 bg-[var(--surface-2)] rounded-lg">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-sm flex items-center gap-2">
                    {s.course.title}
                    {s.course.is_mandatory && <span className="badge badge-d text-[10px]">Zorunlu</span>}
                  </div>
                  <span className={`badge ${s.status === "tamamlandi" ? "badge-a" : s.status === "suresi_doldu" || s.status === "basarisiz" ? "badge-d" : "badge-neutral"}`}>
                    {LMS_STATUS_LABELS[s.status] || s.status}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {s.status === "atandi" && (
                    <button onClick={() => startCourse(s.id)} className="btn btn-primary text-xs" data-testid={`course-start-${s.id}`}>
                      <PlayCircle size={12}/> Başla
                    </button>
                  )}
                  {(s.status === "devam_ediyor" || s.status === "atandi") && (
                    <button onClick={() => setOpenCourseId(openCourseId === s.id ? null : s.id)} className="btn btn-ghost text-xs">
                      {openCourseId === s.id ? "İçerikleri Gizle" : "İçerikleri Göster"}
                    </button>
                  )}
                </div>
                {openCourseId === s.id && (
                  <div className="mt-2 space-y-1.5">
                    {(s.course.contents || []).map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={!!(s.content_progress || {})[c.id]}
                               onChange={() => toggleCourseContent(s.id, c.id, !!(s.content_progress || {})[c.id])}/>
                        {c.title}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {myCourses.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Size atanmış bir eğitim yok</div>}
          </div>
        </div>
      </div>

      {/* MODAL — Yeni Sulama Kaydı */}
      {showIrrigation && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowIrrigation(false)}>
          <div className="card max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Yeni Sulama Kaydı</h3>
              <button onClick={() => setShowIrrigation(false)} className="text-[var(--text-dim)] hover:text-white"><X size={20}/></button>
            </div>
            <form onSubmit={submitIrrigation} className="space-y-3">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">PARSEL</label>
                <select className="input" value={form.parcel_id} onChange={(e) => setForm({...form, parcel_id: e.target.value})} required>
                  {parcels.map((p) => <option key={p.id} value={p.id}>{p.parcel_code} — {p.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">TARİH</label>
                  <input type="date" className="input" value={form.date} onChange={(e) => setForm({...form, date: e.target.value})} required/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">YÖNTEM</label>
                  <select className="input" value={form.method} onChange={(e) => setForm({...form, method: e.target.value})}>
                    <option value="damla">Damla</option>
                    <option value="yağmurlama">Yağmurlama</option>
                    <option value="karık">Karık</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">SU MİKTARI (m³)</label>
                <input type="number" step="0.1" className="input" value={form.water_m3}
                       onChange={(e) => setForm({...form, water_m3: e.target.value})}
                       placeholder="Örn: 25.5" required data-testid="water-amount-input"/>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">NEM ÖNCESİ (%)</label>
                  <input type="number" className="input" value={form.moisture_before}
                         onChange={(e) => setForm({...form, moisture_before: e.target.value})} placeholder="20"/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">NEM SONRASI (%)</label>
                  <input type="number" className="input" value={form.moisture_after}
                         onChange={(e) => setForm({...form, moisture_after: e.target.value})} placeholder="70"/>
                </div>
              </div>
              <button type="submit" disabled={submitting} className="btn btn-primary w-full justify-center" data-testid="submit-irrigation">
                {submitting ? "Kaydediliyor..." : "Kaydı Ekle"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* MODAL — Toprak Analizi */}
      {showSoil && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowSoil(false)}>
          <div className="card max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto scrollbar" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Toprak Analiz Sonucu</h3>
              <button onClick={() => setShowSoil(false)}><X size={20}/></button>
            </div>
            <form onSubmit={submitSoil} className="space-y-3">
              <select className="input" value={soilForm.parcel_id} onChange={(e) => setSoilForm({...soilForm, parcel_id: e.target.value})} required>
                {data.parcels.map((p) => <option key={p.id} value={p.id}>{p.parcel_code} — {p.name}</option>)}
              </select>
              <div className="grid grid-cols-2 gap-3">
                <input type="date" className="input" value={soilForm.date} onChange={(e) => setSoilForm({...soilForm, date: e.target.value})}/>
                <input type="text" className="input" placeholder="Lab adı" value={soilForm.lab_name} onChange={(e) => setSoilForm({...soilForm, lab_name: e.target.value})}/>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div><label className="text-[10px] text-[var(--text-dim)]">pH</label><input type="number" step="0.1" className="input" value={soilForm.ph} onChange={(e) => setSoilForm({...soilForm, ph: e.target.value})}/></div>
                <div><label className="text-[10px] text-[var(--text-dim)]">EC</label><input type="number" step="0.1" className="input" value={soilForm.ec} onChange={(e) => setSoilForm({...soilForm, ec: e.target.value})}/></div>
                <div><label className="text-[10px] text-[var(--text-dim)]">OM %</label><input type="number" step="0.1" className="input" value={soilForm.organic_matter_pct} onChange={(e) => setSoilForm({...soilForm, organic_matter_pct: e.target.value})}/></div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div><label className="text-[10px] text-[var(--text-dim)]">N (ppm)</label><input type="number" className="input" value={soilForm.n_ppm} onChange={(e) => setSoilForm({...soilForm, n_ppm: e.target.value})}/></div>
                <div><label className="text-[10px] text-[var(--text-dim)]">P (ppm)</label><input type="number" className="input" value={soilForm.p_ppm} onChange={(e) => setSoilForm({...soilForm, p_ppm: e.target.value})}/></div>
                <div><label className="text-[10px] text-[var(--text-dim)]">K (ppm)</label><input type="number" className="input" value={soilForm.k_ppm} onChange={(e) => setSoilForm({...soilForm, k_ppm: e.target.value})}/></div>
              </div>
              <textarea className="input" rows="2" placeholder="Lab önerisi (opsiyonel)" value={soilForm.recommendation} onChange={(e) => setSoilForm({...soilForm, recommendation: e.target.value})}/>
              <button type="submit" disabled={submitting} className="btn btn-primary w-full justify-center">{submitting ? "Kaydediliyor..." : "Kaydet"}</button>
            </form>
          </div>
        </div>
      )}

      {/* MODAL — Destek Talebi (IT-18) */}
      {showSupport && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowSupport(false)}>
          <div className="card max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Yeni Destek Talebi</h3>
              <button onClick={() => setShowSupport(false)}><X size={20}/></button>
            </div>
            {myCycles.length === 0 || supportTypes.length === 0 ? (
              <div className="text-sm text-[var(--text-dim)] py-4 text-center">
                {myCycles.length === 0 ? "Aktif üretim sezonunuz bulunmuyor." : "Şu an tanımlı destek tipi yok."}
              </div>
            ) : (
              <form onSubmit={submitSupport} className="space-y-3">
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">ÜRETİM SEZONU</label>
                  <select className="input" value={supportForm.production_cycle_id}
                          onChange={(e) => setSupportForm({ ...supportForm, production_cycle_id: e.target.value })} required>
                    {myCycles.map((c) => <option key={c.id} value={c.id}>{c.year} — {c.season} ({c.crop})</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">DESTEK TİPİ</label>
                  <select className="input" value={supportForm.support_type_id}
                          onChange={(e) => setSupportForm({ ...supportForm, support_type_id: e.target.value })} required>
                    {supportTypes.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.unit})</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">MİKTAR</label>
                  <input type="number" step="0.01" className="input" value={supportForm.requested_amount}
                         onChange={(e) => setSupportForm({ ...supportForm, requested_amount: e.target.value })}
                         placeholder="Örn: 200" required data-testid="support-amount-input"/>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-dim)] mb-1.5 block">NOT (opsiyonel)</label>
                  <textarea className="input" rows="2" value={supportForm.note}
                            onChange={(e) => setSupportForm({ ...supportForm, note: e.target.value })}/>
                </div>
                <button type="submit" disabled={submitting} className="btn btn-primary w-full justify-center" data-testid="submit-support-request">
                  {submitting ? "Gönderiliyor..." : "Talebi Gönder"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* MODAL — Profil Düzenleme */}
      {showProfile && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowProfile(false)}>
          <div className="card max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Profilimi Düzenle</h3>
              <button onClick={() => setShowProfile(false)}><X size={20}/></button>
            </div>
            <form onSubmit={submitProfile} className="space-y-3">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">TELEFON</label>
                <input className="input" value={profileForm.phone} onChange={(e) => setProfileForm({...profileForm, phone: e.target.value})}/>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">E-POSTA</label>
                <input className="input" value={profileForm.email} onChange={(e) => setProfileForm({...profileForm, email: e.target.value})}/>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">IBAN</label>
                <input className="input" value={profileForm.iban} onChange={(e) => setProfileForm({...profileForm, iban: e.target.value})}/>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">KÖY</label>
                <input className="input" value={profileForm.village} onChange={(e) => setProfileForm({...profileForm, village: e.target.value})}/>
              </div>
              <button type="submit" disabled={submitting} className="btn btn-primary w-full justify-center">{submitting ? "..." : "Güncelle"}</button>
            </form>
          </div>
        </div>
      )}

      {/* MODAL — AI Hastalık Tespiti */}
      {showAI && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4 fade-in" onClick={() => setShowAI(false)}>
          <div className="card max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto scrollbar" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl flex items-center gap-2"><Brain size={20} className="text-purple-400"/>AI Hastalık Tespiti</h3>
              <button onClick={() => { setShowAI(false); setPhoto(null); setAiResult(null); }}><X size={20}/></button>
            </div>
            {!photo ? (
              <div onClick={() => fileRef.current?.click()} className="border-2 border-dashed border-[var(--border)] rounded-xl p-8 text-center cursor-pointer hover:border-[var(--primary)]">
                <Camera size={32} className="mx-auto text-[var(--text-dim)] mb-3"/>
                <div className="text-sm">Bitki fotoğrafı çek/seç</div>
              </div>
            ) : (
              <div>
                <img src={photo} alt="" className="w-full rounded-xl mb-3 max-h-[250px] object-contain bg-[var(--surface-2)]"/>
                <div className="flex gap-2 mb-3">
                  <button onClick={() => { setPhoto(null); setAiResult(null); }} className="btn btn-ghost flex-1 justify-center text-sm">Değiştir</button>
                  <button onClick={analyzeAI} disabled={aiLoading} className="btn btn-primary flex-1 justify-center text-sm">
                    {aiLoading ? <><Loader2 size={14} className="animate-spin"/> Analiz...</> : <><Brain size={14}/> Analiz Et</>}
                  </button>
                </div>
              </div>
            )}
            <input ref={fileRef} type="file" accept="image/*" capture="environment" onChange={onPhotoSelect} className="hidden"/>
            {aiResult && (
              <div className="space-y-2 mt-4 fade-in">
                {aiResult.plant && <div className="p-3 bg-[var(--surface-2)] rounded-lg"><span className="text-xs text-[var(--text-dim)]">BİTKİ:</span> <strong>{aiResult.plant}</strong></div>}
                {aiResult.disease && <div className="p-3 bg-amber-500/10 rounded-lg"><span className="text-xs text-[var(--text-dim)]">HASTALIK:</span> <strong className="text-amber-400">{aiResult.disease}</strong></div>}
                {aiResult.severity && <div className="p-3 bg-[var(--surface-2)] rounded-lg"><span className="text-xs text-[var(--text-dim)]">ŞİDDET:</span> <strong>{aiResult.severity}</strong></div>}
                {aiResult.action && <div className="p-3 bg-[var(--primary)]/10 rounded-lg text-sm"><span className="text-xs text-[var(--primary)]">ÖNERİ:</span> {aiResult.action}</div>}
                {aiResult.raw && <div className="p-3 bg-[var(--surface-2)] rounded-lg text-xs whitespace-pre-wrap">{aiResult.raw}</div>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
