"use client";

import { type RefObject } from "react";

import { Magnifier } from "@/components/icons";

/**
 * Typed text filters players and teams live, within whatever the popup picks leave. It is
 * never a chip and Clear all leaves it alone; its × button or Esc empties it.
 */
export function SearchBox({
  text,
  onText,
  inputRef,
}: {
  text: string;
  onText: (text: string) => void;
  /** The text input, so the zero-result row's Clear search can hand focus back to it. */
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="sbox">
      <Magnifier />
      <input
        ref={inputRef}
        type="text"
        aria-label="Search players or teams"
        placeholder="Search players or teams"
        enterKeyHint="search"
        autoComplete="off"
        spellCheck={false}
        value={text}
        onChange={(event) => onText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && text) onText("");
        }}
      />
      {text && (
        <button
          type="button"
          className="sclear"
          aria-label="Clear search"
          onClick={() => {
            onText("");
            inputRef.current?.focus();
          }}
        >
          ×
        </button>
      )}
    </div>
  );
}
