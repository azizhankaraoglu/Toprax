/**
 * IT-10/IT-12 ortak yardımcı — bir Query Engine modülü + kaydı, o kaydın
 * detay sayfası rotasına çevirir. Dashboard araması ve WorkspaceDrawer.jsx
 * (Favoriler/Son Açılanlar) bu eşlemeyi paylaşır.
 *
 * SON HAL: sözleşmenin artık kendi detay sayfası var (/sozlesmeler/:id,
 * ContractDetail.jsx) — eski "parsele yönlendir" davranışı kaldırıldı.
 */
export function moduleDetailPath(module, item) {
  if (module === "farmers") return `/ciftciler/${item.id}`;
  if (module === "parcels") return `/parseller/${item.id}`;
  if (module === "production_cycles") return `/uretim-sezonlari/${item.id}`;
  if (module === "contracts") return `/sozlesmeler/${item.id}`;
  return null;
}
