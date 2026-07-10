/**
 * SAHA VERİ TOPLAMA — Form Modülü Sayfaları (M18)
 *
 * - FormListesi: tüm formlar (admin)
 * - FormBuilder: form oluştur/düzenle (drag-sıralama)
 * - FormDoldur: kullanıcı/çiftçi form doldurma (GPS+foto+video)
 * - PublicFormDoldur: token'la public erişim
 * - FormDashboard: yanıt analiz + widget'lar
 */
import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/api";
import {
  Plus, Trash2, GripVertical, Save, Share2, Send, Eye, BarChart3,
  MapPin, Camera, Star, Calendar, Type, AlignLeft, Hash, List, CheckSquare,
  ChevronUp, ChevronDown, Link2, Loader2, X, Image as ImageIcon, ClipboardList
} from "lucide-react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

// Alan tipleri kataloğu
const FIELD_TYPES = [
  { id: "text", icon: Type, label: "Kısa Metin" },
  { id: "textarea", icon: AlignLeft, label: "Uzun Metin" },
  { id: "number", icon: Hash, label: "Sayı" },
  { id: "select", icon: List, label: "Tek Seçim" },
  { id: "multiselect", icon: CheckSquare, label: "Çoklu Seçim" },
  { id: "yesno", icon: CheckSquare, label: "Evet/Hayır" },
  { id: "rating", icon: Star, label: "Yıldız (1-5)" },
  { id: "date", icon: Calendar, label: "Tarih" },
  { id: "gps", icon: MapPin, label: "GPS Konum" },
  { id: "photo", icon: Camera, label: "Fotoğraf" },
  { id: "signature", icon: Type, label: "İmza" },
];

// =====================================================================
// FORM LİSTESİ (Admin)
// =====================================================================
export function FormListesi() {
  const nav = useNavigate();
  const [forms, setForms] = useState([]);

  const load = () => api.get("/forms").then((r) => setForms(r.data));
  useEffect(load, []);

  async function deleteForm(id) {
    if (!window.confirm("Form ve tüm yanıtları silinecek. Emin misin?")) return;
    await api.delete(`/forms/${id}`);
    load();
  }

  function shareLink(form) {
    if (form.share_mode === "public" && form.public_token) {
      const link = `${window.location.origin}/form/${form.public_token}`;
      navigator.clipboard.writeText(link);
      alert("Public link kopyalandı:\n" + link);
    } else {
      alert("Bu form public modunda değil");
    }
  }

  return (
    <div className="p-8 max-w-[1600px]" data-testid="form-list-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M18 · SAHA VERİ TOPLAMA</div>
          <h1 className="font-display text-4xl">Formlar & Anketler</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">{forms.length} aktif form</p>
        </div>
        <button onClick={() => nav("/formlar/yeni")} className="btn btn-primary" data-testid="new-form-btn">
          <Plus size={16}/> Yeni Form
        </button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {forms.map((f) => (
          <div key={f.id} className="card p-5 card-hover" data-testid={`form-card-${f.id}`}>
            <div className="flex items-start justify-between mb-3">
              <span className={`badge ${f.share_mode === "public" ? "badge-a" : f.share_mode === "internal" ? "badge-b" : "badge-c"}`}>
                {f.share_mode === "public" ? "Public" : f.share_mode === "internal" ? "Kurum İçi" : "Özel"}
              </span>
              <span className="text-xs text-[var(--text-dim)]">{f.category}</span>
            </div>
            <h3 className="font-display text-lg leading-tight mb-2">{f.title}</h3>
            <p className="text-xs text-[var(--text-dim)] line-clamp-2 mb-4">{f.description}</p>
            <div className="flex items-center justify-between text-xs text-[var(--text-dim)] mb-4">
              <span>{f.fields?.length || 0} alan</span>
              <span className="text-[var(--primary)]">{f.response_count || 0} yanıt</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => nav(`/formlar/${f.id}/dashboard`)} className="btn btn-ghost text-xs flex-1 justify-center">
                <BarChart3 size={12}/> Sonuçlar
              </button>
              <button onClick={() => nav(`/formlar/${f.id}/duzenle`)} className="btn btn-ghost text-xs">
                Düzenle
              </button>
              {f.share_mode === "public" && (
                <button onClick={() => shareLink(f)} className="btn btn-ghost text-xs" title="Public link">
                  <Share2 size={12}/>
                </button>
              )}
              <button onClick={() => deleteForm(f.id)} className="btn btn-ghost text-xs text-red-400 hover:text-red-300">
                <Trash2 size={12}/>
              </button>
            </div>
          </div>
        ))}
      </div>
      {forms.length === 0 && (
        <div className="card p-12 text-center text-[var(--text-dim)]">
          Henüz form yok. <button onClick={() => nav("/formlar/yeni")} className="text-[var(--primary)] underline">İlk formu oluştur</button>
        </div>
      )}
    </div>
  );
}

// =====================================================================
// FORM BUILDER (Yeni / Düzenleme)
// =====================================================================
export function FormBuilder() {
  const { id } = useParams();
  const nav = useNavigate();
  const isEdit = !!id;
  
  const [form, setForm] = useState({
    title: "", description: "", category: "genel",
    share_mode: "internal", fields: []
  });
  const [farmers, setFarmers] = useState([]);
  const [showAssign, setShowAssign] = useState(false);
  const [selectedFarmers, setSelectedFarmers] = useState([]);
  const [searchFarmer, setSearchFarmer] = useState("");
  const [createdFormId, setCreatedFormId] = useState(null);

  useEffect(() => {
    if (isEdit) {
      api.get(`/forms/${id}`).then((r) => setForm(r.data));
      setCreatedFormId(id);
    }
  }, [id]);

  function addField(type) {
    const newField = {
      id: "f" + Date.now(),
      type, label: "Yeni alan",
      required: false,
      order: form.fields.length + 1,
      options: ["select", "multiselect"].includes(type) ? ["Seçenek 1", "Seçenek 2"] : null
    };
    setForm({ ...form, fields: [...form.fields, newField] });
  }
  
  function updateField(idx, patch) {
    const fields = [...form.fields];
    fields[idx] = { ...fields[idx], ...patch };
    setForm({ ...form, fields });
  }

  function removeField(idx) {
    setForm({ ...form, fields: form.fields.filter((_, i) => i !== idx) });
  }

  function moveField(idx, dir) {
    const fields = [...form.fields];
    const ni = idx + dir;
    if (ni < 0 || ni >= fields.length) return;
    [fields[idx], fields[ni]] = [fields[ni], fields[idx]];
    setForm({ ...form, fields });
  }

  async function save() {
    if (!form.title) { alert("Başlık gerekli"); return; }
    if (form.fields.length === 0) { alert("En az 1 alan ekleyin"); return; }
    
    try {
      if (isEdit) {
        await api.put(`/forms/${id}`, form);
        alert("Form güncellendi");
      } else {
        const { data } = await api.post("/forms", form);
        setCreatedFormId(data.id);
        alert(`Form oluşturuldu! ${data.share_mode === "public" ? "Public link: /form/" + data.public_token : ""}`);
        nav(`/formlar/${data.id}/duzenle`, { replace: true });
      }
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || err.message));
    }
  }
  
  // Atama
  useEffect(() => {
    if (showAssign && farmers.length === 0) {
      api.get("/farmers?limit=300").then((r) => setFarmers(r.data));
    }
  }, [showAssign]);
  
  async function assign() {
    const formId = createdFormId || id;
    if (!formId) { alert("Önce formu kaydedin"); return; }
    if (selectedFarmers.length === 0) { alert("En az 1 çiftçi seçin"); return; }
    await api.post(`/forms/${formId}/assign`, {
      farmer_ids: selectedFarmers,
      send_notification: true
    });
    alert(`${selectedFarmers.length} çiftçiye atandı (bildirim gönderildi)`);
    setShowAssign(false);
    setSelectedFarmers([]);
  }

  return (
    <div className="p-8 max-w-[1600px]" data-testid="form-builder-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">{isEdit ? "DÜZENLEME" : "YENİ FORM"}</div>
          <h1 className="font-display text-3xl">Form Tasarımcısı</h1>
        </div>
        <div className="flex gap-2">
          <button onClick={() => nav("/formlar")} className="btn btn-ghost">İptal</button>
          {(isEdit || createdFormId) && form.share_mode === "private" && (
            <button onClick={() => setShowAssign(true)} className="btn btn-ghost">
              <Send size={14}/> Çiftçilere Ata
            </button>
          )}
          <button onClick={save} className="btn btn-primary" data-testid="save-form-btn">
            <Save size={14}/> {isEdit ? "Güncelle" : "Kaydet"}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Sol: Form üst bilgi + alan tipi paleti */}
        <div className="card p-5 space-y-4">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">BAŞLIK</label>
            <input className="input" value={form.title} onChange={(e) => setForm({...form, title: e.target.value})} data-testid="form-title-input" />
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">AÇIKLAMA</label>
            <textarea className="input" rows="3" value={form.description || ""} onChange={(e) => setForm({...form, description: e.target.value})}/>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">KATEGORİ</label>
            <input className="input" value={form.category || ""} onChange={(e) => setForm({...form, category: e.target.value})} placeholder="örn: tarla denetimi"/>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1.5 block">PAYLAŞIM MODU</label>
            <select className="input" value={form.share_mode} onChange={(e) => setForm({...form, share_mode: e.target.value})}>
              <option value="private">🔒 Özel — Atanan çiftçilere</option>
              <option value="internal">🏢 Kurum İçi — Login gerekli</option>
              <option value="public">🌍 Public — Herkese açık link</option>
            </select>
          </div>

          <div className="pt-3 border-t border-[var(--border)]">
            <div className="text-xs text-[var(--text-dim)] mb-2">ALAN EKLE</div>
            <div className="grid grid-cols-2 gap-1.5">
              {FIELD_TYPES.map((t) => (
                <button key={t.id} onClick={() => addField(t.id)}
                        className="flex items-center gap-1.5 px-2 py-2 text-xs border border-[var(--border)] rounded-lg hover:border-[var(--primary)] transition-colors"
                        data-testid={`add-field-${t.id}`}>
                  <t.icon size={12}/> {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Sağ: Alan listesi (sıralı) */}
        <div className="lg:col-span-3 space-y-2">
          {form.fields.length === 0 ? (
            <div className="card p-12 text-center text-[var(--text-dim)]">
              Soldaki paletten alan ekleyerek başla
            </div>
          ) : form.fields.map((field, idx) => (
            <div key={field.id} className="card p-4" data-testid={`field-row-${idx}`}>
              <div className="flex items-start gap-3">
                <div className="flex flex-col gap-1 pt-2">
                  <button onClick={() => moveField(idx, -1)} disabled={idx === 0} className="text-[var(--text-dim)] disabled:opacity-30"><ChevronUp size={14}/></button>
                  <button onClick={() => moveField(idx, 1)} disabled={idx === form.fields.length - 1} className="text-[var(--text-dim)] disabled:opacity-30"><ChevronDown size={14}/></button>
                </div>
                <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="badge badge-b">{FIELD_TYPES.find(t => t.id === field.type)?.label || field.type}</span>
                      <label className="flex items-center gap-1 text-xs text-[var(--text-dim)]">
                        <input type="checkbox" checked={field.required} onChange={(e) => updateField(idx, { required: e.target.checked })}/>
                        Zorunlu
                      </label>
                    </div>
                    <input className="input" value={field.label} onChange={(e) => updateField(idx, { label: e.target.value })} placeholder="Alan başlığı"/>
                  </div>
                  <div>
                    {["select", "multiselect"].includes(field.type) && (
                      <div>
                        <label className="text-xs text-[var(--text-dim)]">SEÇENEKLER (virgülle)</label>
                        <input className="input" value={(field.options || []).join(", ")}
                               onChange={(e) => updateField(idx, { options: e.target.value.split(",").map(s => s.trim()) })}/>
                      </div>
                    )}
                    {field.type === "number" && (
                      <div className="grid grid-cols-2 gap-2">
                        <div><label className="text-xs text-[var(--text-dim)]">MIN</label><input type="number" className="input" value={field.min ?? ""} onChange={(e) => updateField(idx, { min: e.target.value === "" ? null : parseFloat(e.target.value) })}/></div>
                        <div><label className="text-xs text-[var(--text-dim)]">MAX</label><input type="number" className="input" value={field.max ?? ""} onChange={(e) => updateField(idx, { max: e.target.value === "" ? null : parseFloat(e.target.value) })}/></div>
                      </div>
                    )}
                  </div>
                </div>
                <button onClick={() => removeField(idx)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14}/></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ATAMA MODAL */}
      {showAssign && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setShowAssign(false)}>
          <div className="card max-w-2xl w-full p-6 max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Çiftçilere Ata</h3>
              <button onClick={() => setShowAssign(false)}><X size={20}/></button>
            </div>
            <input className="input mb-3" placeholder="Çiftçi ara..." value={searchFarmer} onChange={(e) => setSearchFarmer(e.target.value)}/>
            <div className="flex-1 overflow-y-auto scrollbar space-y-1">
              {farmers
                .filter((f) => !searchFarmer || f.full_name.toLowerCase().includes(searchFarmer.toLowerCase()) || f.member_no.includes(searchFarmer))
                .slice(0, 100).map((f) => (
                <label key={f.id} className="flex items-center gap-3 p-2.5 hover:bg-[var(--surface-2)] rounded cursor-pointer">
                  <input type="checkbox" checked={selectedFarmers.includes(f.id)}
                         onChange={(e) => {
                           if (e.target.checked) setSelectedFarmers([...selectedFarmers, f.id]);
                           else setSelectedFarmers(selectedFarmers.filter(x => x !== f.id));
                         }}/>
                  <div className="flex-1">
                    <div className="text-sm">{f.full_name}</div>
                    <div className="text-xs text-[var(--text-dim)]">{f.member_no} · {f.village}</div>
                  </div>
                  <span className={`badge badge-${f.karne_score.toLowerCase()}`}>{f.karne_score}</span>
                </label>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <div className="flex-1 text-xs text-[var(--text-dim)] pt-2">{selectedFarmers.length} seçili</div>
              <button onClick={() => setSelectedFarmers([])} className="btn btn-ghost text-xs">Temizle</button>
              <button onClick={assign} className="btn btn-primary" data-testid="assign-confirm">
                <Send size={14}/> Ata & Bildir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// =====================================================================
// FORM DOLDURMA (Login'li veya Public)
// =====================================================================
export function FormDoldur({ isPublic = false }) {
  const { id, token } = useParams();
  const nav = useNavigate();
  const [form, setForm] = useState(null);
  const [answers, setAnswers] = useState({});
  const [gps, setGps] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const url = isPublic ? `/public/forms/${token}` : `/forms/${id}`;
    api.get(url).then((r) => setForm(r.data)).catch(() => setForm({ error: true }));
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => setGps({ lat: 39.5, lng: 33.5 })
      );
    }
  }, [id, token]);

  function setA(fid, val) { setAnswers({ ...answers, [fid]: val }); }

  function onPhoto(fid, e) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { alert("Maks 5 MB"); return; }
    const reader = new FileReader();
    reader.onload = (ev) => setA(fid, ev.target.result);
    reader.readAsDataURL(f);
  }

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const url = isPublic ? `/public/forms/${token}/submit` : `/forms/${form.id}/submit`;
      const payload = {
        form_id: form.id,
        answers,
        gps_lat: gps?.lat,
        gps_lng: gps?.lng,
        public_token: isPublic ? token : null
      };
      await api.post(url, payload);
      setSubmitted(true);
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || err.message));
    } finally { setSubmitting(false); }
  }

  if (!form) return <div className="p-10 text-center text-[var(--text-dim)]">Yükleniyor...</div>;
  if (form.error) return <div className="p-10 text-center text-red-400">Form bulunamadı veya yayında değil.</div>;
  
  if (submitted) return (
    <div className="min-h-screen bg-[var(--bg)] grain flex items-center justify-center p-6">
      <div className="card p-8 max-w-md text-center">
        <div className="text-5xl mb-3">✅</div>
        <h2 className="font-display text-2xl mb-2">Teşekkürler!</h2>
        <p className="text-[var(--text-dim)] text-sm mb-4">Yanıtınız kaydedildi.</p>
        {!isPublic && <button onClick={() => nav("/")} className="btn btn-primary">Ana sayfaya dön</button>}
      </div>
    </div>
  );

  return (
    <div className={`${isPublic ? "min-h-screen bg-[var(--bg)] grain" : ""} p-4 md:p-8`} data-testid="form-fill-page">
      <div className="max-w-2xl mx-auto">
        <header className="mb-6">
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FORM DOLDURMA</div>
          <h1 className="font-display text-3xl">{form.title}</h1>
          {form.description && <p className="text-sm text-[var(--text-dim)] mt-2">{form.description}</p>}
          {gps && <p className="text-xs text-[var(--primary)] mt-2">📍 GPS alındı: {gps.lat.toFixed(4)}, {gps.lng.toFixed(4)}</p>}
        </header>

        <form onSubmit={submit} className="space-y-4">
          {(form.fields || []).sort((a, b) => (a.order || 0) - (b.order || 0)).map((field) => (
            <div key={field.id} className="card p-4">
              <label className="text-sm font-medium block mb-2">
                {field.label} {field.required && <span className="text-red-400">*</span>}
              </label>
              {field.type === "text" && (
                <input className="input" required={field.required} value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}/>
              )}
              {field.type === "textarea" && (
                <textarea className="input" rows="3" required={field.required} value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}/>
              )}
              {field.type === "number" && (
                <input type="number" className="input" min={field.min} max={field.max} required={field.required}
                       value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}/>
              )}
              {field.type === "date" && (
                <input type="date" className="input" required={field.required} value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}/>
              )}
              {field.type === "select" && (
                <select className="input" required={field.required} value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}>
                  <option value="">Seçiniz...</option>
                  {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {field.type === "multiselect" && (
                <div className="space-y-2">
                  {(field.options || []).map((o) => (
                    <label key={o} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={(answers[field.id] || []).includes(o)}
                             onChange={(e) => {
                               const cur = answers[field.id] || [];
                               setA(field.id, e.target.checked ? [...cur, o] : cur.filter(x => x !== o));
                             }}/>
                      {o}
                    </label>
                  ))}
                </div>
              )}
              {field.type === "yesno" && (
                <div className="flex gap-3">
                  <button type="button" onClick={() => setA(field.id, "Evet")}
                          className={`flex-1 py-3 rounded-lg border ${answers[field.id] === "Evet" ? "border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]" : "border-[var(--border)]"}`}>Evet</button>
                  <button type="button" onClick={() => setA(field.id, "Hayır")}
                          className={`flex-1 py-3 rounded-lg border ${answers[field.id] === "Hayır" ? "border-red-400 bg-red-500/10 text-red-400" : "border-[var(--border)]"}`}>Hayır</button>
                </div>
              )}
              {field.type === "rating" && (
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button key={n} type="button" onClick={() => setA(field.id, n)}
                            className={`w-12 h-12 rounded-lg border ${answers[field.id] >= n ? "border-amber-400 bg-amber-400/10 text-amber-400" : "border-[var(--border)]"}`}>
                      <Star size={20} className="mx-auto" fill={answers[field.id] >= n ? "currentColor" : "none"}/>
                    </button>
                  ))}
                </div>
              )}
              {field.type === "gps" && (
                <div className="text-sm">
                  {gps ? <span className="text-[var(--primary)]">📍 {gps.lat.toFixed(5)}, {gps.lng.toFixed(5)}</span> : <span className="text-[var(--text-dim)]">GPS alınıyor...</span>}
                </div>
              )}
              {field.type === "photo" && (
                <div>
                  {answers[field.id] ? (
                    <div>
                      <img src={answers[field.id]} alt="" className="w-full max-h-[200px] object-contain rounded-lg bg-[var(--surface-2)] mb-2"/>
                      <button type="button" onClick={() => setA(field.id, null)} className="btn btn-ghost text-xs">Kaldır</button>
                    </div>
                  ) : (
                    <label className="btn btn-ghost cursor-pointer w-full justify-center">
                      <Camera size={14}/> Fotoğraf çek/seç
                      <input type="file" accept="image/*" capture="environment" onChange={(e) => onPhoto(field.id, e)} className="hidden"/>
                    </label>
                  )}
                </div>
              )}
              {field.type === "signature" && (
                <textarea className="input" rows="2" placeholder="İmza/onay metni..."
                          value={answers[field.id] || ""} onChange={(e) => setA(field.id, e.target.value)}/>
              )}
            </div>
          ))}
          <button type="submit" disabled={submitting} className="btn btn-primary w-full justify-center py-3.5" data-testid="submit-form-response">
            {submitting ? <><Loader2 size={14} className="animate-spin"/> Gönderiliyor...</> : <><Send size={14}/> Yanıtı Gönder</>}
          </button>
        </form>
      </div>
    </div>
  );
}

// =====================================================================
// FORM DASHBOARD (Sonuç analizi)
// =====================================================================
const PIE_COLORS = ["#4ade80", "#60a5fa", "#fbbf24", "#ef4444", "#a78bfa", "#22d3ee"];

export function FormDashboard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [responses, setResponses] = useState([]);
  const [view, setView] = useState("widgets");
  const [order, setOrder] = useState([]);

  useEffect(() => {
    api.get(`/forms/${id}/analytics`).then((r) => {
      setData(r.data);
      setOrder(r.data.widgets.map((_, i) => i));
    });
    api.get(`/forms/${id}/responses`).then((r) => setResponses(r.data));
  }, [id]);

  function moveWidget(idx, dir) {
    const newOrder = [...order];
    const ni = idx + dir;
    if (ni < 0 || ni >= newOrder.length) return;
    [newOrder[idx], newOrder[ni]] = [newOrder[ni], newOrder[idx]];
    setOrder(newOrder);
  }

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor...</div>;

  // Tüm GPS noktalarını al (harita merkezi için)
  const gpsWidget = data.widgets.find((w) => w.type === "map");
  const mapCenter = gpsWidget?.points?.length > 0
    ? [gpsWidget.points[0].lat, gpsWidget.points[0].lng]
    : [39.5, 33.5];

  return (
    <div className="p-8 max-w-[1600px]" data-testid="form-dashboard">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <button onClick={() => nav("/formlar")} className="btn btn-ghost text-xs mb-2">← Tüm formlar</button>
          <h1 className="font-display text-3xl">{data.form.title}</h1>
          <p className="text-[var(--text-dim)] text-sm">{data.total_responses} yanıt · {data.form.fields?.length} alan</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setView("widgets")} className={`btn ${view === "widgets" ? "btn-primary" : "btn-ghost"} text-sm`}>Görsel</button>
          <button onClick={() => setView("table")} className={`btn ${view === "table" ? "btn-primary" : "btn-ghost"} text-sm`}>Tablo</button>
        </div>
      </header>

      {view === "widgets" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {order.map((origIdx, displayIdx) => {
            const w = data.widgets[origIdx];
            if (!w) return null;
            return (
              <div key={origIdx} className={`card p-5 ${w.type === "map" || w.type === "photo-gallery" ? "lg:col-span-2" : ""}`}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-display text-base">{w.title}</h3>
                  <div className="flex gap-1">
                    <button onClick={() => moveWidget(displayIdx, -1)} className="text-[var(--text-dim)] text-xs"><ChevronUp size={14}/></button>
                    <button onClick={() => moveWidget(displayIdx, 1)} className="text-[var(--text-dim)] text-xs"><ChevronDown size={14}/></button>
                  </div>
                </div>
                {w.type === "stat" && <div className="font-display text-4xl text-[var(--primary)]">{fmt(w.value)}</div>}
                {w.type === "stat-trio" && (
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div><div className="text-xs text-[var(--text-dim)]">Ort</div><div className="font-display text-2xl text-[var(--primary)]">{w.avg}</div></div>
                    <div><div className="text-xs text-[var(--text-dim)]">Min</div><div className="font-display text-2xl">{w.min}</div></div>
                    <div><div className="text-xs text-[var(--text-dim)]">Max</div><div className="font-display text-2xl">{w.max}</div></div>
                  </div>
                )}
                {w.type === "pie" && (
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={w.data} dataKey="value" nameKey="name" outerRadius={70} label>
                        {w.data.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]}/>)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
                      <Legend wrapperStyle={{ fontSize: 11 }}/>
                    </PieChart>
                  </ResponsiveContainer>
                )}
                {w.type === "bar" && (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={w.data}>
                      <XAxis dataKey="name" stroke="#97a8a0" style={{ fontSize: 10 }}/>
                      <YAxis stroke="#97a8a0"/>
                      <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
                      <Bar dataKey="value" fill="#4ade80" radius={[6,6,0,0]}/>
                    </BarChart>
                  </ResponsiveContainer>
                )}
                {w.type === "map" && (
                  <div style={{ height: 300 }}>
                    <MapContainer center={mapCenter} zoom={6} style={{ height: "100%", borderRadius: 8 }}>
                      <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"/>
                      {w.points.map((p) => (
                        <Marker key={p.id} position={[p.lat, p.lng]}>
                          <Popup>{p.id.substring(0, 8)}</Popup>
                        </Marker>
                      ))}
                    </MapContainer>
                  </div>
                )}
                {w.type === "text-list" && (
                  <div className="space-y-2 text-xs">
                    {w.samples.map((s, i) => <div key={i} className="p-2 bg-[var(--surface-2)] rounded">{s}</div>)}
                  </div>
                )}
                {w.type === "photo-gallery" && (
                  <div className="grid grid-cols-3 md:grid-cols-4 gap-2">
                    {w.photos.map((p, i) => <img key={i} src={p} alt="" className="w-full h-24 object-cover rounded"/>)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {view === "table" && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Tarih</th>
                <th className="p-3">Yanıtlayan</th>
                {(data.form.fields || []).map((f) => <th key={f.id} className="p-3">{f.label}</th>)}
                <th className="p-3">GPS</th>
              </tr>
            </thead>
            <tbody>
              {responses.map((r) => (
                <tr key={r.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                  <td className="p-3 text-xs text-[var(--text-dim)]">{new Date(r.created_at).toLocaleString("tr-TR")}</td>
                  <td className="p-3 text-xs">{r.submitter_name || r.submitter_role || "—"}</td>
                  {(data.form.fields || []).map((f) => {
                    const v = r.answers?.[f.id];
                    return (
                      <td key={f.id} className="p-3 text-xs max-w-[200px] truncate">
                        {f.type === "photo" && v ? <img src={v} alt="" className="w-12 h-12 object-cover rounded"/> :
                         Array.isArray(v) ? v.join(", ") : v || "—"}
                      </td>
                    );
                  })}
                  <td className="p-3 text-xs text-[var(--text-dim)]">{r.gps_lat ? `${r.gps_lat.toFixed(3)}, ${r.gps_lng.toFixed(3)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
