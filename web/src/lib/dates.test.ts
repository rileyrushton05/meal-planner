import { describe, expect, it } from "vitest";

import { addDays, formatWeekRange, fromIso, mondayOf, toIso } from "./dates";

describe("mondayOf", () => {
  it.each([
    ["2026-08-03", "Monday itself"],
    ["2026-08-06", "midweek"],
    ["2026-08-09", "Sunday, the last day of the week"],
  ])("snaps %s back to its Monday (%s)", (iso) => {
    expect(mondayOf(fromIso(iso))).toBe("2026-08-03");
  });

  it("does not shift a date across the UTC boundary", () => {
    // Late-evening local time is the next day in UTC, so any
    // toISOString()-based implementation reports the wrong week for
    // anyone east of Greenwich.
    const lateSunday = new Date(2026, 7, 9, 23, 30);
    expect(mondayOf(lateSunday)).toBe("2026-08-03");
  });
});

describe("toIso", () => {
  it("uses local date parts rather than UTC", () => {
    expect(toIso(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });

  it("zero-pads months and days", () => {
    expect(toIso(new Date(2026, 8, 7))).toBe("2026-09-07");
  });
});

describe("addDays", () => {
  it("moves forward a week", () => {
    expect(addDays("2026-08-03", 7)).toBe("2026-08-10");
  });

  it("moves backward a week", () => {
    expect(addDays("2026-08-03", -7)).toBe("2026-07-27");
  });

  it("crosses a month boundary", () => {
    expect(addDays("2026-08-31", 1)).toBe("2026-09-01");
  });

  it("crosses a year boundary", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
});

describe("formatWeekRange", () => {
  it("spans Monday to Sunday and ends with the year", () => {
    const formatted = formatWeekRange("2026-08-03");
    expect(formatted).toContain("–");
    expect(formatted).toContain("2026");
  });
});
