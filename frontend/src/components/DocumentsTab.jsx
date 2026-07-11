import { useEffect, useState } from "react";
import api, { BACKEND_URL } from "@/api";
import { Upload, Trash2, FileText } from "lucide-react";

/**
 * IT-04 — "Belgeler" sekmesi. Belirli bir dinamik alana (field_key) bağlı
 * OLMAYAN, serbest doküman yüklemeleri için genel amaçlı bileşen (kimlik
 * fotokopisi gibi field_definitions alanına bağlı dosyalar için bkz.
 * DynamicFieldsSection'daki FileFieldWidget — aynı /uploads altyapısını
 * kullanır, sadece field_key=null ile kaydeder).
 *
 * Kullanım: <DocumentsTab module="farmers" entityId={farmer.id} />
 */
export default function DocumentsTab({ module, entityId }) {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    api.get("/uploads", { params: { module, entity_id: entityId } }).then((r) => setDocs(r.data));
  };

  useEffect(() => { load(); }, [module, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("module", module);
      form.append("entity_id", entityId);
      await api.post("/uploads", form, { headers: { "Content-Type": "multipart/form-data" } });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Yükleme başarısız");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleRemove(id) {
    await api.delete(`/uploads/${id}`);
    load();
  }

  const fmtSize = (bytes) => (bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);
  const fileUrl = (d) => `${BACKEND_URL}${d.url}?token=${localStorage.getItem("token")}`;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-display text-lg">Belgeler</h3>
        <label className="btn btn-ghost text-xs cursor-pointer">
          <Upload size={14} /> {uploading ? "Yükleniyor…" : "Belge Ekle"}
          <input type="file" className="hidden" onChange={handleFile} disabled={uploading} />
        </label>
      </div>
      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-2">{error}</div>}
      {docs.length === 0 ? (
        <div className="text-center text-[var(--text-dim)] py-6 text-sm">Henüz belge yüklenmemiş</div>
      ) : (
        <div className="space-y-2">
          {docs.map((d) => (
            <div key={d.id} className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)]">
              <a href={fileUrl(d)} target="_blank" rel="noreferrer"
                 className="flex items-center gap-2 text-sm hover:text-[var(--primary)] min-w-0">
                <FileText size={16} className="text-[var(--text-dim)] shrink-0" />
                <span className="truncate">{d.filename}</span>
                {d.field_key && (
                  <span className="text-[10px] text-[var(--text-dim)] bg-[var(--surface-2)] px-1.5 py-0.5 rounded shrink-0">{d.field_key}</span>
                )}
              </a>
              <div className="flex items-center gap-3 text-xs text-[var(--text-dim)] shrink-0 ml-3">
                <span>{fmtSize(d.size_bytes)}</span>
                <span>{d.uploaded_by}</span>
                <button onClick={() => handleRemove(d.id)} className="text-red-400 hover:text-red-300">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
