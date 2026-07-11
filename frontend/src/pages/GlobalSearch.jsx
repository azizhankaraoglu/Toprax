/**
 * GLOBAL ARAMA (IT-10) — Çiftçi/Parsel/Sözleşme/Üretim Sezonu tek kutu arama.
 * Backend: GET /search?q=... (query_engine.py) — modül bazlı contains+OR,
 * kullanıcının izni olmayan modüller sessizce atlanır.
 */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "@/api";
import { Search, Users, Map, FileText, Sprout } from "lucide-react";
import { moduleDetailPath } from "@/lib/moduleRoutes";

const MODULE_META = {
  farmers: { label: "Çiftçiler", icon: Users },
  parcels: { label: "Parseller", icon: Map },
  contracts: { label: "Sözleşmeler", icon: FileText },
  production_cycles: { label: "Üretim Sezonları", icon: Sprout },
};

function rowLabel(module, item) {
  if (module === "farmers") return item.full_name;
  if (module === "parcels") return item.name;
  if (module === "contracts") return `${item.crop} — ${item.variety} (${item.season})`;
  if (module === "production_cycles") return `${item.crop} — ${item.year} ${item.season}`;
  return item.id;
}

function rowSubtitle(module, item) {
  if (module === "farmers") return `${item.member_no || ""} · ${item.village || ""}`.trim();
  if (module === "parcels") return item.village || "";
  if (module === "contracts") return item.status || "";
  if (module === "production_cycles") return item.status || "";
  return "";
}

export default function GlobalSearch() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const query = params.get("q") || "";
    if (query.trim().length < 2) { setResults({}); return; }
    setLoading(true);
    api.get("/search", { params: { q: query } })
      .then((r) => setResults(r.data.results))
      .finally(() => setLoading(false));
  }, [params]);

  function submit(e) {
    e.preventDefault();
    setParams(q.trim() ? { q: q.trim() } : {});
  }

  function goTo(module, item) {
    const path = moduleDetailPath(module, item);
    if (path) nav(path);
  }

  const moduleKeys = Object.keys(results);

  return (
    <div className="p-8 max-w-[1000px]" data-testid="global-search-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">TEK KUTU ARAMA</div>
        <h1 className="font-display text-4xl">Global Arama</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Çiftçi, parsel, sözleşme ve üretim sezonlarında birlikte arayın.</p>
      </header>

      <form onSubmit={submit} className="card p-4 mb-6">
        <div className="relative">
          <Search size={16} className="absolute left-4 top-3.5 text-[var(--text-dim)]" />
          <input
            data-testid="global-search-input"
            className="input pl-11"
            placeholder="Ad, TC, köy, ürün, sezon… (en az 2 karakter)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
          />
        </div>
      </form>

      {loading && <div className="text-[var(--text-dim)] text-sm">Aranıyor…</div>}

      {!loading && params.get("q") && moduleKeys.length === 0 && (
        <div className="text-[var(--text-dim)] text-sm">Sonuç bulunamadı.</div>
      )}

      {moduleKeys.map((module) => {
        const meta = MODULE_META[module];
        const group = results[module];
        if (!meta || !group) return null;
        const Icon = meta.icon;
        return (
          <div key={module} className="card p-4 mb-4">
            <div className="flex items-center gap-2 text-sm font-medium mb-3">
              <Icon size={15} /> {meta.label}
              <span className="text-[var(--text-dim)] font-normal">({group.total})</span>
            </div>
            <div className="space-y-1">
              {group.items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => goTo(module, item)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--surface-2)] flex items-center justify-between"
                >
                  <span>{rowLabel(module, item)}</span>
                  <span className="text-xs text-[var(--text-dim)]">{rowSubtitle(module, item)}</span>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
