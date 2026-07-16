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
 * - mode: "polygon" | "edit" | "select" | "none" — hangi araç aktif olarak tetiklensin
 *   ("select" — IT-15: polygon/rectangle/circle ÜÇÜNÜ de araç çubuğunda sunar,
 *   otomatik tetiklemez, kullanıcı hangisini kullanacağını L.Control.Draw
 *   toolbar'ından seçer — haritada parsel seçmek için, geometri tanımlamak için DEĞİL)
 * - onCreated(layer, geojson, shapeType): yeni şekil çizildiğinde (shapeType:
 *   "polygon"|"rectangle"|"circle" — leaflet-draw'ın e.layerType'ı, circle için
 *   geojson.geometry bir Point'tir, gerçek geometri layer.getLatLng()/getRadius()'tan kurulmalı)
 * - onEdited(geojsonList): mevcut şekil(ler) düzenlendiğinde
 * - existingLayer: düzenleme moduna sokulacak, harici olarak eklenmiş bir L.Polygon (opsiyonel)
 */
export function MapDrawTools({ active, mode = "none", onCreated, onEdited }) {
  const map = useMap();
  const drawnItemsRef = useRef(null);
  const drawControlRef = useRef(null);
  const polygonDrawerRef = useRef(null);
  const isSelectMode = mode === "select";

  // IT-15 sırasında keşfedildi: aşağıdaki useEffect SADECE `[map]` değiştiğinde
  // (yani sadece bir kere) çalışır — `handleCreated`/`handleEdited` map.on() ile
  // kaydedildiğinde `onCreated`/`onEdited` parametrelerinin İLK render'daki
  // değerine kilitlenir. Çağıran taraf (örn. HaritaPaneli) her render'da bu
  // callback'i tazeler ama olay dinleyicisi hiç yeniden bağlanmadığı için hep
  // ESKİ (stale) closure çalışır — MapSync'teki `onChangeRef` ile aynı aile
  // (bkz. HaritaPaneli.jsx). "select" modunda callback'in kapattığı state
  // (örn. filteredParcels/mapBounds) her render değiştiğinden bu, gerçek bir
  // hataya yol açıyordu (şekil içindeki parseller mapBounds'a göre DEĞİL, ilk
  // mount anındaki — genelde boş/sınırsız — duruma göre seçiliyordu). Çözüm:
  // ref ile HER ZAMAN en güncel callback'i takip et.
  const onCreatedRef = useRef(onCreated);
  onCreatedRef.current = onCreated;
  const onEditedRef = useRef(onEdited);
  onEditedRef.current = onEdited;

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
          shapeOptions: { color: "#FF8C00", weight: 2 },
        },
        polyline: false,
        rectangle: isSelectMode ? { shapeOptions: { color: "#3B82F6", weight: 2 } } : false,
        circle: isSelectMode ? { shapeOptions: { color: "#3B82F6", weight: 2 } } : false,
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
      onCreatedRef.current && onCreatedRef.current(layer, geojson, e.layerType);
    };
    const handleEdited = (e) => {
      const geojsonList = [];
      e.layers.eachLayer((layer) => geojsonList.push(layer.toGeoJSON()));
      onEditedRef.current && onEditedRef.current(geojsonList);
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
      shapeOptions: { color: "#FF8C00", weight: 2 },
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
