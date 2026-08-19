/**
 * Güvenli sayı biçimlendirme yardımcıları.
 *
 * NEDEN: Ekranlar veriyi doğrudan `x.toFixed(1)` ile basıyordu. Alan bir
 * şekilde eksikse (dış içe aktarma, kısmi kayıt, farklı kaynaktan gelen
 * veri) bu ifade `undefined.toFixed is not a function` ile PATLIYOR ve
 * React tüm SAYFAYI düşürüyor — canlıda Parsel Detayı, Çiftçiler ve
 * Verimlilik ekranlarında yaşandı (2026-08-19).
 *
 * Kural: bir sayı eksikse ekranda "—" görünür, sayfa çalışmaya devam eder.
 * Eksik veriyi 0 GİBİ GÖSTERMEK yanlış olurdu (0 ton ile "bilinmiyor"
 * aynı şey değildir) — bu yüzden varsayılan boş göstergedir.
 */

/** Sayıyı sabit ondalıkla biçimler; değer yoksa `fallback` döner. */
export function fx(value, digits = 1, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : fallback;
}

/** Binlik ayraçlı tam sayı (tr-TR); değer yoksa `fallback`. */
export function fmtNum(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? new Intl.NumberFormat("tr-TR").format(n) : fallback;
}

/** Güvenli bölme — payda 0/yok ise `fallback` (sıfıra bölme = Infinity tuzağı). */
export function ratio(numerator, denominator, digits = 2, fallback = "—") {
  const a = Number(numerator);
  const b = Number(denominator);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return fallback;
  return (a / b).toFixed(digits);
}
