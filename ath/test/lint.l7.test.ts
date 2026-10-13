// lint.l7.test.ts — the L7 comparators: text (designators stripped, footnote marks, bullets), cells per cell, tex by
// symbol multiset on the Equation (1) pair from TOOL03.
import { describe, expect, test } from "bun:test";
import { compareCells, compareTex, compareText } from "../src/engine/lint/l7.ts";
import { stripTex } from "../src/engine/norm/tex.ts";

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
    expect(compareCells(["$FC_{i,j,y}$", "Mass or volume unit per year"], "FCi,j,y Mass or volume unit per year", [])).toBeNull();
    expect(compareCells(["Data unit:", "tCO2/GJ"], "Data unit: tCO2/GJ", [])).toBeNull();
    expect(compareCells(["QA/QC procedures:", "-"], "QA/QC procedures: -", [])).toBeNull();
    expect(compareCells(["Parameter", "Missing cell"], "Parameter SI Unit", [])).toContain("Missing cell");
  });

  test("tex: Equation (1) passes by symbol multiset; a dropped term fails", () => {
    const reading = "PE_{FC,j,y} = \\sum_{i} FC_{i,j,y} \\times COEF_{i,y}";
    const derivation = "𝑃𝐸𝐹𝐶,𝑗,𝑦 = ∑ 𝐹𝐶𝑖,𝑗,𝑦 × 𝐶𝑂𝐸𝐹𝑖,𝑦 𝑖 Equation (1)";
    expect(stripTex(reading)).toBe("PEFC,j,y = ∑i FCi,j,y × COEFi,y");
    expect(compareTex(reading, derivation)).toBeNull();
    expect(compareTex("PE_{FC,j,y} = \\sum_{i} FC_{i,j,y}", derivation)).toContain("counts differ");
    expect(compareTex("COEF_{i,y} = w_{C,i,y} \\times 44/12", "𝐶𝑂𝐸𝐹𝑖,𝑦 = 𝑤𝐶,𝑖,𝑦 × 44/12 Equation (2)")).toBeNull();
  });
});
