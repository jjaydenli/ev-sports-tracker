"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

const TIP_ID = "board-tip";
const GAP = 6;
const EDGE = 8;

type Shown = { text: string; target: HTMLElement };

/**
 * The page's one tooltip: any element with `data-tip` shows its text on hover and on
 * keyboard focus, in a fixed layer so the table's scroll box cannot clip it. An element
 * that already names itself to screen readers sets `data-tip-named`, so the tip is not
 * read twice; any other target is described by the tip while it shows.
 */
export function TipLayer() {
  const [shown, setShown] = useState<Shown | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tipTarget = (event: Event) =>
      event.target instanceof Element
        ? (event.target.closest("[data-tip]") as HTMLElement | null)
        : null;
    const show = (event: Event) => {
      const target = tipTarget(event);
      const text = target?.dataset.tip;
      if (target && text) setShown({ text, target });
    };
    const hide = (event: PointerEvent | FocusEvent) => {
      const target = tipTarget(event);
      // Moving onto the target's own child is not leaving it.
      if (target && event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) {
        return;
      }
      setShown((current) => (current && current.target === target ? null : current));
    };
    const hideAll = () => setShown(null);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") hideAll();
    };
    document.addEventListener("pointerover", show);
    document.addEventListener("pointerout", hide);
    document.addEventListener("focusin", show);
    document.addEventListener("focusout", hide);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hideAll, true);
    return () => {
      document.removeEventListener("pointerover", show);
      document.removeEventListener("pointerout", hide);
      document.removeEventListener("focusin", show);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hideAll, true);
    };
  }, []);

  // Describe the target while the tip shows, unless it already carries its own name.
  useEffect(() => {
    if (!shown || "tipNamed" in shown.target.dataset) return;
    const { target } = shown;
    target.setAttribute("aria-describedby", TIP_ID);
    return () => target.removeAttribute("aria-describedby");
  }, [shown]);

  // Above the target, centred; below it when there is no room; kept inside the viewport.
  useLayoutEffect(() => {
    const tip = tipRef.current;
    if (!shown || !tip) {
      setPos(null);
      return;
    }
    const box = shown.target.getBoundingClientRect();
    const { width, height } = tip.getBoundingClientRect();
    const left = Math.min(
      Math.max(box.left + box.width / 2 - width / 2, EDGE),
      window.innerWidth - width - EDGE,
    );
    const above = box.top - height - GAP;
    setPos({ left, top: above >= EDGE ? above : box.bottom + GAP });
  }, [shown]);

  return (
    <div
      ref={tipRef}
      id={TIP_ID}
      role="tooltip"
      className="tip"
      hidden={!shown}
      style={pos ? { left: pos.left, top: pos.top } : { visibility: "hidden" }}
    >
      {shown?.text}
    </div>
  );
}
