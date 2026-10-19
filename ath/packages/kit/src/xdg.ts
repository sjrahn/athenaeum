// xdg.ts — where a host keeps what is its own (spec §5.6): the local store under $XDG_DATA_HOME, the custody index,
// each instance's staged passes, locks, journal and history under $XDG_STATE_HOME, the access and host files under
// $XDG_CONFIG_HOME, the daemon's socket under $XDG_RUNTIME_DIR, bases at their pins under $XDG_CACHE_HOME. Nothing here
// is inside a repository.
import { join } from "node:path";

export interface HostPaths {
  /** `$XDG_DATA_HOME/athenaeum`: the local store (`artifacts/`, `testimony/`). */
  data: string;
  /** `$XDG_STATE_HOME/athenaeum`: `index.sqlite`, `locks/`, `instances/<id>/`. */
  state: string;
  /** `$XDG_CONFIG_HOME/athenaeum`: `access.yaml`, `host.yaml`. */
  config: string;
  /** `$XDG_RUNTIME_DIR/athenaeum`: `athd.sock`. */
  runtime: string;
  /** `$XDG_CACHE_HOME/athenaeum`: `bases/<id>/<commit>/`, always safe to delete. */
  cache: string;
}

type Env = Record<string, string | undefined>;

const base = (env: Env, key: string, fallback: string): string => {
  const v = env[key];
  return v?.startsWith("/") ? v : join(env.HOME ?? "/", fallback);
};

export function hostPaths(env: Env): HostPaths {
  const state = join(base(env, "XDG_STATE_HOME", ".local/state"), "athenaeum");
  const runtime = env.XDG_RUNTIME_DIR?.startsWith("/") ? join(env.XDG_RUNTIME_DIR, "athenaeum") : join(state, "run");
  return {
    data: join(base(env, "XDG_DATA_HOME", ".local/share"), "athenaeum"),
    state,
    config: join(base(env, "XDG_CONFIG_HOME", ".config"), "athenaeum"),
    runtime,
    cache: join(base(env, "XDG_CACHE_HOME", ".cache"), "athenaeum"),
  };
}

/** One instance's host state, by the instance's `id` (§5.6): staged passes, locks, the journal, the history. */
export const instanceState = (host: HostPaths, id: string): string => join(host.state, "instances", id);
