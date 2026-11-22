"use client";

import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  activePicks,
  type Chip,
  type FacetKey,
  type Filters,
  type MenuOption,
  NO_PICKS,
} from "@/lib/filters";

/**
 * One chip per popup pick, oldest first, in a row under the bar, then Clear all, which takes
 * off the chips and nothing else. The row is absent while nothing is picked.
 */
export function ChipRow({
  options,
  filters,
  onChange,
  filtersButtonRef,
}: {
  options: Record<FacetKey, MenuOption[]>;
  filters: Filters;
  onChange: (change: Partial<Filters>) => void;
  /** Where focus goes once the last chip is gone, and the row with it. */
  filtersButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  /** Chip ids in the order they were added; a chip that goes keeps no place. */
  const order = useRef<string[]>([]);
  const rowRef = useRef<HTMLDivElement>(null);
  /** The chip position to focus once a removal has re-rendered the row. */
  const focusAt = useRef<number | null>(null);
  /** Chips playing their exit, then the change to apply and the position to focus. */
  const [leaving, setLeaving] = useState<{
    ids: string[];
    change: Partial<Filters>;
    at: number;
  } | null>(null);
  const leave = (ids: string[], change: Partial<Filters>, at: number) => {
    if (!leaving) setLeaving({ ids, change, at });
  };
  /** Where each chip (and Clear all) sat before a removal, so the rest slide into the gap. */
  const before = useRef<Map<Element, DOMRect> | null>(null);
  const gone = () => {
    if (!leaving) return;
    const kids = Array.from(rowRef.current?.children ?? []);
    before.current = new Map(kids.map((el) => [el, el.getBoundingClientRect()]));
    focusAt.current = leaving.at;
    setLeaving(null);
    onChange(leaving.change);
  };

  useLayoutEffect(() => {
    const was = before.current;
    const row = rowRef.current;
    before.current = null;
    if (!was || !row) return;
    const style = getComputedStyle(row);
    // The minifier may serve 240ms as .24s.
    const open = style.getPropertyValue("--t-open").trim();
    const duration = parseFloat(open) * (open.endsWith("ms") ? 1 : 1000);
    if (!duration) return;
    const easing = style.getPropertyValue("--ease-open").trim();
    for (const el of Array.from(row.children)) {
      const from = was.get(el);
      if (!from) continue;
      const to = el.getBoundingClientRect();
      const dx = from.left - to.left;
      const dy = from.top - to.top;
      if (dx || dy) el.animate({ translate: [`${dx}px ${dy}px`, "0 0"] }, { duration, easing });
    }
  });

  const current = activePicks(options, filters);
  const ids = current.map((chip) => chip.id);
  order.current = [
    ...order.current.filter((id) => ids.includes(id)),
    ...ids.filter((id) => !order.current.includes(id)),
  ];
  const chips = order.current.map((id) => current.find((chip) => chip.id === id) as Chip);

  // After a chip goes, focus the one that took its place (or the new last one).
  useEffect(() => {
    // A refresh took the leaving chip away before its exit ended: apply its change now.
    if (leaving && !ids.includes(leaving.ids[0])) return gone();
    const at = focusAt.current;
    if (at === null) return;
    focusAt.current = null;
    const buttons = rowRef.current?.querySelectorAll<HTMLElement>(".chip button");
    if (buttons?.length) buttons[Math.min(at, buttons.length - 1)].focus();
    else filtersButtonRef.current?.focus();
  });

  if (!chips.length) return null;

  return (
    <div className="chips" role="group" aria-label="Picked filters" ref={rowRef}>
      {chips.map((chip, i) => (
        <span
          key={chip.id}
          title={chip.title}
          className={leaving?.ids.includes(chip.id) ? "chip leaving" : "chip"}
          onAnimationEnd={(event) => {
            if (event.animationName === "shrink" && chip.id === leaving?.ids[0]) gone();
          }}
        >
          <button
            type="button"
            aria-label={`Remove ${chip.label}`}
            onClick={() => leave([chip.id], chip.remove, i)}
          >
            ×
          </button>
          <span className="cname">{chip.label}</span>
        </span>
      ))}
      <button
        type="button"
        className="link"
        onClick={() => leave(ids, NO_PICKS, 0)}
      >
        Clear all
      </button>
    </div>
  );
}
