/**
 * IT-14 — Harita Paneli widget'ları için genel (widget-agnostik) render
 * bileşeni. `widget` (bkz. lib/mapWidgets) ve `ctx`'i alır, `widget.compute(ctx)`
 * çağırır ve sonucu Dashboard.jsx'teki KPI kartıyla aynı görsel dilde basar.
 * Bu bileşen HİÇBİR widget'ın iş mantığını bilmez — yeni bir widget eklendiğinde
 * burada değişiklik gerekmez.
 */
export default function WidgetCard({ widget, ctx }) {
  const { icon: Icon, title, accent, key } = widget;

  let result;
  try {
    result = widget.compute(ctx) || {};
  } catch {
    // Bir widget'ın compute'u hata verirse (ör. ileride eklenecek, henüz
    // veri modeli tam oturmamış bir widget) tüm paneli çökertmesin.
    result = { value: "—", hint: "Hesaplanamadı" };
  }

  return (
    <div className="card card-hover p-5 fade-in" data-testid={`map-widget-${key}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent || "bg-[var(--primary)]/10 text-[var(--primary)]"}`}>
          <Icon size={20} />
        </div>
      </div>
      <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">{title}</div>
      <div className="font-display text-3xl mt-1">
        {result.value}
        {result.suffix && <span className="text-base text-[var(--text-dim)] ml-1">{result.suffix}</span>}
      </div>
      {result.hint && <div className="text-[10px] text-[var(--text-dim)] mt-1">{result.hint}</div>}
    </div>
  );
}
