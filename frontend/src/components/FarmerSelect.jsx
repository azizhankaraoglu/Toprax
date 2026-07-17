/**
 * FarmerSelect — Aranabilir çiftçi seçici (combobox).
 *
 * Yeni bir bağımlılık EKLEMEDEN (Karar Protokolü) basit bir arama+dropdown:
 * ad / üye no / telefon üzerinden filtreler. `farmers` prop verilirse onu
 * kullanır (Parcels.jsx zaten yüklüyor), verilmezse kendisi `/farmers` çeker
 * (ParcelDetail.jsx gibi listeyi ayrı tutmayan yerler için).
 *
 * value    : seçili farmer.id (veya null)
 * onChange : (farmerId | null) => void
 */
import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/api";
import { Search, X } from "lucide-react";

const trLower = (s) => (s ?? "").toString().toLocaleLowerCase("tr");

export default function FarmerSelect({
  value,
  onChange,
  farmers: farmersProp = null,
  placeholder = "Çiftçi ara ve seç…",
  allowClear = true,
  testId,
}) {
  const [farmers, setFarmers] = useState(farmersProp || []);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const boxRef = useRef(null);

  useEffect(() => {
    if (farmersProp) { setFarmers(farmersProp); return; }
    api.get("/farmers", { params: { limit: 2000 } })
      .then((r) => setFarmers(Array.isArray(r.data) ? r.data : (r.data?.farmers || [])))
      .catch(() => setFarmers([]));
  }, [farmersProp]);

  useEffect(() => {
    function onDoc(e) { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const selected = farmers.find((f) => f.id === value) || null;

  const filtered = useMemo(() => {
    const needle = trLower(q);
    if (!needle) return farmers.slice(0, 50);
    return farmers.filter((f) =>
      trLower(f.full_name).includes(needle) ||
      trLower(f.member_no).includes(needle) ||
      trLower(f.phone).includes(needle)
    ).slice(0, 50);
  }, [farmers, q]);

  return (
    <div className="relative" ref={boxRef} data-testid={testId}>
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-dim)] pointer-events-none" />
        <input
          className="input pl-8"
          placeholder={placeholder}
          value={open ? q : (selected ? `${selected.full_name} (${selected.member_no})` : "")}
          onFocus={() => { setOpen(true); setQ(""); }}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        />
        {allowClear && value && !open && (
          <button type="button"
            onClick={() => onChange(null)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-dim)] hover:text-red-400"
            title="Seçimi temizle">
            <X size={14} />
          </button>
        )}
      </div>
      {open && (
        <div className="absolute z-[2000] mt-1 w-full max-h-60 overflow-auto card p-1 shadow-xl border border-[var(--border)]">
          {filtered.length === 0 && (
            <div className="px-2 py-2 text-xs text-[var(--text-dim)]">Eşleşen çiftçi yok</div>
          )}
          {filtered.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => { onChange(f.id); setOpen(false); setQ(""); }}
              className={`block w-full text-left px-2 py-1.5 rounded hover:bg-[var(--surface-2)] text-sm ${f.id === value ? "bg-[var(--surface-2)]" : ""}`}
            >
              <div>{f.full_name}</div>
              <div className="text-xs text-[var(--text-dim)]">
                {f.member_no}{f.phone ? " · " + f.phone : ""}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
