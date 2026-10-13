// report.ts — a finding: its code, severity, where, what. Blocking findings stop a pass from signing (spec §13).
export type Severity = "block" | "soft" | "list";

export interface Finding {
  code: string;
  severity: Severity;
  subject: string;
  at?: string;
  msg: string;
}

export const blocking = (f: Finding[]): Finding[] => f.filter((x) => x.severity === "block");
