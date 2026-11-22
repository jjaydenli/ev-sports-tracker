/**
 * The page's one info icon: a button that shows `tip` on hover, focus and tap (TipLayer
 * owns the showing). Never put it inside another button: a tap would do both.
 */
export function InfoTip({ tip, label }: { tip: string; label: string }) {
  return (
    <button type="button" className="info-btn" aria-label={label} data-tip={tip}>
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <circle cx="8" cy="8" r="6.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="8" cy="4.9" r="1" fill="currentColor" />
        <path d="M8 7.2v4.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </button>
  );
}
