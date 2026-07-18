/**
 * SON HAL — Aranabilir parsel seçici (ortak bileşen).
 *
 * EkimPlanlama.jsx'in (Ekim Karar Motoru) debounce'lu combobox'ı buraya
 * çıkarıldı; artık Ekim Kaydı, Sulama, Operasyon ve Karar Motoru AYNI
 * bileşeni kullanır. Backend: GET /ekim-planlama/parcel-search
 * (agronomy.py — il/ilçe/mahalle/ada/parsel no/ad ile arar, farmer_name
 * ve hazır "display" metni döner). Yeni bağımlılık YOK (bilinçli).
 *
 * Kullanım:
 *   <ParcelPicker value={parcel} onSelect={setParcel} />
 *   value null ise arama kutusu, doluysa seçili-parsel çipi gösterilir.
 */
import { useEffect, useRef, useState } from "react";
import api from "@/api";
import { X } from "lucide-react";

export default function ParcelPicker({ value, onSelect, placeholder, testId = "parcel-picker" }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setResults([]); return; }
    timer.current = setTimeout(() => {
      api.get(`/ekim-planlama/parcel-search?q=${encodeURIComponent(q)}`)
        .then((r) => { setResults(r.data); setOpen(true); })
        .catch(() => setResults([]));
    }, 300);
    return () => timer.current && clearTimeout(timer.current);
  }, [q]);

  if (value) {
    return (
      <div className="flex items-center gap-2 input" data-testid={`${testId}-selected`}>
        <div className="flex-1 min-w-0">
          <div className="text-sm truncate">{value.display || value.name}</div>
          <div className="text-[11px] text-[var(--text-dim)] truncate">
            {value.farmer_name || "Çiftçi atanmamış"} · {value.area_dekar || "?"} dekar
          </div>
        </div>
        <button type="button" onClick={() => { onSelect(null); setQ(""); }}
                className="text-[var(--text-dim)] hover:text-white shrink-0"
                data-testid={`${testId}-clear`} title="Seçimi değiştir">
          <X size={14} />
        </button>
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <input
        className="input" data-testid={testId}
        placeholder={placeholder || "İl, ilçe, mahalle, ada, parsel no veya ad ile ara…"}
        value={q} onChange={(e) => setQ(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
      />
      {open && results.length > 0 && (
        <div className="card" style={{
          position: "absolute", zIndex: 30, left: 0, right: 0, top: "100%",
          maxHeight: 300, overflowY: "auto", padding: 4,
        }}>
          {results.map((r) => (
            <div key={r.id} data-testid={`${testId}-option`}
                 onMouseDown={(e) => e.preventDefault()}
                 onClick={() => { onSelect(r); setOpen(false); setQ(""); }}
                 style={{ padding: "8px 10px", cursor: "pointer", borderRadius: 6 }}
                 onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(125,125,125,.12)")}
                 onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{r.display}</div>
              <div className="text-[11px] text-[var(--text-dim)]">
                {r.farmer_name || "Çiftçi atanmamış"} · {r.area_dekar || "?"} dekar
              </div>
            </div>
          ))}
        </div>
      )}
      {q.trim().length >= 2 && results.length === 0 && (
        <p className="text-[11px] text-[var(--text-dim)] mt-1">Eşleşen parsel bulunamadı.</p>
      )}
    </div>
  );
}
