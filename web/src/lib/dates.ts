/** Week arithmetic, kept in one place so the whole app agrees on it. */

/** ISO date (YYYY-MM-DD) for the Monday of the week containing `date`. */
export function mondayOf(date: Date): string {
  const copy = new Date(date);
  // getDay() is 0 for Sunday, so map it to 6 to make Monday the first day.
  const offset = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - offset);
  return toIso(copy);
}

/** ISO date string, using local time rather than UTC.
 *
 * toISOString() would convert to UTC first, which shifts the date by a day
 * for anyone far enough from Greenwich - including all of Australia.
 */
export function toIso(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addDays(iso: string, days: number): string {
  const date = fromIso(iso);
  date.setDate(date.getDate() + days);
  return toIso(date);
}

/** Parse an ISO date as local midnight, avoiding the UTC shift above. */
export function fromIso(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** e.g. "Aug 03 – Aug 09, 2026" */
export function formatWeekRange(mondayIso: string): string {
  const start = fromIso(mondayIso);
  const end = fromIso(addDays(mondayIso, 6));
  const short = (d: Date) =>
    d.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  return `${short(start)} – ${short(end)}, ${end.getFullYear()}`;
}

/** e.g. "Aug 03, 2026" */
export function formatDate(iso: string): string {
  return fromIso(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}
