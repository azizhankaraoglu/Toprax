/**
 * DatasetEditor — bir AI datasetinin İÇİNİ düzenleme (RAG besleme ekranı).
 *
 * Kullanıcı isteği (2026-08-19): "Kütüphanede yeni dataset ekleyebiliyorum
 * ama datasetin içini düzenleyip bilgi ekleyemiyorum. Burası benim RAG
 * ekleme alanım — foto, PDF, hatta video gibi tüm verileri buraya ekleyip
 * kendi LLM modelimi buradan beslemem lazım. Yani resmi, etiketini ve
 * açıklamasını buraya gireceğim ki LLM buradan öğrensin."
 *
 * Mimari: YENİ bir dosya yükleme mekanizması İCAT EDİLMEZ — mevcut genel
 * `storage.py` (`POST /uploads`, module="ai_knowledge") kullanılır; bilgi
 * kaydı da mevcut `POST /ai/knowledge-records` ucuna yazılır. Yani bu ekran
 * var olan iki altyapıyı birleştiren bir yüzeydir.
 *
 * Doğrulama akışı: kaydedilen her bilgi kaydı `approval_status: "incelemede"`
 * ile başlar → Doğrulama sekmesinde ziraat mühendisi onaylar → onaylananlar
 * "golden set" olarak eğitim/RAG'da kullanılır.
 */
import { useEffect, useRef, useState } from "react";
import api from "@/api";
import {
  Upload, Image as ImageIcon, FileText, Video, Tag, Save, Trash2, CheckCircle2,
  Loader2, X,
} from "lucide-react";

const OBJECT_TYPES = [
  ["hastalik", "Hastalık"], ["zararli", "Zararlı"], ["yabanci_ot", "Yabancı Ot"],
  ["besin_eksikligi", "Besin Eksikliği"], ["fenoloji", "Fenolojik Evre"],
  ["toprak", "Toprak"], ["ekipman", "Ekipman"], ["diger", "Diğer"],
];

const MEDIA_ICON = { image: ImageIcon, pdf: FileText, video: Video, text: FileText };

function mediaKind(name = "") {
  const ext = name.split(".").pop()?.toLowerCase();
  if (["jpg", "jpeg", "png", "webp", "gif", "tif", "tiff"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  if (["mp4", "mov", "avi", "mkv", "webm"].includes(ext)) return "video";
  return "text";
}

export default function DatasetEditor({ dataset, taxonomy = [], onClose, onChanged }) {
  const [records, setRecords] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const fileRef = useRef(null);
  const [form, setForm] = useState({
    object_type: "hastalik", label: "", description: "", taxonomy_id: "",
    crop: "", severity: "", source: "manuel",
  });
  const [file, setFile] = useState(null);
  const [uploaded, setUploaded] = useState(null);

  const load = () => {
    api.get("/ai/knowledge-records", { params: { dataset_id: dataset.id, limit: 200 } })
      .then((r) => setRecords(r.data.items || []))
      .catch(() => setRecords([]));
  };
  useEffect(load, [dataset.id]);

  async function uploadFile() {
    if (!file) return null;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("module", "ai_knowledge");
    fd.append("entity_id", dataset.id);
    fd.append("field_key", "media");
    const { data } = await api.post("/uploads", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  }

  async function submit(e) {
    e.preventDefault();
    if (!form.label.trim()) { setMsg("Etiket zorunlu — LLM bu etiketten öğrenir."); return; }
    setBusy(true);
    setMsg("");
    try {
      let media = null;
      if (file) {
        media = await uploadFile();
        setUploaded(media);
      }
      await api.post("/ai/knowledge-records", {
        dataset_id: dataset.id,
        object_type: form.object_type,
        label: form.label.trim(),
        description: form.description.trim(),
        taxonomy_id: form.taxonomy_id || null,
        crop: form.crop || null,
        severity: form.severity || null,
        source: form.source,
        // Medya bilgisi kayda GÖMÜLÜR (ayrı bir tablo açılmaz) — dosyanın
        // kendisi storage.py'de, burada sadece referansı tutulur.
        media: media ? {
          upload_id: media.id, stored_name: media.stored_name,
          original_name: media.original_name || file.name,
          kind: mediaKind(file.name), size: file.size,
        } : null,
        approval_status: "incelemede",
      });
      setMsg("Bilgi kaydı eklendi — Doğrulama sekmesinde uzman onayına düştü.");
      setForm({ ...form, label: "", description: "" });
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      load();
      onChanged && onChanged();
    } catch (err) {
      const d = err.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Kayıt eklenemedi (ai_knowledge:create izni gerekir).");
    } finally { setBusy(false); }
  }

  async function approve(rec) {
    try {
      await api.post(`/ai/knowledge-records/${rec.id}/approve`, {});
      setMsg("Kayıt onaylandı — golden set'e eklendi.");
      load();
    } catch (err) {
      setMsg("Onaylanamadı (ai_prediction:validate izni gerekir).");
    }
  }

  const token = localStorage.getItem("token") || "";
  const mediaUrl = (rec) => rec?.media?.stored_name
    ? `${api.defaults.baseURL || ""}/uploads/file/ai_knowledge/${rec.media.stored_name}?token=${token}`
    : null;

  return (
    <div className="card p-4" data-testid="dataset-editor">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-display text-lg">{dataset.name}</h3>
          <div className="text-xs text-[var(--text-dim)]">
            Kaynak: {dataset.source_type} · {records.length} bilgi kaydı ·
            {" "}{records.filter((r) => r.approval_status === "onayli").length} onaylı
          </div>
        </div>
        <button className="btn btn-ghost text-xs" onClick={onClose}><X size={13} /> Kapat</button>
      </div>

      {msg && <div className="text-sm text-[var(--primary)] mb-3">{msg}</div>}

      {/* YENİ BİLGİ KAYDI — resim/PDF/video + etiket + açıklama */}
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2 mb-4 p-3 rounded-lg bg-[var(--surface-2)]">
        <div className="md:col-span-2 text-sm font-medium flex items-center gap-2">
          <Upload size={14} className="text-[var(--primary)]" /> Yeni Bilgi Kaydı (RAG besleme)
        </div>

        <div>
          <label className="text-xs text-[var(--text-dim)]">Dosya (resim / PDF / video)</label>
          <input ref={fileRef} className="input" type="file"
                 accept=".jpg,.jpeg,.png,.webp,.gif,.tif,.tiff,.pdf,.mp4,.mov,.avi,.mkv,.webm,.txt,.md"
                 onChange={(e) => setFile(e.target.files?.[0] || null)}
                 data-testid="dataset-file" />
          {file && (
            <div className="text-[11px] text-[var(--text-dim)] mt-1">
              {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB · tip: {mediaKind(file.name)}
            </div>
          )}
        </div>

        <div>
          <label className="text-xs text-[var(--text-dim)]">Nesne tipi</label>
          <select className="input" value={form.object_type}
                  onChange={(e) => setForm({ ...form, object_type: e.target.value })}>
            {OBJECT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs text-[var(--text-dim)]">Etiket (LLM bunu öğrenir) *</label>
          <input className="input" required value={form.label} data-testid="dataset-label"
                 placeholder="ör. Cercospora yaprak lekesi — erken evre"
                 onChange={(e) => setForm({ ...form, label: e.target.value })} />
        </div>

        <div>
          <label className="text-xs text-[var(--text-dim)]">Taksonomi bağlantısı</label>
          <select className="input" value={form.taxonomy_id}
                  onChange={(e) => setForm({ ...form, taxonomy_id: e.target.value })}>
            <option value="">— seçilmedi —</option>
            {taxonomy.map((t) => (
              <option key={t.id} value={t.id}>{t.label || t.name || t.key}</option>
            ))}
          </select>
        </div>

        <div className="md:col-span-2">
          <label className="text-xs text-[var(--text-dim)]">Açıklama (bağlam — modele verilecek metin)</label>
          <textarea className="input" rows={3} value={form.description} data-testid="dataset-description"
                    placeholder="Belirtiler, hangi koşulda görüldüğü, önerilen mücadele… Model bu metinden öğrenir."
                    onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>

        <div>
          <label className="text-xs text-[var(--text-dim)]">Ürün</label>
          <input className="input" value={form.crop} placeholder="Şeker Pancarı"
                 onChange={(e) => setForm({ ...form, crop: e.target.value })} />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)]">Şiddet / evre</label>
          <input className="input" value={form.severity} placeholder="hafif / orta / şiddetli"
                 onChange={(e) => setForm({ ...form, severity: e.target.value })} />
        </div>

        <div className="md:col-span-2">
          <button className="btn btn-primary text-sm" disabled={busy} data-testid="dataset-save">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {busy ? " Kaydediliyor…" : " Kaydet ve doğrulamaya gönder"}
          </button>
        </div>
      </form>

      {/* KAYIT LİSTESİ */}
      <div className="space-y-2 max-h-[520px] overflow-y-auto scrollbar">
        {records.length === 0 && (
          <div className="text-sm text-[var(--text-dim)] text-center py-6">
            Bu datasette henüz bilgi kaydı yok. Yukarıdan resim/PDF/video + etiket ekleyin.
          </div>
        )}
        {records.map((r) => {
          const Icon = MEDIA_ICON[r.media?.kind] || Tag;
          const url = mediaUrl(r);
          return (
            <div key={r.id} className="flex gap-3 p-3 rounded-lg border border-[var(--border)]">
              <div className="shrink-0" style={{ width: 84 }}>
                {r.media?.kind === "image" && url ? (
                  <img src={url} alt={r.label} style={{ width: 84, height: 64, objectFit: "cover", borderRadius: 6 }} />
                ) : (
                  <div className="flex items-center justify-center rounded-lg bg-[var(--surface-2)]"
                       style={{ width: 84, height: 64 }}>
                    <Icon size={22} className="text-[var(--text-dim)]" />
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <b className="truncate">{r.label || r.object_type || "—"}</b>
                  <span className={`badge ${r.approval_status === "onayli" ? "badge-a"
                    : r.approval_status === "reddedildi" ? "badge-d" : "badge-b"} text-[10px]`}>
                    {r.approval_status || "taslak"}
                  </span>
                </div>
                <div className="text-xs text-[var(--text-dim)] line-clamp-2">{r.description || "—"}</div>
                <div className="text-[10px] text-[var(--text-dim)] mt-1">
                  {[r.crop, r.severity, r.media?.original_name].filter(Boolean).join(" · ")}
                </div>
              </div>
              {r.approval_status !== "onayli" && (
                <button className="btn btn-ghost text-xs self-start" onClick={() => approve(r)}
                        title="Uzman onayı ver — golden set'e ekle">
                  <CheckCircle2 size={13} /> Onayla
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
