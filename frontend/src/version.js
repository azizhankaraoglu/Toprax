/**
 * TOPRAX Sürüm Bilgisi — TEK KAYNAK.
 *
 * APP_BUILD formatı: GGAAYYYY-SSDD (gün ay yıl - saat dakika).
 * KURAL: Her tamamlanan işten sonra APP_BUILD bir sonraki damgaya güncellenir
 * (ve gerektiğinde APP_VERSION artırılır). Login açılış sayfası ve
 * Ayarlar > Entegrasyonlar bu tek kaynaktan okur.
 */
export const APP_VERSION = "1.0";
export const APP_BUILD = "17072026-1404";
export const APP_VERSION_LABEL = `v${APP_VERSION} · Build ${APP_BUILD}`;
