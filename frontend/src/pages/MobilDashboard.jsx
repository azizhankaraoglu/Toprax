/**
 * MOBİL DASHBOARD — PWA (IT-35 / FAZ 12, genişletildi IT-36/37/38/39 / FAZ 13)
 *
 * ROADMAP: "mevcut React kod tabanından, Experience Profile'ı tüketen
 * görev-odaklı mobil dashboard." Mevcut REST API'ler üzerinden çalışır,
 * ayrı bir mobil iş mantığı YAZILMADI.
 *
 * (IT-36) Görev Yaşam Döngüsü — field_ops.py'nin (IT-22/23) 11 durumlu
 * FieldTask durum makinesi TEK ekrandan yönetilir (atandı→...→kapandı),
 * `SahaOperasyonlari.jsx`'teki AYNI `ALLOWED_NEXT`/`TASK_STATUS_LABELS`
 * client-side tahminiyle. Offline: TÜM yazma işlemleri `lib/offlineQueue.js`
 * ile aynı kalıba tabi.
 *
 * (IT-37) Saha Formları — forms_module.py'nin (M18) `GET /forms` +
 * `POST /forms/{id}/submit` uçları mobilden tüketilir; YENİ bir form
 * altyapısı İCAT EDİLMEDİ, sadece 11 alan tipi (text/textarea/number/
 * select/multiselect/yesno/rating/date/gps/photo/video/signature) için
 * genel bir render fonksiyonu eklendi. "signature" tipi BİLİNÇLİ OLARAK
 * bir canvas imza pedi DEĞİL (yeni bağımlılık gerektirirdi) — ad-soyad +
 * "elektronik onaylıyorum" onay kutusu ile basitleştirildi.
 *
 * (IT-38) Çiftçi Mobil Self-Servis — `role==="ciftci"` iken 4 self-servis
 * akışı: sulama kaydı (`POST /farmer/irrigation`, ZATEN VARDI), uydu
 * görüntüsü (`GET /satellite/ndvi/{parcel_id}`, ZATEN VARDI), finansal
 * özet (`GET /farmer/my-dashboard`'ın stats+finance'ı, ZATEN VARDI),
 * ziyaret onaylama (YENİ: `GET/PUT /portal/visits*`, field_ops.py'ye
 * eklendi). Sözleşme onaylama / ekim planlama / randevu alma BİLİNÇLİ
 * OLARAK bu iterasyonun DIŞINDA bırakıldı — üçü de gerçek bir durum
 * makinesi/veri modeli kararı gerektiriyor (Karar Protokolü: "veri modeli
 * değişiklikleri her zaman sorulur"), roadmap'te ayrı not edildi.
 *
 * (IT-39) Teslim Kodu — support.py'nin var olan ama hiç doğrulanmayan
 * `qr_kod` yöntemi GERÇEKLEŞTİRİLDİ: personel `teslim_edildi` bir talep
 * için tek-kullanımlık 6 haneli kod üretir (`POST /support-requests/{id}/
 * delivery-code`), çiftçi KENDİ cihazından bu kodu girip kendi onayını
 * verir (`POST /portal/support-requests/confirm-delivery-code`). Gerçek
 * kamera-taramalı barkod YERİNE kısa kod kullanıldı (yeni bir QR-render
 * kütüphanesi eklemeden AYNI güvenlik özelliğini verir — bkz. support.py
 * docstring'i).
 */
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "@/api";
import { enqueue, flush, getAll as getQueuedItems } from "@/lib/offlineQueue";
import {
  Wifi, WifiOff, LayoutDashboard, ListChecks, Camera, MapPin, CloudUpload,
  CheckCircle2, Clock, RefreshCw, ThumbsUp, ThumbsDown, Truck, Flag,
  PlayCircle, Send, Lock, XCircle, RotateCcw, FileText, Droplets,
  Satellite, Wallet, KeyRound, Video, Star,
} from "lucide-react";

const MENU_ROUTES = {
  "ciftciler": "/ciftciler", "parseller": "/parseller", "harita-paneli": "/harita-paneli",
  "saha-operasyonlari": "/saha-operasyonlari", "egitim-yonetimi": "/egitim-yonetimi",
  "ufyd-dashboard": "/ufyd-dashboard", "otomasyon-kurallari": "/otomasyon-kurallari",
  "toprak": "/toprak", "sozlesmeler": "/sozlesmeler", "kampanyalar": "/kampanyalar",
};

const WIDGET_LABELS = {
  "toplam_ciftci": "Toplam Çiftçi", "aktif_uretim_sezonlari": "Aktif Üretim Sezonları",
  "gorev_bekleyen_parseller": "Görev Bekleyen Parseller", "riskli_parseller": "Riskli Parseller",
  "bekleyen_odemeler": "Bekleyen Ödemeler",
};

const QUICK_ACTION_LABELS = {
  "sulama-ekle": "Sulama Ekle", "destek-talebi": "Destek Talebi",
  "gorev-tamamla": "Görev Tamamla", "hakedis-goruntule": "Hakediş Görüntüle",
};

// backend/field_ops.py'deki TASK_STATUS_LABELS/TASK_ALLOWED_TRANSITIONS'ın
// client-side kopyası — SahaOperasyonlari.jsx'teki AYNI sabitlerle TUTARLI
// tutulmalı (iki dosyada bilinçli olarak ayrı, bkz. o dosyanın TKGM mapping
// notundaki "iki yerde elle senkron" emsali — burada da geçerli).
const TASK_STATUS_LABELS = {
  planlandi: "Planlandı", atandi: "Atandı", kabul_edildi: "Kabul Edildi",
  reddedildi: "Reddedildi", yola_cikildi: "Yola Çıkıldı", yerine_ulasildi: "Yerine Ulaşıldı",
  calisiliyor: "Çalışılıyor", tamamlandi: "Tamamlandı", onay_bekliyor: "Onay Bekliyor",
  kapandi: "Kapandı", iptal_edildi: "İptal Edildi",
};
const ALLOWED_NEXT = {
  planlandi: ["atandi", "iptal_edildi"],
  atandi: ["kabul_edildi", "reddedildi", "iptal_edildi"],
  kabul_edildi: ["yola_cikildi", "iptal_edildi"],
  yola_cikildi: ["yerine_ulasildi", "iptal_edildi"],
  yerine_ulasildi: ["calisiliyor", "iptal_edildi"],
  calisiliyor: ["tamamlandi", "iptal_edildi"],
  tamamlandi: ["onay_bekliyor", "iptal_edildi"],
  onay_bekliyor: ["kapandi", "iptal_edildi"],
  reddedildi: ["planlandi", "iptal_edildi"],
  kapandi: [], iptal_edildi: [],
};
const IRRIGATION_METHODS = ["damla", "yağmurlama", "karık"];

// (IT-37) forms_module.py'nin 11 alan tipini render eden genel bileşen.
// `value`/`onChange` her tip için farklı şekle sahip olabilir (string,
// number, string[], {lat,lng}) — form JSON'ı zaten tip-serbest olduğu
// için burada da esnek tutuldu.
function FormFieldInput({ field, value, onChange, gps }) {
  switch (field.type) {
    case "textarea":
      return <textarea className="input text-sm" rows={3} required={field.required}
        placeholder={field.placeholder || ""} value={value || ""} onChange={(e) => onChange(e.target.value)} />;
    case "number":
      return <input type="number" className="input text-sm" required={field.required}
        min={field.min} max={field.max} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
    case "date":
      return <input type="date" className="input text-sm" required={field.required}
        value={value || ""} onChange={(e) => onChange(e.target.value)} />;
    case "select":
      return (
        <select className="input text-sm" required={field.required} value={value || ""} onChange={(e) => onChange(e.target.value)}>
          <option value="">Seçiniz...</option>
          {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    case "multiselect":
      return (
        <div className="space-y-1">
          {(field.options || []).map((o) => (
            <label key={o} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={(value || []).includes(o)} onChange={(e) => {
                const list = value || [];
                onChange(e.target.checked ? [...list, o] : list.filter((x) => x !== o));
              }} />
              {o}
            </label>
          ))}
        </div>
      );
    case "yesno":
      return (
        <div className="flex gap-2">
          <button type="button" onClick={() => onChange(true)} className={`btn text-xs flex-1 ${value === true ? "btn-primary" : "btn-ghost"}`}>Evet</button>
          <button type="button" onClick={() => onChange(false)} className={`btn text-xs flex-1 ${value === false ? "btn-primary" : "btn-ghost"}`}>Hayır</button>
        </div>
      );
    case "rating": {
      const max = field.max || 5;
      return (
        <div className="flex gap-1">
          {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
            <button key={n} type="button" onClick={() => onChange(n)} className="p-0.5">
              <Star size={18} className={n <= (value || 0) ? "fill-amber-400 text-amber-400" : "text-[var(--text-dim)]"} />
            </button>
          ))}
        </div>
      );
    }
    case "gps":
      return <div className="text-xs text-[var(--text-dim)]">{gps ? `${gps.lat.toFixed(5)}, ${gps.lng.toFixed(5)} (otomatik alındı)` : "Konum henüz alınamadı"}</div>;
    case "photo":
    case "video":
      return (
        <label className="btn btn-ghost text-xs flex items-center gap-1 cursor-pointer w-fit">
          {field.type === "photo" ? <Camera size={12}/> : <Video size={12}/>} {value ? "Değiştir" : "Seç"} ({value ? 1 : 0})
          <input type="file" accept={field.type === "photo" ? "image/*" : "video/*"} capture="environment" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const reader = new FileReader();
              reader.onload = (ev) => onChange(ev.target.result);
              reader.readAsDataURL(f);
            }} />
        </label>
      );
    case "signature":
      // Bilinçli sadeleştirme — canvas imza pedi yerine ad-soyad + onay
      // kutusu (bkz. dosya başı notu, yeni bağımlılık eklenmedi).
      return (
        <div className="space-y-1">
          <input className="input text-sm" placeholder="Ad Soyad" value={value?.name || ""}
            onChange={(e) => onChange({ ...(value || {}), name: e.target.value })} />
          <label className="flex items-center gap-2 text-[11px]">
            <input type="checkbox" checked={!!value?.confirmed} onChange={(e) => onChange({ ...(value || {}), confirmed: e.target.checked })} />
            Bu belgeyi elektronik olarak imzalıyorum
          </label>
        </div>
      );
    default:
      return <input type="text" className="input text-sm" required={field.required}
        placeholder={field.placeholder || ""} value={value || ""} onChange={(e) => onChange(e.target.value)} />;
  }
}

export default function MobilDashboard() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isFarmer = user.role === "ciftci";
  const [experience, setExperience] = useState(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [queueCount, setQueueCount] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [submitMsg, setSubmitMsg] = useState("");

  // --- IT-36: görev yaşam döngüsü ---
  const [tasks, setTasks] = useState([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [checklist, setChecklist] = useState([]);
  const [notes, setNotes] = useState("");
  const [gps, setGps] = useState(null);
  const [photos, setPhotos] = useState([]);
  const [reasonMode, setReasonMode] = useState(null); // null | "reddedildi" | "iptal_edildi"
  const [reasonText, setReasonText] = useState("");
  const [busy, setBusy] = useState(false);

  // --- IT-37: saha formları ---
  const [forms, setForms] = useState([]);
  const [selectedFormId, setSelectedFormId] = useState("");
  const [formAnswers, setFormAnswers] = useState({});
  const [formGps, setFormGps] = useState(null);
  const [formBusy, setFormBusy] = useState(false);

  // --- IT-38: çiftçi self-servis ---
  const [farmerDashboard, setFarmerDashboard] = useState(null);
  const [irrigationForm, setIrrigationForm] = useState({ parcel_id: "", date: new Date().toISOString().slice(0, 10), method: "damla", water_m3: "" });
  const [irrigationBusy, setIrrigationBusy] = useState(false);
  const [ndviParcelId, setNdviParcelId] = useState("");
  const [ndviResult, setNdviResult] = useState(null);
  const [myVisits, setMyVisits] = useState([]);

  // --- IT-39: teslim kodu ---
  const [deliverableRequests, setDeliverableRequests] = useState([]);
  const [generatedCodes, setGeneratedCodes] = useState({}); // request_id -> {code, expires_at}
  const [deliveryCodeInput, setDeliveryCodeInput] = useState("");

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || null;
  const selectedForm = forms.find((f) => f.id === selectedFormId) || null;

  const refreshQueueCount = useCallback(() => {
    getQueuedItems().then((items) => setQueueCount(items.length)).catch(() => {});
  }, []);

  const loadTasks = useCallback(() => {
    if (user.id && !isFarmer) {
      api.get("/tasks", { params: { assigned_to: user.id } }).then((r) => setTasks(r.data)).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);

  const trySync = useCallback(async () => {
    setSyncing(true);
    try {
      const { sent } = await flush(api);
      if (sent > 0) {
        setSubmitMsg(`${sent} bekleyen kayıt senkronize edildi.`);
        loadTasks();
      }
    } finally {
      setSyncing(false);
      refreshQueueCount();
    }
  }, [refreshQueueCount, loadTasks]);

  useEffect(() => {
    api.get("/me/experience").then((r) => setExperience(r.data));
    loadTasks();
    refreshQueueCount();
    trySync();
    api.get("/forms").then((r) => setForms(r.data)).catch(() => {});

    if (isFarmer) {
      api.get("/farmer/my-dashboard").then((r) => setFarmerDashboard(r.data)).catch(() => {});
      api.get("/portal/visits").then((r) => setMyVisits(r.data)).catch(() => {});
    } else {
      api.get("/support-requests", { params: { status: "teslim_edildi" } }).then((r) => setDeliverableRequests(r.data)).catch(() => {});
    }

    const onOnline = () => { setOnline(true); trySync(); };
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectTask(taskId) {
    setSelectedTaskId(taskId);
    const t = tasks.find((x) => x.id === taskId);
    setChecklist(t ? t.checklist.map((c) => ({ ...c })) : []);
    setNotes(""); setGps(null); setPhotos([]); setReasonMode(null); setReasonText("");
  }

  function toggleChecklistItem(idx) {
    setChecklist((c) => c.map((item, i) => (i === idx ? { ...item, done: !item.done } : item)));
  }

  function captureGps(setter) {
    navigator.geolocation.getCurrentPosition(
      (pos) => setter({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setSubmitMsg("Konum alınamadı — tarayıcı izni gerekli."),
    );
  }

  function onPhotoSelect(e) {
    const files = [...(e.target.files || [])];
    files.forEach((f) => {
      const reader = new FileReader();
      reader.onload = (ev) => setPhotos((p) => [...p, ev.target.result]);
      reader.readAsDataURL(f);
    });
  }

  function applyLocalStatus(taskId, status) {
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status } : t)));
  }

  async function doTransition(status, reason) {
    if (!selectedTaskId || busy) return;
    setBusy(true);
    setSubmitMsg("");
    const payload = { status, reason: reason || null };
    try {
      if (!navigator.onLine) throw new Error("offline");
      const { data } = await api.put(`/tasks/${selectedTaskId}/transition`, payload);
      setTasks((prev) => prev.map((t) => (t.id === selectedTaskId ? data : t)));
      setSubmitMsg(`Durum güncellendi: ${TASK_STATUS_LABELS[status] || status}`);
    } catch (err) {
      if (!navigator.onLine || err.message === "offline" || !err.response) {
        await enqueue({ method: "put", url: `/tasks/${selectedTaskId}/transition`, body: payload });
        applyLocalStatus(selectedTaskId, status);
        setSubmitMsg("Bağlantı yok — durum değişikliği cihazda saklandı, bağlantı gelince gönderilecek.");
        refreshQueueCount();
      } else {
        setSubmitMsg("Hata: " + (err.response?.data?.detail || "İşlem başarısız"));
      }
    } finally {
      setBusy(false);
      setReasonMode(null); setReasonText("");
    }
  }

  async function completeTask() {
    if (!selectedTaskId || busy) return;
    setBusy(true);
    setSubmitMsg("");

    const visitPayload = { task_id: selectedTaskId, gps_start: gps || null, photos, notes: notes || null };
    const checklistUpdates = checklist.map((c) => ({ item: c.item, done: c.done }));
    const isOffline = !navigator.onLine;

    try {
      if (isOffline) throw new Error("offline");
      await api.post("/visits", visitPayload);
      for (const c of checklistUpdates) {
        await api.put(`/tasks/${selectedTaskId}/checklist`, c);
      }
      const { data } = await api.put(`/tasks/${selectedTaskId}/transition`, { status: "tamamlandi" });
      setTasks((prev) => prev.map((t) => (t.id === selectedTaskId ? data : t)));
      setSubmitMsg("Görev tamamlandı — ziyaret ve checklist kaydedildi.");
    } catch (err) {
      if (isOffline || err.message === "offline" || !err.response) {
        await enqueue({ method: "post", url: "/visits", body: visitPayload });
        for (const c of checklistUpdates) {
          await enqueue({ method: "put", url: `/tasks/${selectedTaskId}/checklist`, body: c });
        }
        await enqueue({ method: "put", url: `/tasks/${selectedTaskId}/transition`, body: { status: "tamamlandi" } });
        setTasks((prev) => prev.map((t) => (
          t.id === selectedTaskId ? { ...t, status: "tamamlandi", checklist } : t
        )));
        setSubmitMsg("Bağlantı yok — kayıt cihazda saklandı, bağlantı gelince otomatik gönderilecek.");
        refreshQueueCount();
      } else {
        setSubmitMsg("Hata: " + (err.response?.data?.detail || "Kaydedilemedi"));
      }
    } finally {
      setBusy(false);
      setNotes(""); setGps(null); setPhotos([]);
    }
  }

  // --- IT-37: form doldurma ---
  function selectForm(formId) {
    setSelectedFormId(formId);
    setFormAnswers({});
    setFormGps(null);
    if (formId) captureGps(setFormGps);
  }

  async function submitForm(e) {
    e.preventDefault();
    if (!selectedForm || formBusy) return;
    setFormBusy(true);
    setSubmitMsg("");
    const answers = { ...formAnswers };
    for (const f of selectedForm.fields) {
      if (f.type === "gps") answers[f.id] = formGps;
    }
    const payload = { form_id: selectedForm.id, answers, gps_lat: formGps?.lat ?? null, gps_lng: formGps?.lng ?? null };
    try {
      if (!navigator.onLine) throw new Error("offline");
      await api.post(`/forms/${selectedForm.id}/submit`, payload);
      setSubmitMsg("Form gönderildi.");
      setSelectedFormId(""); setFormAnswers({}); setFormGps(null);
    } catch (err) {
      if (!navigator.onLine || err.message === "offline" || !err.response) {
        await enqueue({ method: "post", url: `/forms/${selectedForm.id}/submit`, body: payload });
        setSubmitMsg("Bağlantı yok — form cihazda saklandı, bağlantı gelince gönderilecek.");
        setSelectedFormId(""); setFormAnswers({}); setFormGps(null);
        refreshQueueCount();
      } else {
        setSubmitMsg("Hata: " + (err.response?.data?.detail || "Form gönderilemedi"));
      }
    } finally {
      setFormBusy(false);
    }
  }

  // --- IT-38: çiftçi self-servis ---
  async function submitIrrigation(e) {
    e.preventDefault();
    if (irrigationBusy || !irrigationForm.parcel_id || !irrigationForm.water_m3) return;
    setIrrigationBusy(true);
    setSubmitMsg("");
    const payload = { ...irrigationForm, water_m3: Number(irrigationForm.water_m3) };
    try {
      if (!navigator.onLine) throw new Error("offline");
      await api.post("/farmer/irrigation", payload);
      setSubmitMsg("Sulama kaydı eklendi.");
      setIrrigationForm({ parcel_id: "", date: new Date().toISOString().slice(0, 10), method: "damla", water_m3: "" });
    } catch (err) {
      if (!navigator.onLine || err.message === "offline" || !err.response) {
        await enqueue({ method: "post", url: "/farmer/irrigation", body: payload });
        setSubmitMsg("Bağlantı yok — sulama kaydı cihazda saklandı, bağlantı gelince gönderilecek.");
        refreshQueueCount();
      } else {
        setSubmitMsg("Hata: " + (err.response?.data?.detail || "Kaydedilemedi"));
      }
    } finally {
      setIrrigationBusy(false);
    }
  }

  function loadNdvi(parcelId) {
    setNdviParcelId(parcelId);
    setNdviResult(null);
    if (!parcelId) return;
    api.get(`/satellite/ndvi/${parcelId}`).then((r) => setNdviResult(r.data)).catch(() => setSubmitMsg("Uydu verisi alınamadı."));
  }

  async function confirmVisit(visitId) {
    try {
      const { data } = await api.put(`/portal/visits/${visitId}/confirm-by-farmer`);
      setMyVisits((prev) => prev.map((v) => (v.id === visitId ? data : v)));
      setSubmitMsg("Ziyaret onaylandı.");
    } catch (err) {
      setSubmitMsg("Hata: " + (err.response?.data?.detail || "Onaylanamadı"));
    }
  }

  // --- IT-39: teslim kodu ---
  async function generateDeliveryCode(requestId) {
    try {
      const { data } = await api.post(`/support-requests/${requestId}/delivery-code`);
      setGeneratedCodes((prev) => ({ ...prev, [requestId]: data }));
    } catch (err) {
      setSubmitMsg("Hata: " + (err.response?.data?.detail || "Kod üretilemedi"));
    }
  }

  async function confirmDeliveryCode(e) {
    e.preventDefault();
    if (!deliveryCodeInput) return;
    try {
      await api.post("/portal/support-requests/confirm-delivery-code", { code: deliveryCodeInput });
      setSubmitMsg("Teslimat onaylandı.");
      setDeliveryCodeInput("");
    } catch (err) {
      setSubmitMsg("Hata: " + (err.response?.data?.detail || "Kod doğrulanamadı"));
    }
  }

  const incompleteItems = checklist.filter((c) => !c.done).map((c) => c.item);
  const farmerParcels = farmerDashboard?.parcels || [];

  if (!experience) return <div className="p-6 text-[var(--text-dim)]">Yükleniyor…</div>;

  return (
    <div className="min-h-screen bg-[var(--bg)] p-4 max-w-md mx-auto" data-testid="mobil-dashboard">
      <header className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] text-[var(--primary)] tracking-widest">MOBİL — {experience.profile_name}</div>
          <h1 className="font-display text-2xl">Merhaba, {user.full_name || "Kullanıcı"}</h1>
        </div>
        <span className={`badge ${online ? "badge-a" : "badge-d"} flex items-center gap-1`}>
          {online ? <Wifi size={12}/> : <WifiOff size={12}/>} {online ? "Çevrimiçi" : "Çevrimdışı"}
        </span>
      </header>

      {queueCount > 0 && (
        <div className="card p-3 mb-4 flex items-center justify-between" data-testid="offline-queue-banner">
          <div className="flex items-center gap-2 text-sm">
            <Clock size={14} className="text-amber-400"/>
            {queueCount} kayıt senkron bekliyor
          </div>
          <button onClick={trySync} disabled={syncing} className="btn btn-ghost text-xs flex items-center gap-1">
            <RefreshCw size={12} className={syncing ? "animate-spin" : ""}/> Şimdi Dene
          </button>
        </div>
      )}
      {submitMsg && <div className="text-xs p-2 bg-[var(--surface-2)] rounded mb-4" data-testid="mobil-submit-msg">{submitMsg}</div>}

      <div className="card p-4 mb-4">
        <h3 className="text-sm font-medium mb-2 flex items-center gap-2"><LayoutDashboard size={14} className="text-[var(--primary)]"/>Widget'lar</h3>
        <div className="grid grid-cols-2 gap-2">
          {experience.dashboard_widgets.map((w) => (
            <div key={w} className="bg-[var(--surface-2)] rounded-lg p-3 text-xs">{WIDGET_LABELS[w] || w}</div>
          ))}
        </div>
      </div>

      <div className="card p-4 mb-4">
        <h3 className="text-sm font-medium mb-2">Menü</h3>
        <div className="grid grid-cols-2 gap-2">
          {experience.menu_items.map((m) => (
            MENU_ROUTES[m] ? (
              <Link key={m} to={MENU_ROUTES[m]} className="bg-[var(--surface-2)] rounded-lg p-3 text-xs text-center hover:bg-[var(--primary)]/10">
                {m}
              </Link>
            ) : <div key={m} className="bg-[var(--surface-2)] rounded-lg p-3 text-xs text-center text-[var(--text-dim)]">{m}</div>
          ))}
        </div>
      </div>

      <div className="card p-4 mb-4">
        <h3 className="text-sm font-medium mb-2">Hızlı Aksiyonlar</h3>
        <div className="flex flex-wrap gap-2">
          {experience.quick_actions.map((qa) => (
            <span key={qa} className="badge badge-neutral text-xs">{QUICK_ACTION_LABELS[qa] || qa}</span>
          ))}
        </div>
      </div>

      {/* (IT-36) Görev Yaşam Döngüsü — sadece saha/personel rolleri (çiftçinin
          field_ops:view izni yok, GET /tasks zaten 403 döner). */}
      {!isFarmer && (
        <div className="card p-4 mb-4" data-testid="task-lifecycle-panel">
          <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><ListChecks size={14} className="text-[var(--primary)]"/>Görevlerim</h3>

          <select className="input text-sm mb-3" value={selectedTaskId} onChange={(e) => selectTask(e.target.value)} data-testid="mobil-task-select">
            <option value="">Görev seç...</option>
            {tasks.map((t) => <option key={t.id} value={t.id}>{t.task_type_id} — {TASK_STATUS_LABELS[t.status] || t.status}</option>)}
          </select>

          {selectedTask && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="badge badge-b text-xs" data-testid="mobil-task-status">{TASK_STATUS_LABELS[selectedTask.status] || selectedTask.status}</span>
                {selectedTask.priority && <span className="text-[10px] text-[var(--text-dim)] uppercase">{selectedTask.priority}</span>}
              </div>

              {selectedTask.status === "planlandi" && (
                <div className="text-xs text-[var(--text-dim)]">Görev planlandı — yönetici ataması onayı bekleniyor.</div>
              )}

              {selectedTask.status === "atandi" && (
                <div className="flex gap-2">
                  <button disabled={busy} onClick={() => doTransition("kabul_edildi")} className="btn btn-primary flex-1 text-xs flex items-center justify-center gap-1" data-testid="task-action-kabul">
                    <ThumbsUp size={13}/> Kabul Et
                  </button>
                  <button disabled={busy} onClick={() => setReasonMode("reddedildi")} className="btn btn-ghost flex-1 text-xs flex items-center justify-center gap-1" data-testid="task-action-reddet">
                    <ThumbsDown size={13}/> Reddet
                  </button>
                </div>
              )}

              {selectedTask.status === "kabul_edildi" && (
                <button disabled={busy} onClick={() => doTransition("yola_cikildi")} className="btn btn-primary w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-yola-cikildi">
                  <Truck size={14}/> Yola Çıktım
                </button>
              )}

              {selectedTask.status === "yola_cikildi" && (
                <button disabled={busy} onClick={() => doTransition("yerine_ulasildi")} className="btn btn-primary w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-yerine-ulasildi">
                  <Flag size={14}/> Yerine Ulaştım
                </button>
              )}

              {selectedTask.status === "yerine_ulasildi" && (
                <button disabled={busy} onClick={() => doTransition("calisiliyor")} className="btn btn-primary w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-calisiliyor">
                  <PlayCircle size={14}/> Çalışmaya Başla
                </button>
              )}

              {selectedTask.status === "calisiliyor" && (
                <div className="space-y-2 border-t border-[var(--border)] pt-3">
                  {checklist.length > 0 && (
                    <div className="space-y-1.5">
                      {checklist.map((c, idx) => (
                        <label key={idx} className="flex items-center gap-2 text-xs">
                          <input type="checkbox" checked={c.done} onChange={() => toggleChecklistItem(idx)}/>
                          {c.item}
                        </label>
                      ))}
                    </div>
                  )}
                  <textarea className="input text-sm" rows={2} placeholder="Not..." value={notes} onChange={(e) => setNotes(e.target.value)}/>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => captureGps(setGps)} className="btn btn-ghost text-xs flex items-center gap-1">
                      <MapPin size={12}/> {gps ? `${gps.lat.toFixed(4)}, ${gps.lng.toFixed(4)}` : "Konumu Al"}
                    </button>
                    <label className="btn btn-ghost text-xs flex items-center gap-1 cursor-pointer">
                      <Camera size={12}/> Fotoğraf ({photos.length})
                      <input type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={onPhotoSelect}/>
                    </label>
                  </div>
                  <button disabled={busy} onClick={completeTask} className="btn btn-primary w-full flex items-center justify-center gap-2" data-testid="task-action-tamamla">
                    {online ? <CheckCircle2 size={14}/> : <CloudUpload size={14}/>}
                    {online ? "Tamamlandı Olarak İşaretle" : "Kaydet (Offline)"}
                  </button>
                </div>
              )}

              {selectedTask.status === "tamamlandi" && (
                <button disabled={busy} onClick={() => doTransition("onay_bekliyor")} className="btn btn-primary w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-onaya-gonder">
                  <Send size={14}/> Yöneticiye Onaya Gönder
                </button>
              )}

              {selectedTask.status === "onay_bekliyor" && (
                <div className="space-y-2">
                  {incompleteItems.length > 0 && (
                    <div className="text-[11px] text-amber-400">Eksik checklist: {incompleteItems.join(", ")}</div>
                  )}
                  <button disabled={busy} onClick={() => doTransition("kapandi")} className="btn btn-primary w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-kapat">
                    <Lock size={14}/> Görevi Kapat
                  </button>
                </div>
              )}

              {selectedTask.status === "reddedildi" && (
                <button disabled={busy} onClick={() => doTransition("planlandi")} className="btn btn-ghost w-full text-xs flex items-center justify-center gap-2" data-testid="task-action-yeniden-planla">
                  <RotateCcw size={14}/> Yeniden Planla
                </button>
              )}

              {(selectedTask.status === "kapandi" || selectedTask.status === "iptal_edildi") && (
                <div className="text-xs text-[var(--text-dim)]">Bu görev sonlanmış, işlem yapılamaz.</div>
              )}

              {reasonMode && (
                <div className="space-y-2 border-t border-[var(--border)] pt-3">
                  <input className="input text-sm" placeholder="Sebep (opsiyonel)..." value={reasonText} onChange={(e) => setReasonText(e.target.value)} data-testid="reason-input"/>
                  <div className="flex gap-2">
                    <button disabled={busy} onClick={() => doTransition(reasonMode, reasonText)} className="btn btn-primary flex-1 text-xs" data-testid="reason-confirm">Onayla</button>
                    <button onClick={() => { setReasonMode(null); setReasonText(""); }} className="btn btn-ghost flex-1 text-xs">Vazgeç</button>
                  </div>
                </div>
              )}

              {ALLOWED_NEXT[selectedTask.status]?.includes("iptal_edildi") && !reasonMode && (
                <button disabled={busy} onClick={() => setReasonMode("iptal_edildi")} className="text-[11px] text-[var(--danger)] flex items-center gap-1 mx-auto mt-1" data-testid="task-action-iptal">
                  <XCircle size={11}/> Görevi İptal Et
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* (IT-37) Saha Formları — herkes (çiftçi kendi atanmış + internal
          formları görür, personel/admin tüm katalogu görür — bkz. forms_
          module.py'nin GET /forms rol ayrımı, burada YENİDEN yapılmadı). */}
      <div className="card p-4 mb-4" data-testid="forms-panel">
        <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><FileText size={14} className="text-[var(--primary)]"/>Formlar</h3>
        <select className="input text-sm mb-3" value={selectedFormId} onChange={(e) => selectForm(e.target.value)} data-testid="mobil-form-select">
          <option value="">Form seç...</option>
          {forms.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
        </select>

        {selectedForm && (
          <form onSubmit={submitForm} className="space-y-3" data-testid="mobil-form-fill">
            {selectedForm.description && <div className="text-xs text-[var(--text-dim)]">{selectedForm.description}</div>}
            {[...selectedForm.fields].sort((a, b) => (a.order || 0) - (b.order || 0)).map((f) => (
              <div key={f.id}>
                <label className="text-xs text-[var(--text-dim)] block mb-1">{f.label}{f.required && " *"}</label>
                <FormFieldInput field={f} gps={formGps} value={formAnswers[f.id]}
                  onChange={(v) => setFormAnswers((prev) => ({ ...prev, [f.id]: v }))} />
              </div>
            ))}
            <button type="submit" disabled={formBusy} className="btn btn-primary w-full flex items-center justify-center gap-2" data-testid="mobil-form-submit">
              {online ? <CheckCircle2 size={14}/> : <CloudUpload size={14}/>}
              {online ? "Formu Gönder" : "Kaydet (Offline)"}
            </button>
          </form>
        )}
      </div>

      {/* (IT-38) Çiftçi Mobil Self-Servis */}
      {isFarmer && (
        <>
          <div className="card p-4 mb-4" data-testid="farmer-irrigation-panel">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Droplets size={14} className="text-[var(--primary)]"/>Sulama Kaydı Ekle</h3>
            <form onSubmit={submitIrrigation} className="space-y-2">
              <select className="input text-sm" required value={irrigationForm.parcel_id}
                onChange={(e) => setIrrigationForm((p) => ({ ...p, parcel_id: e.target.value }))} data-testid="irrigation-parcel-select">
                <option value="">Parsel seç...</option>
                {farmerParcels.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <div className="flex gap-2">
                <input type="date" className="input text-sm flex-1" required value={irrigationForm.date}
                  onChange={(e) => setIrrigationForm((p) => ({ ...p, date: e.target.value }))} />
                <select className="input text-sm flex-1" value={irrigationForm.method}
                  onChange={(e) => setIrrigationForm((p) => ({ ...p, method: e.target.value }))}>
                  {IRRIGATION_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <input type="number" step="0.1" min="0" className="input text-sm" required placeholder="Su miktarı (m³)"
                value={irrigationForm.water_m3} onChange={(e) => setIrrigationForm((p) => ({ ...p, water_m3: e.target.value }))} />
              <button type="submit" disabled={irrigationBusy} className="btn btn-primary w-full text-xs" data-testid="irrigation-submit">Kaydet</button>
            </form>
          </div>

          <div className="card p-4 mb-4" data-testid="farmer-ndvi-panel">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Satellite size={14} className="text-[var(--primary)]"/>Uydu Görüntüsü (NDVI)</h3>
            <select className="input text-sm mb-2" value={ndviParcelId} onChange={(e) => loadNdvi(e.target.value)} data-testid="ndvi-parcel-select">
              <option value="">Parsel seç...</option>
              {farmerParcels.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {ndviResult && (
              <div className="grid grid-cols-2 gap-2 text-xs" data-testid="ndvi-result">
                <div className="bg-[var(--surface-2)] rounded-lg p-2">NDVI: <b>{ndviResult.latest_ndvi}</b></div>
                <div className="bg-[var(--surface-2)] rounded-lg p-2">Tarih: <b>{ndviResult.latest_date}</b></div>
                <div className="bg-[var(--surface-2)] rounded-lg p-2 col-span-2">
                  Sağlık: <b style={{ color: ndviResult.health?.color }}>{ndviResult.health?.label}</b>
                </div>
              </div>
            )}
          </div>

          <div className="card p-4 mb-4" data-testid="farmer-finance-panel">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><Wallet size={14} className="text-[var(--primary)]"/>Finansal Özetim</h3>
            {farmerDashboard ? (
              <div className="space-y-2 text-xs">
                <div className="bg-[var(--surface-2)] rounded-lg p-2">Bakiye: <b>{farmerDashboard.stats.balance} TL</b></div>
                {farmerDashboard.finance.slice(0, 5).map((f) => (
                  <div key={f.id} className="flex justify-between border-b border-[var(--border)] pb-1">
                    <span className="text-[var(--text-dim)]">{f.date} — {f.type || f.category || "Hareket"}</span>
                    <span>{f.amount} TL</span>
                  </div>
                ))}
              </div>
            ) : <div className="text-xs text-[var(--text-dim)]">Yükleniyor…</div>}
          </div>

          <div className="card p-4 mb-4" data-testid="farmer-visits-panel">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><CheckCircle2 size={14} className="text-[var(--primary)]"/>Ziyaretlerim</h3>
            {myVisits.length === 0 && <div className="text-xs text-[var(--text-dim)]">Kayıtlı ziyaret yok.</div>}
            {myVisits.slice(0, 10).map((v) => (
              <div key={v.id} className="flex items-center justify-between border-b border-[var(--border)] py-1.5 text-xs">
                <span>{(v.started_at || "").slice(0, 10)} — {v.task_type_id || "Ziyaret"}</span>
                {v.confirmed_by_farmer ? (
                  <span className="badge badge-a text-[10px]">Onaylandı</span>
                ) : (
                  <button onClick={() => confirmVisit(v.id)} className="btn btn-ghost text-[10px] py-1" data-testid={`confirm-visit-${v.id}`}>Onayla</button>
                )}
              </div>
            ))}
          </div>

          <div className="card p-4 mb-4" data-testid="farmer-delivery-code-panel">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><KeyRound size={14} className="text-[var(--primary)]"/>Teslim Kodu Onayla</h3>
            <form onSubmit={confirmDeliveryCode} className="flex gap-2">
              <input className="input text-sm flex-1" placeholder="6 haneli kod" maxLength={6}
                value={deliveryCodeInput} onChange={(e) => setDeliveryCodeInput(e.target.value)} data-testid="delivery-code-input"/>
              <button type="submit" className="btn btn-primary text-xs" data-testid="delivery-code-confirm">Onayla</button>
            </form>
          </div>
        </>
      )}

      {/* (IT-39) Teslim Kodu Oluştur — personel tarafı */}
      {!isFarmer && deliverableRequests.length > 0 && (
        <div className="card p-4 mb-4" data-testid="staff-delivery-code-panel">
          <h3 className="text-sm font-medium mb-3 flex items-center gap-2"><KeyRound size={14} className="text-[var(--primary)]"/>Teslim Kodu Oluştur</h3>
          {deliverableRequests.map((r) => (
            <div key={r.id} className="border-b border-[var(--border)] py-2">
              <div className="text-xs mb-1">{r.requested_amount} {r.unit} — {r.farmer_id}</div>
              {generatedCodes[r.id] ? (
                <div className="text-lg font-display tracking-widest text-[var(--primary)]" data-testid={`delivery-code-${r.id}`}>
                  {generatedCodes[r.id].code}
                </div>
              ) : (
                <button onClick={() => generateDeliveryCode(r.id)} className="btn btn-ghost text-xs" data-testid={`generate-code-${r.id}`}>Kod Oluştur</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
