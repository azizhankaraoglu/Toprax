import totalFarmers from "./totalFarmers";
import totalParcels from "./totalParcels";
import plantedArea from "./plantedArea";
import emptyParcels from "./emptyParcels";
import activeSeasons from "./activeSeasons";
import harvestPendingArea from "./harvestPendingArea";
import pendingTaskParcels from "./pendingTaskParcels";
import riskyParcels from "./riskyParcels";

/**
 * IT-14 — Widget Kayıt Altyapısı (Harita Paneli'nin asıl teslimi).
 *
 * Her widget kendi dosyasında bağımsız tanımlanır:
 *   { key, title, icon, accent, compute(ctx) => { value, suffix?, hint? } }
 *
 * `ctx` — HaritaPaneli.jsx tarafından kurulan, harita görünümüne/aktif
 * filtreye/seçime göre KAPSAMLANMIŞ ortak bağlam:
 *   { parcels, parcelIds, productionCycles, tasks, farmers }
 * `parcels` zaten kapsamlıdır; `productionCycles`/`tasks`/`farmers` TAM
 * listedir — widget'lar kendi join'ini kendisi yapar (parcel_id/farmer_id
 * üzerinden), böylece hangi ek veriye ihtiyaç duyacağı için sayfanın
 * önceden bir şey hazırlamasına gerek kalmaz.
 *
 * YENİ BİR WİDGET EKLEMEK İÇİN:
 *   1) bu dizine yeni bir dosya ekle (yukarıdaki sözleşmeyi uygulayan)
 *   2) burada import edip MAP_WIDGET_REGISTRY listesine ekle
 * Başka HİÇBİR dosyanın (harita bileşeni, sayfa, backend) değişmesi
 * gerekmez — NDVI/Su Stresi gibi gerçek veriye bağlı widget'lar (FAZ 9.5)
 * ileride bu şekilde eklenecek; `ctx.parcels` zaten `ndvi_latest`/
 * `risk_level` alanlarını taşıyor (bkz. extras.py simüle uydu verisi).
 */
export const MAP_WIDGET_REGISTRY = [
  totalFarmers,
  totalParcels,
  plantedArea,
  emptyParcels,
  activeSeasons,
  harvestPendingArea,
  pendingTaskParcels,
  riskyParcels,
];

export const MAP_WIDGETS_BY_KEY = Object.fromEntries(MAP_WIDGET_REGISTRY.map((w) => [w.key, w]));

export const DEFAULT_WIDGET_KEYS = MAP_WIDGET_REGISTRY.map((w) => w.key);
