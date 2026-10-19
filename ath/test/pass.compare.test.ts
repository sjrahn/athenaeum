// lint.l7.test.ts — the L7 comparators: text (designators stripped, footnote marks, bullets), cells per cell, tex by
// symbol multiset on equations of the generated calculation procedure (testdata/synthetic/procedure.pdf).
import { describe, expect, test } from "bun:test";
import { stripTex } from "@ath/engine/norm/tex.ts";
import { compareCells, compareTex, compareText } from "@ath/engine/pass/compare.ts";

describe("L7", () => {
  test("text: conventions and squash absorb what the reading normalised", () => {
    expect(compareText("Baseline emissions", "Baseline emissions", [])).toBeNull();
    expect(compareText("CO2 emissions from fuel", "CO 2 emissions from fuel", [])).toBeNull();
    expect(
      compareText("the first batch[^1] of project devices", "the first batch1 of project devices", ["footnote marks as [^n]"]),
    ).toBeNull();
    expect(compareText("• Use either mass or volume meters", "Use either mass or volume meters", [])).toBeNull();
    expect(compareText("Baseline emissions", "Baseline omissions", [])).toContain("token 1");
    expect(compareText("Baseline", "Baseline emissions", [])).toContain("length");
  });

  test("cells: each cell is a contiguous run of the row's words, in any row order", () => {
    expect(compareCells(["Parameter", "SI Unit", "Description"], "Parameter SI Unit Description", [])).toBeNull();
    expect(
      compareCells(["$A_{i,k,y}$", "Outer surface area of the insulation"], "𝐴𝑖,𝑘,𝑦 Outer surface area of the insulation", []),
    ).toBeNull();
    expect(
      compareCells(
        ["$\\Delta T_{i,y}$", "=", "Difference between the surface temperature"],
        "Δ𝑇𝑖,𝑦 = Difference between the surface temperature",
        [],
      ),
    ).toBeNull();
    expect(compareCells(["Data unit:", "W/m2 K"], "Data unit: W/m2 K", [])).toBeNull();
    expect(compareCells(["QA/QC procedures:", "-"], "QA/QC procedures: -", [])).toBeNull();
    expect(compareCells(["Parameter", "Missing cell"], "Parameter SI Unit", [])).toContain("Missing cell");
  });

  test("tex: an equation passes by symbol multiset, greek by name and superscripts out of order; a dropped term fails", () => {
    const reading = "U_{i,y} = h_{i,y} + 4 \\times \\epsilon_{i} \\times \\sigma \\times T_{s,i,y}^{3}";
    const derivation = "𝑈𝑖,𝑦 = ℎ𝑖,𝑦 + 4 × 𝜀𝑖 × 𝜎 × 𝑇 3 𝑠,𝑖,𝑦 Equation (2)";
    expect(stripTex(reading)).toBe("Ui,y = hi,y + 4 × εi × σ × Ts,i,y3");
    expect(compareTex(reading, derivation)).toBeNull();
    expect(compareTex("U_{i,y} = h_{i,y} + 4 \\times \\epsilon_{i} \\times \\sigma", derivation)).toContain("counts differ");
    expect(compareTex("\\Delta T_{i,y} = T_{s,i,y} - T_{a,y}", "Δ𝑇𝑖,𝑦 = 𝑇𝑠,𝑖,𝑦 − 𝑇𝑎,𝑦 Equation (3)")).toBeNull();
  });
});
