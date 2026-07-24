/**
 * PUBLIC HARİTA GÖRÜNTÜLEYİCİ (Denetim raporu #9 / Faz 7)
 *
 * `/harita/:token` — login GEREKMEZ (PublicReportViewer.jsx'in `/rapor/:token`
 * sayfasıyla AYNI kalıp).
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import api from "@/api";
import { Map as MapIcon, AlertTriangle } from "lucide-react";

function renderTemplate(tpl, props) {
  return (tpl || "").replace(/\{(\w+)\}/g, (_, k) => (props?.[k] ?? ""));
}

function GeoJsonLayer({ layer }) {
  const map = useMap();
  useEffect(() => {
    if (!layer?.features?.length) return undefined;
    const style = layer.style || {};
    const fc = { type: "FeatureCollection", features: layer.features.map((f) => ({ type: "Feature", geometry: f.geometry, properties: f.properties })) };
    const gj = L.geoJSON(fc, {
      style: () => ({ color: style.color, fillColor: style.fillColor, weight: style.weight, opacity: style.opacity, fillOpacity: style.fillOpacity }),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: 7, color: style.color, fillColor: style.fillColor, weight: style.weight, opacity: style.opacity, fillOpacity: style.fillOpacity }),
      onEachFeature: (feature, l) => {
        const cfg = layer.popup_config || {};
        const title = renderTemplate(cfg.title_template, feature.properties);
        const rows = (cfg.fields || []).map((f) => `<div><b>${f}:</b> ${feature.properties?.[f] ?? "—"}</div>`).join("");
        l.bindPopup(`<div style="min-width:150px"><div style="font-weight:600;margin-bottom:4px">${title || layer.name}</div>${rows}</div>`);
      },
    });
    gj.addTo(map);
    return () => map.removeLayer(gj);
  }, [map, layer]);
  return null;
}

export default function PublicMapViewer() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/maps/${token}`).then((r) => setData(r.data)).catch((err) => setError(err.response?.data?.detail || "Harita yüklenemedi"));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--bg)] grain flex items-center justify-center p-4">
        <div className="card p-8 max-w-md text-center">
          <AlertTriangle className="mx-auto mb-3 text-red-400" size={32}/>
          <div className="font-display text-lg mb-1">Harita Görüntülenemiyor</div>
          <div className="text-sm text-[var(--text-dim)]">{error}</div>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="min-h-screen bg-[var(--bg)] grain flex items-center justify-center text-[var(--text-dim)]">Yükleniyor…</div>;
  }

  const { project, layers } = data;

  return (
    <div className="min-h-screen bg-[var(--bg)] grain p-4 md:p-8" data-testid="public-map-page">
      <div className="max-w-5xl mx-auto">
        <header className="flex items-center gap-2 mb-4">
          <MapIcon className="text-[var(--primary)]" size={22}/>
          <h1 className="font-display text-2xl">{project.name}</h1>
        </header>
        <div className="card overflow-hidden" style={{ height: "70vh" }}>
          <MapContainer center={project.center || [39.0, 35.0]} zoom={project.zoom || 6} style={{ height: "100%", width: "100%" }}>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO"/>
            {(project.layers || []).filter((r) => r.visible).map((r) => layers[r.layer_id] && (
              <GeoJsonLayer key={r.layer_id} layer={layers[r.layer_id]}/>
            ))}
          </MapContainer>
        </div>
      </div>
    </div>
  );
}
