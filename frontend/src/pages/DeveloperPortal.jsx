import { useEffect, useState } from "react";
import api, { BACKEND_URL } from "@/api";
import {
  Code2, Download, KeyRound, Webhook, Gauge, ScrollText,
  Plus, Trash2, Copy, Check, ExternalLink, Loader2,
} from "lucide-react";

// PR-26: Geliştirici / Entegrasyon Portalı — Integration Center'ın (IT-01/
// IT-32) dışa açık yüzü. Swagger UI zaten FastAPI varsayılanıyla /docs'ta
// açık; burada Postman indirme, API Key yönetimi (PR-24), Webhook linki
// (IT-32'ye — kendi mantığı YAZILMAZ, mevcut sayfaya link verilir), rate
// limit bilgisi ve changelog bir araya getirilir.

function Section({ icon: Icon, title, children }) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon size={18} className="text-[var(--primary)]" />
        <h2 className="text-white font-medium">{title}</h2>
      </div>
      {children}
    </div>
  );
}

export default function DeveloperPortal() {
  const [info, setInfo] = useState(null);
  const [changelog, setChangelog] = useState("");
  const [keys, setKeys] = useState([]);
  const [newKey, setNewKey] = useState({ name: "", scopes: "", expires_at: "", rate_limit_per_minute: 60 });
  const [createdKey, setCreatedKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function load() {
    api.get("/dev-portal/info").then((r) => setInfo(r.data));
    api.get("/dev-portal/changelog").then((r) => setChangelog(r.data.markdown));
    api.get("/api-keys").then((r) => setKeys(r.data)).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function createKey(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    setCreatedKey(null);
    try {
      const scopes = newKey.scopes.split(",").map((s) => s.trim()).filter(Boolean);
      const { data } = await api.post("/api-keys", {
        name: newKey.name, scopes,
        expires_at: newKey.expires_at || null,
        rate_limit_per_minute: Number(newKey.rate_limit_per_minute) || 60,
      });
      setCreatedKey(data.key);
      setNewKey({ name: "", scopes: "", expires_at: "", rate_limit_per_minute: 60 });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "API anahtarı oluşturulamadı");
    } finally {
      setLoading(false);
    }
  }

  async function revokeKey(id) {
    if (!window.confirm("Bu API anahtarını iptal etmek istediğinize emin misiniz?")) return;
    await api.delete(`/api-keys/${id}`);
    load();
  }

  function copyKey() {
    navigator.clipboard.writeText(createdKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (!info) {
    return <div className="p-6"><Loader2 className="animate-spin text-[var(--primary)]" /></div>;
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Code2 size={24} className="text-[var(--primary)]" />
        <div>
          <h1 className="text-xl font-display text-white">Geliştirici Portalı</h1>
          <p className="text-sm text-[var(--text-dim)]">Dış entegratörler için API dokümantasyonu, koleksiyon ve anahtar yönetimi.</p>
        </div>
      </div>

      <Section icon={ExternalLink} title="API Dokümantasyonu">
        <div className="flex flex-wrap gap-3">
          <a href={`${BACKEND_URL}${info.swagger_url}`} target="_blank" rel="noreferrer"
             className="px-4 py-2 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
            <ExternalLink size={16} /> Swagger UI (/docs)
          </a>
          <a href={`${BACKEND_URL}${info.openapi_url}`} target="_blank" rel="noreferrer"
             className="px-4 py-2 rounded-lg border border-[var(--border)] text-[var(--text-dim)] inline-flex items-center gap-2">
            <Code2 size={16} /> OpenAPI Şeması (JSON)
          </a>
        </div>
      </Section>

      <Section icon={Download} title="Postman / Insomnia Koleksiyonu">
        <p className="text-sm text-[var(--text-dim)] mb-3">
          Her deploy'da otomatik güncellenir — elle düzenlemeyin. Insomnia, Postman v2.1 formatını
          doğrudan içe aktarabilir (File &gt; Import).
        </p>
        <div className="flex flex-wrap gap-3">
          <a href={`${BACKEND_URL}${info.postman_collection_url}`}
             className="px-4 py-2 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center gap-2">
            <Download size={16} /> Collection İndir
          </a>
          <a href={`${BACKEND_URL}${info.postman_environment_url}`}
             className="px-4 py-2 rounded-lg border border-[var(--border)] text-[var(--text-dim)] inline-flex items-center gap-2">
            <Download size={16} /> Ortam Değişkenleri İndir
          </a>
        </div>
      </Section>

      <Section icon={KeyRound} title="API Anahtarlarım">
        <form onSubmit={createKey} className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
          <input required placeholder="Anahtar adı" value={newKey.name}
            onChange={(e) => setNewKey((f) => ({ ...f, name: e.target.value }))}
            className="px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
          <input required placeholder="Scope'lar (virgülle, örn. farmers:view,parcels:view)" value={newKey.scopes}
            onChange={(e) => setNewKey((f) => ({ ...f, scopes: e.target.value }))}
            className="px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white md:col-span-2" />
          <input type="number" placeholder="Rate limit/dk" value={newKey.rate_limit_per_minute}
            onChange={(e) => setNewKey((f) => ({ ...f, rate_limit_per_minute: e.target.value }))}
            className="px-3 py-2 rounded-lg bg-black/20 border border-[var(--border)] text-white" />
          <button disabled={loading} className="px-4 py-2 rounded-lg bg-[var(--primary)] text-[#052e16] font-medium inline-flex items-center justify-center gap-2 md:col-span-4">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />} Yeni API Anahtarı Oluştur
          </button>
        </form>

        {error && <div className="mb-3 text-sm text-red-300">{error}</div>}

        {createdKey && (
          <div className="mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
            <p className="text-xs text-amber-300 mb-2">
              Bu anahtar SADECE ŞİMDİ gösteriliyor — kaydedin, bir daha görüntülenemez.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs text-white bg-black/30 px-2 py-1.5 rounded overflow-x-auto">{createdKey}</code>
              <button onClick={copyKey} className="p-1.5 rounded bg-black/30 text-white">
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
          </div>
        )}

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[var(--text-dim)] border-b border-[var(--border)]">
              <th className="py-2">Ad</th><th>Önek</th><th>Scope'lar</th><th>Son Kullanım</th><th>Durum</th><th></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} className="border-b border-[var(--border)]/50 text-[var(--text-dim)]">
                <td className="py-2 text-white">{k.name}</td>
                <td><code className="text-xs">{k.key_prefix}</code></td>
                <td className="text-xs">{(k.scopes || []).join(", ")}</td>
                <td className="text-xs">{k.last_used_at || "—"}</td>
                <td>{k.revoked ? "İptal edildi" : "Aktif"}</td>
                <td>
                  {!k.revoked && (
                    <button onClick={() => revokeKey(k.id)} className="p-1 text-red-400"><Trash2 size={14} /></button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-center text-[var(--text-dim)]">Henüz API anahtarı yok</td></tr>
            )}
          </tbody>
        </table>
      </Section>

      <Section icon={Gauge} title="Rate Limit">
        <p className="text-sm text-[var(--text-dim)]">{info.rate_limit_note}</p>
      </Section>

      <Section icon={Webhook} title="Webhook'lar">
        <p className="text-sm text-[var(--text-dim)] mb-2">{info.webhook_docs_note}</p>
        <a href="/integration-hub" className="text-sm text-[var(--primary)] inline-flex items-center gap-1">
          Integration Hub'a git <ExternalLink size={14} />
        </a>
      </Section>

      <Section icon={ScrollText} title="Değişiklik Günlüğü">
        <pre className="text-xs text-[var(--text-dim)] whitespace-pre-wrap max-h-96 overflow-y-auto">{changelog}</pre>
      </Section>
    </div>
  );
}
