// tidewatch.ts — the typed core of the tide reader (twin of a TypeScript source)
export interface Tide {
  port: string;
  kind: "high" | "low";
  time: string;
  height: number;
}
export function next(events: Tide[], now: number): Tide | undefined {
  return events.find((e) => Date.parse(e.time) >= now);
}
export const format = (e: Tide): string => `${e.port.padEnd(12)} ${e.kind.padEnd(5)} ${e.time}  ${e.height.toFixed(1)} m`;
