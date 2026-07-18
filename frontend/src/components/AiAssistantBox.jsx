/**
 * SON HAL — AI Asistanı kutusu (ortak bileşen).
 *
 * HaritaPaneli'nin "AI Harita Asistanı" handler'ının genelleştirilmiş hali —
 * artık Parseller ve Çiftçiler sayfalarında da kullanılır. POST /ai/copilot
 * (extras.py) doğal dil sorgusunu Query Engine filtresine çevirir; AI
 * yapılandırılmamışsa anahtar-kelime fallback'i çalışır (ai_powered:false
 * dürüstçe gösterilir).
 *
 * Kullanım:
 *   <AiAssistantBox module="farmers" onResults={(items) => setList(items)}
 *                   placeholder="Konya'daki A karneli çiftçileri göster" />
 */
import { useState } from "react";
import api from "@/api";
import { Sparkles, X } from "lucide-react";

export default function AiAssistantBox({ module = "parcels", onResults, placeholder, testId = "ai-assistant" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function submit(e) {
    e?.preventDefault();
    if (!query.trim()) return;
    setBusy(true); setResult(null);
    try {
      const { data } = await api.post("/ai/copilot", { query: query.trim(), module });
      onResults(data.items || data.parcels || []);
      setResult({ summary: data.summary, count: data.result_count, ai: data.ai_powered });
    } catch (err) {
      setResult({ summary: err.response?.data?.detail || "Sorgu işlenemedi.", count: 0 });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-ghost" data-testid={`${testId}-open`}>
        <Sparkles size={15} /> AI Asistanı
      </button>
    );
  }

  return (
    <div className="card p-3 w-full" data-testid={testId}>
      <form onSubmit={submit} className="flex items-center gap-2">
        <Sparkles size={16} className="text-[var(--primary)] shrink-0" />
        <input
          className="input flex-1"
          placeholder={placeholder || "Doğal dille sorun…"}
          value={query} onChange={(e) => setQuery(e.target.value)}
          autoFocus data-testid={`${testId}-input`}
        />
        <button type="submit" className="btn btn-primary" disabled={busy} data-testid={`${testId}-submit`}>
          {busy ? "…" : "Sor"}
        </button>
        <button type="button" onClick={() => { setOpen(false); setResult(null); }}
                className="text-[var(--text-dim)] hover:text-white"><X size={16} /></button>
      </form>
      {result && (
        <div className="text-xs mt-2 text-[var(--text-dim)]" data-testid={`${testId}-result`}>
          <b className="text-[var(--text)]">{result.count}</b> sonuç — {result.summary}
          {result.ai === false && " (anahtar kelime eşleştirmesi — AI servisi yapılandırılmamış)"}
        </div>
      )}
    </div>
  );
}
