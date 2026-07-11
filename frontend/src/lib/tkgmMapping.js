/**
 * IT-16 — TKGM (Tapu ve Kadastro Genel Müdürlüğü) kamuya açık "Parsel Sorgu"
 * haritasından (parselsorgu.tkgm.gov.tr) dışa aktarılan GeoJSON özellik
 * adlarını (il/ilce/mahalle/ada/parsel) IT-02'nin parsel alanlarına eşler.
 * Resmi bir API/anahtar GEREKMEZ — kullanıcı bu genel haritadan manuel
 * export/kopyala-yapıştır yapar. `backend/server.py`'deki
 * `_extract_tkgm_fields`'in (toplu `/parcels/import-geojson` için) frontend
 * karşılığıdır — tek-parsel akışında (GeoFileImport → mevcut parseli
 * güncelleme) backend'e gitmeden ÖNCE kullanıcıya önizleme göstermek için
 * burada da aynı eşleme tekrarlanır.
 */
const KEY_ALIASES = {
  il: ["il", "il_adi", "il_ad"],
  ilce: ["ilce", "ilce_adi", "ilce_ad"],
  mahalle: ["mahalle", "mahalle_adi", "mahalle_ad", "koy", "koy_adi"],
  ada_no: ["ada_no", "ada", "adano"],
  parsel_no_tapu: ["parsel_no_tapu", "parsel", "parselno", "pin"],
};

const AREA_KEYS = ["alan", "yuzolcum"]; // m² — area_dekar zaten ayrı kontrol edilir

/**
 * @param {Record<string, any>} properties — GeoJSON feature.properties
 * @returns {Record<string, string|number> | null} tanınan alanlar (boşsa null)
 */
export function mapTkgmProperties(properties) {
  if (!properties || typeof properties !== "object") return null;
  const norm = {};
  for (const [k, v] of Object.entries(properties)) {
    norm[String(k).trim().toLowerCase()] = v;
  }

  const out = {};
  for (const [field, aliases] of Object.entries(KEY_ALIASES)) {
    for (const alias of aliases) {
      const v = norm[alias];
      if (v !== undefined && v !== null && v !== "") {
        out[field] = String(v);
        break;
      }
    }
  }

  if (norm["area_dekar"] != null && norm["area_dekar"] !== "") {
    out.area_dekar = Number(norm["area_dekar"]);
  } else {
    for (const key of AREA_KEYS) {
      const v = norm[key];
      if (v !== undefined && v !== null && v !== "") {
        const m2 = Number(v);
        if (!Number.isNaN(m2)) out.area_dekar = Math.round((m2 / 1000) * 10) / 10;
        break;
      }
    }
  }

  return Object.keys(out).length > 0 ? out : null;
}

export const TKGM_FIELD_LABELS = {
  il: "İl",
  ilce: "İlçe",
  mahalle: "Mahalle",
  ada_no: "Ada No",
  parsel_no_tapu: "Parsel No",
  area_dekar: "Alan (dekar)",
};
