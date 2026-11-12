"use client";

import {
  Fragment,
  type KeyboardEvent,
  type RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { Chevron, Magnifier, Tick } from "@/components/icons";
import {
  allLabel,
  FACET_KEYS,
  FACETS,
  type FacetKey,
  type Filters,
  grayed,
  type MenuOption,
  NONE,
  NO_PICKS,
  pickCount,
  unscoped,
} from "@/lib/filters";

const FOCUSABLE = 'button:not([disabled]):not([tabindex="-1"]), input:not([disabled])';

/**
 * The Filters button and its popup: one home for leagues, games, teams and markets. A category
 * list on the left (tabs on a phone), the picked category's choices on the right, each with its
 * count under the other filters (the search text aside). Picks apply live; OR within a
 * category, AND across them.
 * On a board with two or more leagues the lists group under a foldable heading per league.
 */
export function FiltersPopup({
  options,
  filters,
  onChange,
  counts,
  shown,
  triggerRef,
}: {
  options: Record<FacetKey, MenuOption[]>;
  filters: Filters;
  onChange: (change: Partial<Filters>) => void;
  /** Rows left with this category's own picks ignored: the "All …" row's count. */
  counts: Record<FacetKey, number>;
  /** Rows left with everything applied, the search text included. */
  shown: number;
  /** The Filters button; the chip row hands focus back to it. */
  triggerRef: RefObject<HTMLButtonElement | null>;
}) {
  const [open, setOpen] = useState(false);
  const [cat, setCat] = useState<FacetKey>("league");
  const [query, setQuery] = useState("");
  /** Folded leagues per category; absent until the category is first looked at. */
  const [foldState, setFoldState] = useState<Partial<Record<FacetKey, ReadonlySet<string>>>>({});
  const wrapRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const popId = useId();

  const facet = FACETS[cat];
  const picked = filters[cat];
  const total = pickCount(filters);
  const text = filters.text.trim();

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  };

  const focusList = () =>
    (searchRef.current ?? listRef.current?.querySelector<HTMLElement>(".opt"))?.focus();

  useEffect(() => {
    if (!open) return;
    focusList();
    const onDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // Focus moves once per open, not on every category switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const openOrClose = () => {
    if (open) return close(false);
    setQuery("");
    setOpen(true);
  };

  const pickCategory = (key: FacetKey) => {
    setCat(key);
    setQuery("");
  };

  const toggle = (o: MenuOption) => {
    const next = new Set(picked);
    if (!next.delete(o.value)) next.add(o.value);
    // Unpicked with nothing left, it grays and disables under the focus: move focus first.
    if (grayed(o, next)) focusList();
    onChange({ [cat]: next });
  };

  const needle = query.trim().toLowerCase();
  const leagues = filters.league;
  const list = options[cat].filter(
    (o) => (!needle || o.search.includes(needle)) && (cat === "league" || !leagues.size || leagues.has(o.league)),
  );
  const sectionLeagues = [...new Set(list.map((o) => o.league))];
  const sectioned = cat !== "league" && sectionLeagues.length > 1;
  const folded =
    foldState[cat] ??
    new Set(
      sectionLeagues.filter(
        (lg) => !options[cat].some((o) => o.league === lg && picked.has(o.value)),
      ),
    );
  const toggleFold = (lg: string) => {
    const next = new Set(folded);
    if (!next.delete(lg)) next.add(lg);
    setFoldState((state) => ({ ...state, [cat]: next }));
  };

  // Arrow keys step through the list's rows and league headings; Enter and Space toggle.
  const onListKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = [
      ...(listRef.current?.querySelectorAll<HTMLElement>(".opt:not(:disabled), .lhead") ?? []),
    ];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[Math.max(0, Math.min(items.length - 1, at + step))]?.focus();
  };

  // Esc closes; Tab stays inside the popup.
  const onDialogKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      return close(true);
    }
    if (event.key !== "Tab") return;
    const items = [...(dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const row = (o: MenuOption, tagged: boolean) => {
    const code = cat === "team" ? unscoped(o.value) : null;
    return (
      <button
        key={o.value}
        type="button"
        className={tagged ? "opt" : "opt notag"}
        aria-pressed={picked.has(o.value)}
        disabled={grayed(o, picked)}
        onClick={() => toggle(o)}
      >
        {tagged && <span className="tag">{o.league}</span>}
        <span className="nm">
          {code ?? o.name}
          {code && code !== o.name && <span className="code">{o.name}</span>}
          {o.live && <span className="live">LIVE</span>}
        </span>
        <span className="n">{o.count}</span>
        <Tick />
      </button>
    );
  };

  return (
    <div className="dd" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={total ? "trig set" : "trig"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? popId : undefined}
        onClick={openOrClose}
      >
        <span className="tl">{total ? `Filters · ${total}` : "Filters"}</span>
        <Chevron />
      </button>
      {open && (
        <>
          <div className="scrim" onClick={() => close(true)} />
          <div
            className="fpop"
            id={popId}
            role="dialog"
            aria-modal="true"
            aria-label="Filters"
            ref={dialogRef}
            onKeyDown={onDialogKey}
          >
            <div className="phead">
              <h3>Filters</h3>
              <button type="button" className="xbtn" aria-label="Close" onClick={() => close(true)}>
                ×
              </button>
            </div>
            <div className="fbody">
              <div className="fcats" role="group" aria-label="Category">
                {FACET_KEYS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className="fcat"
                    aria-pressed={key === cat}
                    onClick={() => pickCategory(key)}
                  >
                    <span>{FACETS[key].title}</span>
                    {filters[key].size > 0 && <span className="fn">{filters[key].size}</span>}
                  </button>
                ))}
              </div>
              <div className="fpanel">
                {facet.search && (
                  <div className="lsearch">
                    <Magnifier />
                    <input
                      ref={searchRef}
                      type="search"
                      placeholder={facet.search}
                      aria-label={facet.search}
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </div>
                )}
                <div className="opts" ref={listRef} role="group" aria-label={facet.title} onKeyDown={onListKey}>
                  {!needle && (
                    <button
                      type="button"
                      className="opt notag allrow"
                      aria-pressed={picked.size === 0}
                      onClick={() => onChange({ [cat]: NONE })}
                    >
                      <span className="nm">{allLabel(cat, filters)}</span>
                      <span className="n">{counts[cat]}</span>
                      <Tick />
                    </button>
                  )}
                  {sectioned
                    ? sectionLeagues.map((lg) => {
                        const mine = list.filter((o) => o.league === lg);
                        const shut = !needle && folded.has(lg);
                        const pickedHere = mine.filter((o) => picked.has(o.value)).length;
                        // Nothing left in the league: gray, but it still opens.
                        const gone = mine.every((o) => grayed(o, picked));
                        return (
                          <Fragment key={lg}>
                            <button
                              type="button"
                              className={gone ? "lhead gone" : "lhead"}
                              aria-expanded={!shut}
                              onClick={() => toggleFold(lg)}
                            >
                              <Chevron className="fold" />
                              <span>{lg}</span>
                              <span className="lsum">
                                {pickedHere ? `${pickedHere} picked · ` : ""}
                                {mine.length}
                              </span>
                            </button>
                            {!shut && mine.map((o) => row(o, false))}
                          </Fragment>
                        );
                      })
                    : list.map((o) => row(o, cat !== "league"))}
                  {!list.length && (
                    <p className="nomatch">
                      No {facet.one} matches “{query.trim()}”.
                    </p>
                  )}
                </div>
              </div>
            </div>
            {text && (
              <p className="ftext">
                Search “{text}” also applies ·{" "}
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    // The line goes with the text; focus moves to the list.
                    onChange({ text: "" });
                    focusList();
                  }}
                >
                  Clear
                </button>
              </p>
            )}
            <div className="ffoot">
              <button
                type="button"
                className={total ? "link" : "link idle"}
                aria-hidden={!total}
                tabIndex={total ? undefined : -1}
                onClick={() => {
                  // The button hides once nothing is picked; focus moves to the list.
                  onChange(NO_PICKS);
                  focusList();
                }}
              >
                Clear all
              </button>
              <button type="button" className="more" onClick={() => close(true)}>
                Show {shown} {shown === 1 ? "prop" : "props"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
