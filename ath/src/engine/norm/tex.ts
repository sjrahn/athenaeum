// tex.ts — TeX layout stripped to the symbols the derivation can show (D-L7): control words mapped to their Unicode,
// grouping and script marks dropped.
const SYMBOLS: Record<string, string> = {
  sum: "∑",
  prod: "∏",
  times: "×",
  cdot: "·",
  div: "÷",
  sqrt: "√",
  int: "∫",
  le: "≤",
  leq: "≤",
  ge: "≥",
  geq: "≥",
  ne: "≠",
  neq: "≠",
  rho: "ρ",
  alpha: "α",
  beta: "β",
  gamma: "γ",
  delta: "δ",
  Delta: "Δ",
  epsilon: "ε",
  varepsilon: "ε",
  zeta: "ζ",
  eta: "η",
  theta: "θ",
  Theta: "Θ",
  iota: "ι",
  kappa: "κ",
  lambda: "λ",
  Lambda: "Λ",
  mu: "μ",
  nu: "ν",
  xi: "ξ",
  pi: "π",
  Pi: "Π",
  sigma: "σ",
  Sigma: "Σ",
  tau: "τ",
  upsilon: "υ",
  phi: "φ",
  Phi: "Φ",
  chi: "χ",
  psi: "ψ",
  Psi: "Ψ",
  omega: "ω",
  Omega: "Ω",
  pm: "±",
  infty: "∞",
};

export function stripTex(s: string): string {
  return s
    .replace(/\\(?:left|right|,|;|!|quad|qquad|text|mathrm|mathit|mathbf|frac|tag\*?|operatorname)\b\{?/g, " ")
    .replace(/\\([A-Za-z]+)/g, (_m, w: string) => SYMBOLS[w] ?? w)
    .replace(/[${}^_]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
