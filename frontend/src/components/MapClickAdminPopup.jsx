/**
 * MapClickAdminPopup — haritada PARSEL OLMAYAN bir alana tıklandığında
 * il / ilçe / mahalle bağlantılarını gösteren popup.
 *
 * Kullanıcı isteği (2026-08-19): "kullanıcı parsel olmayan alana tıklarsa
 * pop-up 3 alan açacak (il, ilçe, mahalle) ve tıklanınca demografik veri
 * sayfasını gösterecek."
 *
 * Leaflet'te poligon tıklaması haritaya da yayılır; bu yüzden bileşen
 * kısa bir "az önce bir parsele tıklandı mı" penceresi kullanır — aksi
 * halde her parsel tıklamasında hem parsel popup'ı hem bu popup açılırdı.
 * `MapDrawTools`/`MapSync`'teki ref kalıbıyla AYNI aile.
 */
import { useRef, useState } from "react";
import { Popup, useMapEvents } from "react-leaflet";
import AdminAreaPopupLinks from "@/components/AdminAreaPopupLinks";

export default function MapClickAdminPopup({ disabled = false }) {
  const [point, setPoint] = useState(null);
  const lastLayerClick = useRef(0);

  useMapEvents({
    // Leaflet önce katman (poligon) click'ini, sonra map click'ini tetikler.
    // `originalEvent._stopped` güvenilir değil, bu yüzden zaman penceresi.
    popupopen: () => { lastLayerClick.current = Date.now(); },
    click: (e) => {
      if (disabled) return;
      if (Date.now() - lastLayerClick.current < 300) return;   // parsel popup'ı açıldı
      setPoint([e.latlng.lat, e.latlng.lng]);
    },
  });

  if (!point) return null;
  return (
    <Popup position={point} eventHandlers={{ remove: () => setPoint(null) }} maxWidth={280}>
      <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
        Tıklanan konum · {point[0].toFixed(5)}, {point[1].toFixed(5)}
      </div>
      <AdminAreaPopupLinks lon={point[1]} lat={point[0]} />
    </Popup>
  );
}
