// events.ts — what a command reports while it runs: a bus with sinks (the terminal in text mode, a collector in tests).
import type { Io } from "../lib/io.ts";
import type { Clock, EventBus, EventLevel, EventSink, KitEvent } from "./types.ts";

const RANK: Record<EventLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };

export function createEventBus(clock: Clock): EventBus {
  const sinks = new Set<EventSink>();
  return {
    emit(e) {
      const stamped: KitEvent = { ...e, ts: e.ts ?? clock.iso() };
      for (const s of sinks) s(stamped);
    },
    subscribe(s) {
      sinks.add(s);
      return () => void sinks.delete(s);
    },
  };
}

/** `-q` → warn and above; default → info and above; `-v` → everything. */
export function levelFor(verbose: number, quiet: boolean): EventLevel {
  if (quiet) return "warn";
  return verbose > 0 ? "debug" : "info";
}

export function textSink(io: Io, min: EventLevel): EventSink {
  return (e) => {
    if (RANK[e.level] < RANK[min]) return;
    io.err(`${e.level === "info" ? "" : `${e.level}: `}${e.msg}\n`);
  };
}

export function collectSink(): EventSink & { events: KitEvent[] } {
  const events: KitEvent[] = [];
  const sink = ((e: KitEvent) => void events.push(e)) as EventSink & { events: KitEvent[] };
  sink.events = events;
  return sink;
}
