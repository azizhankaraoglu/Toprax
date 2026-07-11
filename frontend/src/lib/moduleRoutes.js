/**
 * IT-10/IT-12 ortak yardımcı — bir Query Engine modülü + kaydı, o kaydın
 * detay sayfası rotasına çevirir. GlobalSearch.jsx ve WorkspaceDrawer.jsx
 * (Favoriler/Son Açılanlar) bu eşlemeyi paylaşır.
 *
 * contracts'ın kendi detay sayfası yok (bkz. CLAUDE.md IT-03 notu) —
 * parcel_id varsa parselin sayfasına yönlendirilir.
 */
export function moduleDetailPath(module, item) {
  if (module === "farmers") return `/ciftciler/${item.id}`;
  if (module === "parcels") return `/parseller/${item.id}`;
  if (module === "production_cycles") return `/uretim-sezonlari/${item.id}`;
  if (module === "contracts" && item.parcel_id) return `/parseller/${item.parcel_id}`;
  return null;
}
