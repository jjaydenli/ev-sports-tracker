import { afterEach, describe, expect, it, vi } from "vitest";

import {
  F,
  REVALIDATE_SECONDS,
  fetchBoard,
  formatPacificTime,
  hitHeaderTip,
  pickLine,
} from "@/lib/board";

// 23:04:05 UTC on Nov 19 is 3:04:05 PM in Los Angeles (PST, UTC-8).
const ISO = "2026-11-19T23:04:05Z";

/** ICU puts a narrow no-break space before AM/PM; compare words, not space characters. */
function spaced(text: string): string {
  return text.replace(/\s/g, " ");
}

describe("formatPacificTime", () => {
  it("leaves seconds off by default, as the live board shows it", () => {
    expect(spaced(formatPacificTime(ISO))).toBe("Nov 19, 3:04 PM PT");
  });

  it("adds seconds only when asked", () => {
    expect(spaced(formatPacificTime(ISO, { seconds: true }))).toBe("Nov 19, 3:04:05 PM PT");
    expect(spaced(formatPacificTime(ISO, { seconds: false }))).toBe("Nov 19, 3:04 PM PT");
  });

  it("drops the day only when asked", () => {
    expect(spaced(formatPacificTime(ISO, { seconds: true, date: false }))).toBe("3:04:05 PM PT");
  });
});

describe("fetchBoard cache window", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  /** The `revalidate` fetchBoard hands to fetch, the process boundary. */
  async function revalidateFor(local: string | undefined): Promise<unknown> {
    vi.stubEnv("BOARD_API_URL", "http://api.test");
    vi.stubEnv("BOARD_LOCAL", local);
    const fetchStub = vi.fn(async (_url: string, _init?: { next?: { revalidate?: unknown } }) =>
      Response.json({ board: null, latest_run: null }),
    );
    vi.stubGlobal("fetch", fetchStub);
    await fetchBoard();
    return fetchStub.mock.calls[0]?.[1]?.next?.revalidate;
  }

  it("never caches on the local board", async () => {
    expect(await revalidateFor("1")).toBe(0);
  });

  it.each([undefined, "", "0"])("keeps the live window when BOARD_LOCAL is %j", async (value) => {
    expect(await revalidateFor(value)).toBe(REVALIDATE_SECONDS);
  });
});

describe("pickLine", () => {
  it("spells the side out before Betr's line", () => {
    expect(pickLine({ [F.side]: "under", [F.line]: 6.5 })).toBe("Under 6.5");
    expect(pickLine({ [F.side]: "over", [F.line]: 24.5 })).toBe("Over 24.5");
  });

  it("shows only the line when the side is missing", () => {
    expect(pickLine({ [F.line]: 6.5 })).toBe("6.5");
  });
});

describe("hitHeaderTip", () => {
  // -120 implies 120 / 220 = 54.5454...%, shown to two places.
  it("states Betr's payout and breakeven from the lowest breakeven on the board", () => {
    const rows = [{ [F.betrBreakevenPct]: 57.1 }, { [F.betrBreakevenPct]: 54.5455 }];
    expect(hitHeaderTip(rows)).toBe("Betr pays -120 on every pick. Breakeven 54.55%.");
  });

  it("has no tip when no row carries a breakeven", () => {
    expect(hitHeaderTip([{}])).toBeUndefined();
  });
});
