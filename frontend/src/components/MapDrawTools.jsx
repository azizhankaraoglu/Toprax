import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";

/**
 * react-leaflet v5 resmi bir <EditControl> bileşeni sunmuyor (o eski
 * react-leaflet-draw paketi v2-3 API'sine göre yazılmıştı ve v5 ile
 * uyumsuz). Bunun yerine useMap() ile ham Leaflet harita instance'ına
 * erişip leaflet-draw'ı doğrudan (vanilla JS gibi) bağlıyoruz — bu
 * yaklaşım react-leaflet'in hangi sürümü olursa olsun çalışır.
 *
 * Props:
 * - active: çizim kontrolü haritada görünsün mü
 * - mode: "polygon" | "edit" | "none" — hangi araç aktif olarak tetiklensin
 * - onCreated(layer, geojson): yeni şekil çizildiğinde
 * - onEdited(geojsonList): mevcut şekil(ler) düzenlendiğinde
 * - existingLayer: düzenleme moduna sokulacak, harici olarak eklenmiş bir L.Polygon (opsiyonel)
 */
export function MapDrawTools({ active, mode = "none", onCreated, onEdited }) {
  const map = useMap();
  const drawnItemsRef = useRef(null);
  const drawControlRef = useRef(null);
  const polygonDrawerRef = useRef(null);

  // FeatureGroup + Control kurulumu — bir kere
  useEffect(() => {
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    drawnItemsRef.current = drawnItems;

    const drawControl = new L.Control.Draw({
      position: "topright",
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: { color: "#4ade80", weight: 2 },
        },
        polyline: false,
        rectangle: false,
        circle: false,
        circlemarker: false,
        marker: false,
      },
      edit: {
        featureGroup: drawnItems,
        remove: true,
      },
    });
    drawControlRef.current = drawControl;

    const handleCreated = (e) => {
      const layer = e.layer;
      drawnItems.addLayer(layer);
      const geojson = layer.toGeoJSON();
      onCreated && onCreated(layer, geojson);
    };
    const handleEdited = (e) => {
      const geojsonList = [];
      e.layers.eachLayer((layer) => geojsonList.push(layer.toGeoJSON()));
      onEdited && onEdited(geojsonList);
    };

    map.on(L.Draw.Event.CREATED, handleCreated);
    map.on(L.Draw.Event.EDITED, handleEdited);

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      map.off(L.Draw.Event.EDITED, handleEdited);
      map.removeLayer(drawnItems);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Kontrolü haritaya ekle/kaldır (active prop'una göre)
  useEffect(() => {
    if (!drawControlRef.current) return;
    if (active) {
      map.addControl(drawControlRef.current);
    } else {
      map.removeControl(drawControlRef.current);
      // Araç kapatılınca geçici çizilmiş şekiller haritada birikmesin diye temizlenir
      // (kalıcı hale gelen parseller zaten ayrı bir <Polygon> olarak render ediliyor).
      drawnItemsRef.current?.clearLayers();
    }
    return () => {
      try { map.removeControl(drawControlRef.current); } catch { /* zaten kaldırılmış olabilir */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, map]);

  // "polygon" modunda otomatik olarak çizim aracını tetikle (kullanıcı
  // ayrıca L.Control butonuna tıklamak zorunda kalmasın diye)
  useEffect(() => {
    if (!active || mode !== "polygon") return;
    const drawer = new L.Draw.Polygon(map, {
      allowIntersection: false,
      showArea: true,
      shapeOptions: { color: "#4ade80", weight: 2 },
    });
    polygonDrawerRef.current = drawer;
    drawer.enable();
    return () => {
      try { drawer.disable(); } catch { /* zaten tamamlanmış/iptal olmuş olabilir */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, mode, map]);

  /** Dışarıdan çağrılabilecek: mevcut çizilenleri temizle */
  return null;
}

export function clearDrawnItems(map) {
  map.eachLayer((layer) => {
    if (layer instanceof L.FeatureGroup) {
      layer.clearLayers();
    }
  });
}
