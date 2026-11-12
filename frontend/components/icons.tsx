export const ICON_PROPS = { "aria-hidden": true, focusable: false } as const;

export function Chevron({ className }: { className?: string }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 12 12" {...ICON_PROPS}>
      <path
        d="M3 4.5 6 7.5 9 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Magnifier() {
  return (
    <svg className="mag" width="16" height="16" viewBox="0 0 16 16" {...ICON_PROPS}>
      <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5 14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function Tick() {
  return (
    <span className="tick">
      <svg width="12" height="12" viewBox="0 0 12 12" {...ICON_PROPS}>
        <path
          d="M2.5 6.2 5 8.5 9.5 3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
