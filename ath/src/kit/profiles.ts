// profiles.ts — the three built-in profiles and the tier order.
import { PROFILES, type Profile, type ProfileName, TIERS, type Tier } from "./types.ts";

export const BUILTIN_PROFILES: Readonly<Record<ProfileName, Profile>> = {
  owner: { name: "owner", tier: "admin" },
  agent: { name: "agent", tier: "write" },
  reader: { name: "reader", tier: "read" },
};

export const tierRank = (t: Tier): number => TIERS.indexOf(t);

/** The later (narrower) of two profiles in PROFILES order. */
export const narrowerProfile = (a: ProfileName, b: ProfileName): ProfileName => (PROFILES.indexOf(a) >= PROFILES.indexOf(b) ? a : b);

export function parseProfile(v: string, what: string): ProfileName {
  const p = v.trim() as ProfileName;
  if (!PROFILES.includes(p)) throw new Error(`${what} must be one of ${PROFILES.join(", ")} (got '${v}')`);
  return p;
}
