// Slot-based dock — the always-consistent 5-zone workspace (the design's WBDock).
// The subject sits in the CENTER; a TOP strip spans full width; LEFT/RIGHT/BOTTOM tool
// panes flank it. Each peripheral pane resizes (drag the divider), collapses to a thin
// labelled rail, or detaches — pulled in by a gutter so it reads as an island visually
// separated from the central surface (not a floating window). Content is projected via
// named slots (top/left/center/right/bottom + optional <side>-rail / <side>-header), so
// both the corpus workbench and the record workbench reuse this one component.

import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  contentChildren,
  input,
  linkedSignal,
  output,
} from '@angular/core';
import { SLOT, Slot, SlotsAsRecordPipe } from '../../core/slot';

export type PaneMode = 'docked' | 'collapsed' | 'detached' | 'off';
export type PaneSide = 'left' | 'right' | 'bottom';

/** Per-pane layout config. Pass a STABLE reference (a class field) so user resizes/collapses
 *  survive change detection (the dock seeds its state from these via linkedSignal). */
export interface PaneConfig {
  label: string;
  defaultW?: number;
  defaultH?: number;
  defaultCollapsed?: boolean;
  defaultOn?: boolean; // bottom only; false -> starts off
}

/** One peripheral pane: header (collapse/detach) + body, or a collapsed rail, or a
 *  detached island. Renders projected templates passed in by the dock. */
@Component({
  selector: 'wb-pane',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  template: `
    @if (mode() === 'collapsed') {
      <div class="rail wb-rail" [class.h]="side() === 'bottom'" (click)="setMode.emit('docked')"
        [title]="'expand ' + label()">
        <span class="caret">{{ side() === 'left' ? '›' : side() === 'right' ? '‹' : '▴' }}</span>
        <span class="lbl">{{ label() }}</span>
        @if (side() === 'bottom' && rail()) {
          <span class="sep"></span>
          <span class="railc" (click)="$event.stopPropagation()">
            <ng-container *ngTemplateOutlet="rail()!" />
          </span>
        }
      </div>
    } @else {
      <div class="pane" [class.detached]="mode() === 'detached'">
        <div class="head">
          <span class="lbl">{{ label() }}</span>
          <span class="sp"></span>
          @if (header()) { <ng-container *ngTemplateOutlet="header()!" /> }
          <button class="ic" [title]="mode() === 'detached' ? 'attach' : 'separate'"
            (click)="setMode.emit(mode() === 'detached' ? 'docked' : 'detached')">
            {{ mode() === 'detached' ? '⤥' : '⤢' }}
          </button>
          <button class="ic" title="collapse" (click)="setMode.emit('collapsed')">
            {{ side() === 'left' ? '‹' : side() === 'right' ? '›' : '▾' }}
          </button>
        </div>
        <div class="body"><ng-container *ngTemplateOutlet="content()!" /></div>
      </div>
    }
  `,
  styles: [`
    :host { display: block; height: 100%; }
    .pane { box-sizing: border-box; display: flex; flex-direction: column; min-height: 0;
      height: 100%; background: var(--surface); }
    .pane.detached { height: calc(100% - 16px); margin: 8px; border: 1px solid var(--border-strong);
      box-shadow: var(--sh-detach); }
    .head { flex-shrink: 0; height: 28px; display: flex; align-items: center; gap: 7px;
      padding: 0 8px 0 10px; border-bottom: 1px solid var(--border); background: var(--surface-2); }
    .head .lbl { font-family: var(--mono); font-size: 9.5px; text-transform: uppercase;
      letter-spacing: 0.12em; color: var(--muted); font-weight: 600; }
    .sp { flex: 1; }
    .ic { width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center;
      border: none; background: transparent; color: var(--muted); cursor: pointer; font-size: 12px;
      border-radius: 2px; font-family: var(--mono); padding: 0; }
    .ic:hover { background: var(--surface); color: var(--text); }
    .body { flex: 1; min-height: 0; overflow: hidden; }
    .rail { cursor: pointer; background: var(--surface-2); display: flex; align-items: center;
      justify-content: center; gap: 10px; user-select: none; width: 100%; height: 100%;
      flex-direction: column; }
    .rail.h { flex-direction: row; justify-content: flex-start; padding: 0 12px; }
    .rail:hover { background: var(--surface); }
    .rail .caret { color: var(--dim); font-size: 11px; }
    .rail .lbl { font-family: var(--mono); font-size: 9.5px; text-transform: uppercase;
      letter-spacing: 0.14em; color: var(--muted); font-weight: 600; writing-mode: vertical-rl;
      transform: rotate(180deg); }
    .rail.h .lbl { writing-mode: horizontal-tb; transform: none; }
    .rail .sep { width: 1px; height: 14px; background: var(--border); }
    .rail .railc { display: inline-flex; align-items: center; }
  `],
})
export class WbPane {
  side = input.required<PaneSide>();
  label = input.required<string>();
  mode = input.required<PaneMode>();
  content = input.required<TemplateRef<unknown> | undefined>();
  rail = input<TemplateRef<unknown> | undefined>();
  header = input<TemplateRef<unknown> | undefined>();
  setMode = output<PaneMode>();
}

/** The 5-zone dock. Positions a top strip, left/right/bottom WbPanes around a center,
 *  owns each pane's size + mode, and renders the named slot templates. */
@Component({
  selector: 'wb-dock',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, SlotsAsRecordPipe, WbPane],
  template: `
    @let t = slots() | asRecord;
    <div class="dock">
      <!-- TOP -->
      @if (topHeight() > 0 && t['top']) {
        <div class="top" [style.height.px]="topHeight()">
          <ng-container *ngTemplateOutlet="t['top']!" />
        </div>
      }

      <!-- LEFT -->
      <div class="region" [class.island]="leftMode() === 'detached'"
        [style.top.px]="topHeight()" [style.bottom.px]="midBottom()"
        [style.left.px]="0" [style.width.px]="leftDockW()"
        [style.borderRight]="leftDockW() && leftMode() !== 'detached' ? '1px solid var(--border)' : 'none'">
        <wb-pane side="left" [label]="left().label" [mode]="leftMode()"
          [content]="t['left']" [header]="t['left-header']"
          (setMode)="leftMode.set($event)" />
      </div>
      @if (leftMode() !== 'collapsed') {
        <div class="divider v" [style.top.px]="topHeight()" [style.bottom.px]="midBottom()"
          [style.left.px]="leftDockW() - 3" (mousedown)="dragW('left', $event)"><span class="grip v"></span></div>
      }

      <!-- RIGHT -->
      <div class="region" [class.island]="rightMode() === 'detached'"
        [style.top.px]="topHeight()" [style.bottom.px]="midBottom()"
        [style.right.px]="0" [style.width.px]="rightDockW()"
        [style.borderLeft]="rightDockW() && rightMode() !== 'detached' ? '1px solid var(--border)' : 'none'">
        <wb-pane side="right" [label]="right().label" [mode]="rightMode()"
          [content]="t['right']" [header]="t['right-header']"
          (setMode)="rightMode.set($event)" />
      </div>
      @if (rightMode() !== 'collapsed') {
        <div class="divider v" [style.top.px]="topHeight()" [style.bottom.px]="midBottom()"
          [style.right.px]="rightDockW() - 4" (mousedown)="dragW('right', $event)"><span class="grip v"></span></div>
      }

      <!-- CENTER -->
      <div class="center" [style.top.px]="topHeight()" [style.bottom.px]="midBottom()"
        [style.left.px]="leftDockW()" [style.right.px]="rightDockW()">
        <ng-container *ngTemplateOutlet="t['center']!" />
      </div>

      <!-- BOTTOM -->
      @if (bottomMode() !== 'off') {
        <div class="region bottom" [class.island]="bottomMode() === 'detached'"
          [style.height.px]="bottomDockH()"
          [style.borderTop]="bottomMode() !== 'detached' ? '1px solid var(--border)' : 'none'">
          <wb-pane side="bottom" [label]="bottom().label" [mode]="bottomMode()"
            [content]="t['bottom']" [rail]="t['bottom-rail']" [header]="t['bottom-header']"
            (setMode)="bottomMode.set($event)" />
        </div>
        @if (bottomMode() !== 'collapsed') {
          <div class="divider h" [style.bottom.px]="bottomDockH() - 3" (mousedown)="dragH($event)">
            <span class="grip h"></span>
          </div>
        }
      } @else if (t['bottom']) {
        <button class="reopen btn" [style.right.px]="rightDockW() + 12"
          (click)="bottomMode.set('docked')">▴ {{ bottom().label }}</button>
      }
    </div>
  `,
  styles: [`
    .dock { position: absolute; inset: 0; overflow: hidden; background: var(--bg); }
    .top { position: absolute; top: 0; left: 0; right: 0; border-bottom: 1px solid var(--border);
      overflow: hidden; }
    .region { position: absolute; overflow: hidden; }
    .region.island { background: var(--bg); overflow: visible; z-index: 40; }
    .region.bottom { left: 0; right: 0; bottom: 0; }
    .center { position: absolute; overflow: hidden; background: var(--surface); }
    .divider { position: absolute; z-index: 60; display: flex; align-items: center; justify-content: center;
      transition: background 0.1s ease; }
    .divider.v { width: 7px; cursor: ew-resize; }
    .divider.h { left: 0; right: 0; height: 7px; cursor: ns-resize; }
    .divider:hover { background: var(--accent-soft); }
    .grip { background: var(--border-strong); }
    .grip.v { width: 2px; height: 16px; }
    .grip.h { width: 16px; height: 2px; }
    .reopen { position: absolute; bottom: 8px; height: 22px; z-index: 50; font-size: 10px; }
  `],
})
export class WbDock {
  topHeight = input(0);
  left = input.required<PaneConfig>();
  right = input.required<PaneConfig>();
  bottom = input.required<PaneConfig>();

  private slotDirs = contentChildren(SLOT);
  // expose for the template pipe (`slots() | asRecord`)
  readonly slots = computed<readonly Slot[]>(() => this.slotDirs());

  readonly leftW = linkedSignal(() => this.left().defaultW ?? 268);
  readonly rightW = linkedSignal(() => this.right().defaultW ?? 320);
  readonly bottomH = linkedSignal(() => this.bottom().defaultH ?? 170);
  readonly leftMode = linkedSignal<PaneMode>(() => (this.left().defaultCollapsed ? 'collapsed' : 'docked'));
  readonly rightMode = linkedSignal<PaneMode>(() => (this.right().defaultCollapsed ? 'collapsed' : 'docked'));
  readonly bottomMode = linkedSignal<PaneMode>(() =>
    this.bottom().defaultOn === false ? 'off' : this.bottom().defaultCollapsed ? 'collapsed' : 'docked',
  );

  readonly leftDockW = computed(() => (this.leftMode() === 'collapsed' ? 30 : this.leftW()));
  readonly rightDockW = computed(() => (this.rightMode() === 'collapsed' ? 30 : this.rightW()));
  readonly bottomDockH = computed(() =>
    this.bottomMode() === 'off' ? 0 : this.bottomMode() === 'collapsed' ? 30 : this.bottomH(),
  );
  readonly midBottom = computed(() => this.bottomDockH());

  dragW(side: 'left' | 'right', e: MouseEvent): void {
    e.preventDefault();
    const startX = e.clientX;
    const start = side === 'left' ? this.leftW() : this.rightW();
    const move = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      if (side === 'left') this.leftW.set(Math.max(180, Math.min(460, start + dx)));
      else this.rightW.set(Math.max(220, Math.min(520, start - dx)));
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'ew-resize';
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }
  dragH(e: MouseEvent): void {
    e.preventDefault();
    const startY = e.clientY;
    const start = this.bottomH();
    const move = (ev: MouseEvent) => {
      this.bottomH.set(Math.max(110, Math.min(420, start - (ev.clientY - startY))));
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'ns-resize';
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }
}
