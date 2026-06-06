import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

// Minimal markdown renderer for segment bodies (the subset corpus bodies use:
// #/## headings, - lists, | tables, and inline **bold** / *italic* / `code`).
// Rendered via control flow + runs — no innerHTML, so no sanitization concerns.

interface Run {
  t: 'b' | 'i' | 'code' | 'plain';
  s: string;
}
type Block =
  | { kind: 'h1' | 'h2' | 'p'; runs: Run[] }
  | { kind: 'ul'; items: Run[][] }
  | { kind: 'table'; rows: Run[][][] };

const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/;

function inlineRuns(text: string): Run[] {
  const runs: Run[] = [];
  let rest = text;
  while (rest.length) {
    const m = rest.match(INLINE);
    if (!m || m.index === undefined) {
      runs.push({ t: 'plain', s: rest });
      break;
    }
    if (m.index > 0) runs.push({ t: 'plain', s: rest.slice(0, m.index) });
    const tok = m[0];
    if (tok.startsWith('**')) runs.push({ t: 'b', s: tok.slice(2, -2) });
    else if (tok.startsWith('`')) runs.push({ t: 'code', s: tok.slice(1, -1) });
    else runs.push({ t: 'i', s: tok.slice(1, -1) });
    rest = rest.slice(m.index + tok.length);
  }
  return runs;
}

export function parseMd(text: string): Block[] {
  const lines = (text || '').split('\n');
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith('# ')) {
      out.push({ kind: 'h1', runs: inlineRuns(l.slice(2)) });
      i++;
    } else if (l.startsWith('## ')) {
      out.push({ kind: 'h2', runs: inlineRuns(l.slice(3)) });
      i++;
    } else if (l.startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith('|')) {
        rows.push(lines[i]);
        i++;
      }
      const cells = rows
        .filter((r) => !/^\|[\s|:-]+\|$/.test(r))
        .map((r) => r.split('|').slice(1, -1).map((c) => inlineRuns(c.trim())));
      out.push({ kind: 'table', rows: cells });
    } else if (l.startsWith('- ')) {
      const items: Run[][] = [];
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(inlineRuns(lines[i].slice(2)));
        i++;
      }
      out.push({ kind: 'ul', items });
    } else if (l.trim() === '') {
      i++;
    } else {
      out.push({ kind: 'p', runs: inlineRuns(l) });
      i++;
    }
  }
  return out;
}

@Component({
  selector: 'cx-inline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@for (r of runs(); track $index) {
    @switch (r.t) {
      @case ('b') { <b>{{ r.s }}</b> }
      @case ('i') { <i>{{ r.s }}</i> }
      @case ('code') { <code>{{ r.s }}</code> }
      @default { {{ r.s }} }
    }
  }`,
  styles: [`code { background: var(--surface-2); padding: 0 3px; font-family: var(--mono); font-size: 0.92em; }`],
})
export class CxInline {
  runs = input.required<Run[]>();
}

@Component({
  selector: 'cx-md',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CxInline],
  template: `
    @for (b of blocks(); track $index) {
      @switch (b.kind) {
        @case ('h1') { <div class="h1"><cx-inline [runs]="b.runs" /></div> }
        @case ('h2') { <div class="h2"><cx-inline [runs]="b.runs" /></div> }
        @case ('p') { <p><cx-inline [runs]="b.runs" /></p> }
        @case ('ul') {
          <ul>@for (it of b.items; track $index) { <li><cx-inline [runs]="it" /></li> }</ul>
        }
        @case ('table') {
          <table><tbody>
            @for (row of b.rows; track $index; let ri = $index) {
              <tr>
                @for (cell of row; track $index) {
                  @if (ri === 0) { <th><cx-inline [runs]="cell" /></th> }
                  @else { <td><cx-inline [runs]="cell" /></td> }
                }
              </tr>
            }
          </tbody></table>
        }
      }
    }
  `,
  styles: [`
    :host { display: block; }
    .h1 { font-size: 18px; font-weight: 700; font-family: var(--sans); margin: 2px 0 8px; line-height: 1.2; }
    .h2 { font-size: 14px; font-weight: 600; font-family: var(--sans); color: var(--accent); margin: 4px 0 5px; }
    p { margin: 0 0 7px; font-family: var(--sans); font-size: 13px; line-height: 1.65; }
    ul { margin: 4px 0; padding-left: 18px; font-family: var(--sans); font-size: 13px; line-height: 1.6; }
    table { border-collapse: collapse; font-family: var(--mono); font-size: 11px; margin: 6px 0; }
    th, td { border: 1px solid var(--border); padding: 3px 8px; text-align: left; }
    th { background: var(--surface-2); color: var(--muted); }
  `],
})
export class CxMd {
  text = input.required<string>();
  blocks = computed(() => parseMd(this.text()));
}
