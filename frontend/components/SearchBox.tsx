"use client";

import { type RefObject } from "react";

import { Magnifier } from "@/components/icons";

const PLACEHOLDER = "Search props";

/**
 * Typed text filters props (players, teams, markets, leagues) live, within whatever the popup
 * picks leave. It is never a chip and Clear all leaves it alone; its × button or Esc empties it.
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
    <div
      className="sbox"
      onMouseDown={(event) => {
        // Clicking the hint or the padding still lands in the field.
        if (event.target !== inputRef.current && !(event.target as Element).closest("button")) {
          event.preventDefault();
          inputRef.current?.focus();
        }
      }}
    >
      <Magnifier />
      <input
        ref={inputRef}
        type="text"
        aria-label={PLACEHOLDER}
        aria-keyshortcuts="/"
        placeholder={PLACEHOLDER}
        enterKeyHint="search"
        autoComplete="off"
        spellCheck={false}
        // Empty, the field hugs its placeholder so the key hint sits right after the words.
        style={text ? undefined : { width: `${PLACEHOLDER.length * 0.85 + 0.5}ch` }}
        value={text}
        onChange={(event) => onText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && text) onText("");
        }}
      />
      {!text && (
        <kbd className="skey" aria-hidden="true">
          /
        </kbd>
      )}
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
