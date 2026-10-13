// caller.ts — who is calling: the profile from the terminal and Claude ancestry (ancestry outranks the terminal),
// narrowed by ATH_PROFILE / --profile (narrow-only); the actor.
import { AthError } from "./errors.ts";
import { narrowerProfile, parseProfile } from "./profiles.ts";
import type { Caller, CallerKind, ProfileName, SessionIdentity } from "./types.ts";

export interface CallerInput {
  env: Record<string, string | undefined>;
  tty: boolean;
  session: SessionIdentity | null;
  profileFlag?: string;
}

export function resolveCaller(o: CallerInput): Caller {
  const basis: string[] = [];
  let kind: CallerKind;
  let profile: ProfileName;
  if (o.session) {
    kind = "session";
    profile = "agent";
    basis.push(`Claude session ${o.session.name ?? (o.session.id || `pid ${o.session.pid}`)} is an ancestor → agent`);
  } else if (o.tty) {
    kind = "human";
    profile = "owner";
    basis.push("stdin is a terminal and no Claude session is an ancestor → owner");
  } else {
    kind = "script";
    profile = "agent";
    basis.push("no terminal, no Claude ancestry → agent");
  }
  const narrow = (v: string | undefined, what: string) => {
    if (v === undefined || v === "") return;
    let p: ProfileName;
    try {
      p = parseProfile(v, what);
    } catch (e) {
      throw new AthError("USAGE", (e as Error).message);
    }
    const n = narrowerProfile(profile, p);
    if (n !== profile) basis.push(`${what}=${p} narrows ${profile} → ${p}`);
    else if (p !== profile) basis.push(`${what}=${p} is wider than ${profile}; ignored (narrow-only)`);
    profile = n;
  };
  narrow(o.env.ATH_PROFILE, "ATH_PROFILE");
  narrow(o.profileFlag, "--profile");
  const fromEnv = o.env.ATH_ACTOR?.trim();
  const fromUser = o.tty ? o.env.USER?.trim() : undefined;
  const actor = fromEnv || fromUser || null;
  return { profile, kind, session: o.session, basis, actor, tty: o.tty };
}
