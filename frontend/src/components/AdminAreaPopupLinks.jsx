/**
 * AdminAreaPopupLinks — harita popup'ında il / ilçe / mahalle (+ parsel)
 * bağlantıları.
 *
 * Kullanıcı isteği (2026-08-19): "parselin üzerine tıklanıldığında pop-up
 * 4 tane menü çıkaracak: il, ilçe, mahalle, parsel — hangisine tıklarsa
 * sayfa detayı ona gidecek. Parsel olmayan alana tıklanırsa 3 alan
 * (il, ilçe, mahalle) çıkacak ve demografik veri sayfasına gidecek."
 *
 * TEK bileşen üç haritada da kullanılır (Parseller, Harita Paneli, Parsel
 * Detayı) — üç yerde aynı popup'ı elle yazmak, birinde düzeltip ötekini
 * unutma tuzağıdır.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { MapPin, Building2, Landmark, Home, ChevronRight } from "lucide-react";

const LEVELS = [
  { key: "il", label: "İl", icon: Landmark },
  { key: "ilce", label: "İlçe", icon: Building2 },
  { key: "mahalle", label: "Mahalle/Köy", icon: Home },
];

/**
 * @param onParcelClick — verilirse "Parsel" satırı DOĞRUDAN detaya gitmez,
 *   bu geri çağrıyı çalıştırır. Parseller sayfasında kullanıcı önce
 *   il/ilçe/mahalle/parsel arasından seçim yapar; "Parsel"i seçtiğinde
 *   popup, parsele özel işlem menüsünü (parsel detayı, sözleşme detayı,
 *   ekim detayı, görev ata) açar — kullanıcının açık isteği (2026-08-19).
 */
export default function AdminAreaPopupLinks({ lon, lat, parcel = null, compact = false,
                                              onParcelClick = null }) {
  const nav = useNavigate();
  const [areas, setAreas] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (lon == null || lat == null) return;
    setAreas(null);
    setErr("");
    api.get("/admin-areas/at", { params: { lon, lat } })
      .then((r) => setAreas(r.data))
      .catch((e) => setErr(e.response?.data?.detail || "İdari alan bilgisi alınamadı"));
  }, [lon, lat]);

  const Item = ({ icon: Icon, label, value, onClick, disabled }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--surface-2)] text-left disabled:opacity-50 disabled:cursor-default"
      style={{ fontSize: 12, border: "none", background: "transparent", cursor: disabled ? "default" : "pointer" }}
    >
      <Icon size={13} className="text-[var(--primary)] shrink-0" />
      <span className="text-[var(--text-dim)]" style={{ minWidth: 62 }}>{label}</span>
      <b className="flex-1 truncate">{value || "—"}</b>
      {!disabled && <ChevronRight size={12} className="text-[var(--text-dim)]" />}
    </button>
  );

  return (
    <div style={{ minWidth: compact ? 200 : 230 }}>
      {parcel && (
        <Item icon={MapPin} label="Parsel" value={parcel.name || parcel.parcel_code}
              onClick={() => (onParcelClick ? onParcelClick(parcel) : nav(`/parseller/${parcel.id}`))} />
      )}
      {!areas && !err && (
        <div className="text-[11px] text-[var(--text-dim)] px-2 py-1">İdari alanlar sorgulanıyor…</div>
      )}
      {err && <div className="text-[11px] text-red-400 px-2 py-1">{err}</div>}
      {areas && LEVELS.map(({ key, label, icon }) => (
        <Item key={key} icon={icon} label={label}
              value={areas[key]?.name}
              disabled={!areas[key]}
              onClick={() => nav(`/idari-alanlar/${areas[key].id}`)} />
      ))}
      {areas && !areas.il && !areas.ilce && !areas.mahalle && (
        <div className="text-[11px] text-[var(--text-dim)] px-2 py-1">
          Bu noktada tanımlı idari sınır yok.
        </div>
      )}
    </div>
  );
}
