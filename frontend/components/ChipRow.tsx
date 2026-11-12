"use client";

import { type RefObject, useEffect, useRef } from "react";

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

  const current = activePicks(options, filters);
  const ids = current.map((chip) => chip.id);
  order.current = [
    ...order.current.filter((id) => ids.includes(id)),
    ...ids.filter((id) => !order.current.includes(id)),
  ];
  const chips = order.current.map((id) => current.find((chip) => chip.id === id) as Chip);

  // After a chip goes, focus the one that took its place (or the new last one).
  useEffect(() => {
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
        <span key={chip.id} title={chip.title} className="chip">
          <span className="cname">{chip.label}</span>
          <button
            type="button"
            aria-label={`Remove ${chip.label}`}
            onClick={() => {
              focusAt.current = i;
              onChange(chip.remove);
            }}
          >
            ×
          </button>
        </span>
      ))}
      <button
        type="button"
        className="link"
        onClick={() => {
          focusAt.current = 0;
          onChange(NO_PICKS);
        }}
      >
        Clear all
      </button>
    </div>
  );
}
