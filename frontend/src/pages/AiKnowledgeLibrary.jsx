/**
 * AI BİLGİ KÜTÜPHANESİ (FAZ 18 / IT-47..53)
 *
 * backend/ai_engine.py'nin admin ekranı — Ayarlar altında tek menü, 4 sekme
 * (mimari doküman Bölüm 14): Kütüphane / Doğrulama / Model Yönetimi / İzleme.
 * PlatformCore.jsx'in tab + card + badge kalıbıyla AYNI (convention #9 —
 * kendine özgü UI deseni İCAT EDİLMEZ). Tüm veri /ai/* uçlarından gelir.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Brain, Database, CheckSquare, Boxes, Activity, Play, RefreshCw } from "lucide-react";

const STATUS_BADGE = { onayli: "badge-a", incelemede: "badge-b", taslak: "badge-neutral", reddedildi: "badge-d",
  saglikli: "badge-a", uyari: "badge-b", hata: "badge-d",
  production: "badge-a", staging: "badge-b", validation: "badge-b", training: "badge-neutral",
  retired: "badge-neutral", rolled_back: "badge-d" };

const TABS = [
  { key: "library", label: "Kütüphane", icon: Database },
  { key: "validation", label: "Doğrulama", icon: CheckSquare },
  { key: "models", label: "Model Yönetimi", icon: Boxes },
  { key: "monitoring", label: "İzleme", icon: Activity },
];

export default function AiKnowledgeLibrary() {
  const [tab, setTab] = useState("library");
  return (
    <div className="p-8 max-w-[1400px]">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 18 · IT-47..53</div>
          <h1 className="font-display text-4xl flex items-center gap-2">
            <Brain className="text-[var(--primary)]" /> AI Bilgi Kütüphanesi
          </h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Agricultural Intelligence Engine — bilgi kütüphanesi, uzman doğrulama, model registry ve izleme.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4 border-b border-[var(--border)]">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`btn btn-ghost text-sm ${tab === t.key ? "text-[var(--primary)]" : "text-[var(--text-dim)]"}`}>
            <t.icon size={15} className="mr-1" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "library" && <LibraryTab />}
      {tab === "validation" && <ValidationTab />}
      {tab === "models" && <ModelsTab />}
      {tab === "monitoring" && <MonitoringTab />}
    </div>
  );
}

function Badge({ value }) {
  return <span className={`badge ${STATUS_BADGE[value] || "badge-neutral"} text-[10px]`}>{value || "-"}</span>;
}

// ---------------- Kütüphane ----------------
function LibraryTab() {
  const [datasets, setDatasets] = useState([]);
  const [records, setRecords] = useState([]);
  const [taxonomy, setTaxonomy] = useState([]);
  const [msg, setMsg] = useState("");
  const [newDs, setNewDs] = useState({ name: "", source_type: "mobil" });
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get("/ai/datasets").then((r) => setDatasets(r.data.items || [])).catch(() => {});
    api.get("/ai/knowledge-records?limit=50").then((r) => setRecords(r.data.items || [])).catch(() => {});
    api.get("/ai/taxonomy").then((r) => setTaxonomy(r.data.items || [])).catch(() => {});
  };
  useEffect(load, []);

  async function seedTaxonomy() {
    setBusy(true);
    try { const r = await api.post("/ai/seed-taxonomy"); setMsg(`Taksonomi seed: ${r.data.created} yeni kayıt`); load(); }
    catch (e) { setMsg("Yetki yok veya hata (ai_knowledge:manage gerekir)"); } finally { setBusy(false); }
  }
  async function createDataset() {
    if (!newDs.name) return;
    try { await api.post("/ai/datasets", newDs); setNewDs({ name: "", source_type: "mobil" }); load(); }
    catch (e) { setMsg("Dataset oluşturulamadı (yetki?)"); }
  }
  async function runPredict(rec) {
    try { const r = await api.post("/ai/predict", { record_id: rec.id }); setMsg(`Tahmin: ${r.data.decision} (güven ${r.data.confidence})`); }
    catch (e) { setMsg("Tahmin başarısız"); }
  }

  return (
    <div className="space-y-4">
      {msg && <div className="card p-3 text-sm text-[var(--primary)]">{msg}</div>}

      <div className="card p-4 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium">Taksonomi (Ürün / Hastalık / Zararlı ontolojisi)</div>
          <div className="text-xs text-[var(--text-dim)]">{taxonomy.length} tanımlı kayıt</div>
        </div>
        <button className="btn btn-ghost text-sm" disabled={busy} onClick={seedTaxonomy}>
          <RefreshCw size={14} className="mr-1" /> 20+ Örnek Seed Et
        </button>
      </div>

      <div className="card p-4">
        <div className="text-sm font-medium mb-2">Yeni Dataset</div>
        <div className="flex items-center gap-2">
          <input className="w-full text-sm" placeholder="Dataset adı (ör. Konya Şeker Pancarı 2026)"
            value={newDs.name} onChange={(e) => setNewDs({ ...newDs, name: e.target.value })} />
          <select className="text-sm" value={newDs.source_type}
            onChange={(e) => setNewDs({ ...newDs, source_type: e.target.value })}>
            {["uydu", "drone", "mobil", "lab", "sensor"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="btn btn-ghost text-sm" onClick={createDataset}>Ekle</button>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] font-display text-lg">Datasetler ({datasets.length})</div>
        {datasets.length === 0 ? <div className="p-6 text-center text-[var(--text-dim)]">Henüz dataset yok</div> :
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Ad</th><th className="p-3">Kaynak</th><th className="p-3">Kayıt</th><th className="p-3">Durum</th>
            </tr></thead>
            <tbody>{datasets.map((d) => (
              <tr key={d.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-3">{d.name}</td><td className="p-3">{d.source_type}</td>
                <td className="p-3">{d.record_count || 0}</td><td className="p-3"><Badge value={d.status} /></td>
              </tr>))}</tbody>
          </table>}
      </div>

      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] font-display text-lg">Bilgi Kayıtları ({records.length})</div>
        {records.length === 0 ? <div className="p-6 text-center text-[var(--text-dim)]">Henüz kayıt yok</div> :
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Nesne Tipi</th><th className="p-3">Onay</th><th className="p-3">Versiyon</th><th className="p-3">Kalite</th><th className="p-3"></th>
            </tr></thead>
            <tbody>{records.map((r) => (
              <tr key={r.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-3">{r.object_type || "-"}</td><td className="p-3"><Badge value={r.approval_status} /></td>
                <td className="p-3">v{r.version}</td><td className="p-3">{r.quality_score ?? 0}</td>
                <td className="p-3"><button className="btn btn-ghost text-xs" onClick={() => runPredict(r)}>
                  <Play size={12} className="mr-1" /> Tahmin</button></td>
              </tr>))}</tbody>
          </table>}
      </div>
    </div>
  );
}

// ---------------- Doğrulama (Active Learning) ----------------
function ValidationTab() {
  const [queue, setQueue] = useState([]);
  const [msg, setMsg] = useState("");
  const load = () => api.get("/ai/validation-queue?status=bekliyor").then((r) => setQueue(r.data.items || [])).catch(() => {});
  useEffect(load, []);

  async function decide(item, decision) {
    try { await api.post(`/ai/validation-queue/${item.id}/decide`, { decision }); setMsg(`Karar: ${decision}`); load(); }
    catch (e) { setMsg("Karar verilemedi (ai_prediction:validate gerekir)"); }
  }

  return (
    <div className="space-y-4">
      {msg && <div className="card p-3 text-sm text-[var(--primary)]">{msg}</div>}
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] font-display text-lg">
          Uzman Doğrulama Kuyruğu ({queue.length})
        </div>
        <div className="p-3 text-xs text-[var(--text-dim)]">
          Öncelik skoruna göre sıralı. Onaylanan kayıt golden dataset'e girer; düzeltilen kayıt eski versiyonu silmeden yeni versiyon olur.
        </div>
        {queue.length === 0 ? <div className="p-6 text-center text-[var(--text-dim)]">Doğrulama bekleyen kayıt yok</div> :
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Sebep</th><th className="p-3">Öncelik</th><th className="p-3">Case</th><th className="p-3"></th>
            </tr></thead>
            <tbody>{queue.map((q) => (
              <tr key={q.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-3">{q.reason}</td><td className="p-3">{q.priority_score}</td>
                <td className="p-3 font-mono text-xs">{q.case_id ? q.case_id.slice(0, 8) : "-"}</td>
                <td className="p-3 flex gap-2">
                  <button className="btn btn-ghost text-xs" onClick={() => decide(q, "onay")}>Onayla</button>
                  <button className="btn btn-ghost text-xs" onClick={() => decide(q, "yeniden_egitim")}>Yeniden Eğit</button>
                </td>
              </tr>))}</tbody>
          </table>}
      </div>
    </div>
  );
}

// ---------------- Model Yönetimi (MLOps) ----------------
function ModelsTab() {
  const [models, setModels] = useState([]);
  const [msg, setMsg] = useState("");
  const [nm, setNm] = useState({ name: "", task_type: "classification" });
  const load = () => api.get("/ai/models").then((r) => setModels(r.data.items || [])).catch(() => {});
  useEffect(load, []);

  async function create() {
    if (!nm.name) return;
    try { await api.post("/ai/models", { ...nm, metrics: { f1: 0.8, precision: 0.8, recall: 0.8, iou: 0.7, drift_score: 0.02 } }); setNm({ name: "", task_type: "classification" }); load(); }
    catch (e) { setMsg("Model oluşturulamadı (ai_model:deploy gerekir)"); }
  }
  async function act(m, action) {
    try { const r = await api.post(`/ai/models/${m.id}/${action}`); setMsg(`${action}: ${r.data.status || "ok"}`); load(); }
    catch (e) { setMsg(e?.response?.data?.detail || `${action} başarısız`); }
  }

  return (
    <div className="space-y-4">
      {msg && <div className="card p-3 text-sm text-[var(--primary)]">{msg}</div>}
      <div className="card p-4">
        <div className="text-sm font-medium mb-2">Yeni Model</div>
        <div className="flex items-center gap-2">
          <input className="w-full text-sm" placeholder="Model adı (ör. hastalik-vit-v1)"
            value={nm.name} onChange={(e) => setNm({ ...nm, name: e.target.value })} />
          <select className="text-sm" value={nm.task_type} onChange={(e) => setNm({ ...nm, task_type: e.target.value })}>
            {["classification", "detection", "segmentation", "change_detection", "anomaly_detection"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="btn btn-ghost text-sm" onClick={create}>Ekle</button>
        </div>
      </div>
      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] font-display text-lg">Modeller ({models.length})</div>
        <div className="p-3 text-xs text-[var(--text-dim)]">
          Deploy: staging→production öncesi golden dataset regresyon kapısı (yeni F1 mevcut production'dan düşükse reddedilir).
        </div>
        {models.length === 0 ? <div className="p-6 text-center text-[var(--text-dim)]">Henüz model yok</div> :
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Ad</th><th className="p-3">Görev</th><th className="p-3">Durum</th><th className="p-3">F1</th><th className="p-3"></th>
            </tr></thead>
            <tbody>{models.map((m) => (
              <tr key={m.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-3">{m.name}</td><td className="p-3">{m.task_type}</td>
                <td className="p-3"><Badge value={m.status} /></td>
                <td className="p-3">{m.metrics?.f1 ?? "-"}</td>
                <td className="p-3 flex gap-2">
                  <button className="btn btn-ghost text-xs" onClick={() => act(m, "train")}>Eğit</button>
                  <button className="btn btn-ghost text-xs" onClick={() => act(m, "deploy")}>Deploy</button>
                  <button className="btn btn-ghost text-xs" onClick={() => act(m, "rollback")}>Rollback</button>
                </td>
              </tr>))}</tbody>
          </table>}
      </div>
    </div>
  );
}

// ---------------- İzleme ----------------
function MonitoringTab() {
  const [stats, setStats] = useState(null);
  const [quota, setQuota] = useState(null);
  useEffect(() => {
    api.get("/ai/stats").then((r) => setStats(r.data)).catch(() => {});
    api.get("/ai/tenant-quota").then((r) => setQuota(r.data)).catch(() => {});
  }, []);

  const cards = stats ? [
    ["Bilgi Kaydı", stats.total_knowledge_records],
    ["Onaylı (Golden)", stats.approved_records],
    ["Toplam Tahmin", stats.total_predictions],
    ["Doğrulama Bekleyen", stats.pending_validation],
    ["Dataset", stats.datasets],
    ["Production Model", stats.production_model || "—"],
  ] : [];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {cards.map(([label, val]) => (
          <div key={label} className="card p-4">
            <div className="text-xs text-[var(--text-dim)] mb-1">{label}</div>
            <div className="font-display text-3xl text-[var(--primary)]">{val}</div>
          </div>
        ))}
      </div>
      {stats?.model_health && (
        <div className="card p-4 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">{stats.model_health.label}</div>
            <div className="text-xs text-[var(--text-dim)]">{stats.model_health.detail}</div>
          </div>
          <Badge value={stats.model_health.status} />
        </div>
      )}
      {quota && (
        <div className="card p-4">
          <div className="text-sm font-medium mb-2">Bulut AI Kotası ({quota.month})</div>
          <div className="text-xs text-[var(--text-dim)]">
            Kullanılan: {quota.cloud_calls_used} / {quota.monthly_limit_calls} çağrı ·
            Kalan: {quota.remaining_calls} · %{quota.used_pct}
          </div>
        </div>
      )}
    </div>
  );
}
