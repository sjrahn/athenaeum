"""Typeset a single exported record to Typst (`.typ`) and PDF (spec §10, corpus export).

Self-contained: a markdown→Typst emitter we own + an internal LaTeX→native Typst-math
translator (no pandoc, no `@preview` packages). PDFs are produced by shelling out to the
system `typst` binary (>= 0.15). If `typst` is not on PATH, the `.typ` source is still
written and PDF is skipped with a warning — honest degradation, never a crash.

Emits Typst 0.15-correct markup: forward-slash image paths only; native math; no
removed-in-0.15 constructs.

Ported from the fork's `scripts/src/corpus/typeset.py` (the math translator and the
markdown emitter's core are carried over close to verbatim — that machinery is the value
being ported). Two adaptations for this corpus's shapes, beyond dropping the multi-record
bundle plumbing (`Manifest`/`ExportConfig`/`run_typeset`/`_bound_document` — out of scope
for the single-record §10 engine, spec'd against a bundle abstraction this corpus does not
have):

- **Markdown pipe tables.** The fork's `text/data-table` segments always emitted a literal
  HTML `<table>`, so the fork emitter only ever needed `_html_table_to_typst`. Here a
  `text/data-table` segment may emit either an HTML table OR a markdown pipe table
  (`corpus._cli.view`'s `_body_html` renders both shapes for the same reason), so
  `markdown_to_typst` gained native pipe-table recognition (`_md_table_to_typst`) alongside
  the HTML path.
- **Admonition blockquotes.** `corpus.export`'s pass-through placeholders and annotated-mode
  lint redlines both need a callout that reads as a plain blockquote in any markdown viewer
  but renders as a colored, bordered box in Typst — the "clearly-styled placeholder" /
  "visually distinct redline" the export engine's owner ruling calls for. A blockquote whose
  first line is `[!KIND] title` renders as a colored `#block`; every other blockquote is an
  ordinary `#quote`.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

TYPST_BIN = "typst"


def typst_available() -> bool:
    return shutil.which(TYPST_BIN) is not None


# =========================================================================== #
# LaTeX math → native Typst math
# =========================================================================== #


class _UnmappedMath(Exception):
    """Raised when a math span uses a LaTeX command we don't translate, so the
    caller can fall back to emitting it verbatim rather than mis-render it."""


# No-argument symbols/operators. LaTeX name (no backslash) → Typst math token.
_SYM: dict[str, str] = {
    # greek lower
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "epsilon.alt", "zeta": "zeta",
    "eta": "eta", "theta": "theta", "vartheta": "theta.alt", "iota": "iota",
    "kappa": "kappa", "lambda": "lambda", "mu": "mu", "nu": "nu", "xi": "xi",
    "pi": "pi", "varpi": "pi.alt", "rho": "rho", "varrho": "rho.alt",
    "sigma": "sigma", "varsigma": "sigma.alt", "tau": "tau",
    "upsilon": "upsilon", "phi": "phi", "varphi": "phi.alt", "chi": "chi",
    "psi": "psi", "omega": "omega",
    # greek upper
    "Gamma": "Gamma", "Delta": "Delta", "Theta": "Theta", "Lambda": "Lambda",
    "Xi": "Xi", "Pi": "Pi", "Sigma": "Sigma", "Upsilon": "Upsilon",
    "Phi": "Phi", "Psi": "Psi", "Omega": "Omega",
    # binary ops / relations
    "times": "times", "cdot": "dot.op", "div": "div", "pm": "plus.minus",
    "mp": "minus.plus", "ast": "*", "star": "star.op", "circ": "compose",
    "bullet": "bullet", "oplus": "plus.circle", "ominus": "minus.circle",
    "otimes": "times.circle", "leq": "<=", "le": "<=", "geq": ">=", "ge": ">=",
    "neq": "eq.not", "ne": "eq.not", "approx": "approx", "equiv": "equiv",
    "sim": "tilde.op", "simeq": "tilde.eq", "cong": "tilde.equiv",
    "propto": "prop", "in": "in", "notin": "in.not", "ni": "in.rev",
    "subset": "subset", "subseteq": "subset.eq", "supset": "supset",
    "supseteq": "supset.eq", "cup": "union", "cap": "sect", "emptyset": "nothing",
    "to": "arrow.r", "rightarrow": "arrow.r", "leftarrow": "arrow.l",
    "leftrightarrow": "arrow.l.r", "Rightarrow": "arrow.r.double",
    "Leftarrow": "arrow.l.double", "Leftrightarrow": "arrow.l.r.double",
    "mapsto": "arrow.r.bar", "rightleftharpoons": "harpoons.rtlb",
    "infty": "infinity", "partial": "diff", "nabla": "nabla",
    "forall": "forall", "exists": "exists", "neg": "not", "land": "and",
    "lor": "or", "angle": "angle", "perp": "perp", "parallel": "parallel",
    "cdots": "dots.c", "ldots": "dots.h", "dots": "dots.h", "vdots": "dots.v",
    "ddots": "dots.down", "prime": "prime", "degree": "degree",
    # delimiters as symbols
    "langle": "angle.l", "rangle": "angle.r", "lbrack": "[", "rbrack": "]",
    "lbrace": "{", "rbrace": "}", "backslash": "backslash", "vert": "|",
    # big operators / named functions
    "sum": "sum", "prod": "product", "int": "integral", "iint": "integral.double",
    "iiint": "integral.triple", "oint": "integral.cont", "bigcup": "union.big",
    "bigcap": "sect.big", "lim": "lim", "max": "max", "min": "min", "sup": "sup",
    "inf": "inf", "log": "log", "ln": "ln", "exp": "exp", "sin": "sin",
    "cos": "cos", "tan": "tan", "cot": "cot", "sec": "sec", "csc": "csc",
    "gcd": "gcd", "deg": "deg", "det": "det", "dim": "dim", "ker": "ker",
    "mod": "mod", "bmod": "mod",
    # spacing-ish
    "quad": "quad", "qquad": "quad quad", "space": "space",
}

# Size/style hints with no Typst equivalent we need — consume, emit nothing.
_DROP: frozenset[str] = frozenset({
    "left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl",
    "Bigr", "biggl", "biggr", "Biggl", "Biggr", "displaystyle", "textstyle",
    "scriptstyle", "limits", "nolimits", "nonumber",
})

# One-arg accents → Typst accent function.
_ACCENT: dict[str, str] = {
    "hat": "hat", "widehat": "hat", "bar": "macron", "overline": "overline",
    "underline": "underline", "tilde": "tilde", "widetilde": "tilde",
    "dot": "dot", "ddot": "dot.double", "vec": "arrow",
    "overrightarrow": "arrow", "check": "caron", "breve": "breve",
    "acute": "acute", "grave": "grave", "mathring": "circle",
}

# One-arg font/style → Typst function ("TEXT"/"OP" handled specially).
_FONT: dict[str, str] = {
    "mathrm": "upright", "mathbf": "bold", "boldsymbol": "bold",
    "mathbb": "bb", "mathcal": "cal", "mathscr": "cal", "mathit": "italic",
    "mathsf": "sans", "mathtt": "mono", "text": "TEXT", "textbf": "bold",
    "textit": "italic", "textrm": "TEXT", "operatorname": "OP",
}

# Two-arg → Typst function.
_TWOARG: dict[str, str] = {"frac": "frac", "dfrac": "frac", "tfrac": "frac", "binom": "binom"}

# Bare Typst keywords `_convert_environments` synthesizes into the string ahead of the
# second `_conv_math` pass (see the `c.isalpha()` branch below) — never quoted as prose.
_TYPST_SYNTHESIZED_WORDS = frozenset({"mat", "cases", "delim"})


def _qstr(s: str) -> str:
    """Escape a string for embedding inside a Typst `"..."` literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _take_braced(s: str, i: int) -> tuple[str, int]:
    """`s[i]` is `{`; return (inner, index-after-`}`). Tolerant of imbalance."""
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return s[i + 1 :], len(s)


def _conv_math(s: str) -> str:
    """Convert a LaTeX math fragment to Typst math. Raises `_UnmappedMath`."""
    out: list[str] = []
    i, n = 0, len(s)

    def take_arg(k: int) -> tuple[str, int]:
        """Read one argument at index k: a `{...}` group or a single token."""
        while k < n and s[k] == " ":
            k += 1
        if k < n and s[k] == "{":
            return _take_braced(s, k)
        if k < n and s[k] == "\\":
            m = re.match(r"\\([A-Za-z]+)", s[k:])
            if m:
                return s[k : k + m.end()], k + m.end()
        if k < n:
            return s[k], k + 1
        return "", k

    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+)", s[i:])
            if not m:
                nxt = s[i + 1] if i + 1 < n else ""
                if nxt == "\\":
                    out.append(" \\ ")  # math line break
                elif nxt in "{}%&#_$ ":
                    out.append(nxt if nxt != " " else " ")
                elif nxt == ",":
                    out.append(" #h(0.17em) ")
                elif nxt in ";:":
                    out.append(" #h(0.25em) ")
                elif nxt == "!":
                    pass  # negative thin space — drop
                else:
                    out.append(nxt)
                i += 2
                continue
            cmd = m.group(1)
            i += m.end()
            if cmd in _DROP:
                continue
            if cmd in _TWOARG:
                a, i = take_arg(i)
                b, i = take_arg(i)
                out.append(f"{_TWOARG[cmd]}({_conv_math(a)}, {_conv_math(b)})")
            elif cmd == "sqrt":
                while i < n and s[i] == " ":
                    i += 1
                if i < n and s[i] == "[":
                    end = s.index("]", i)
                    root, body_i = s[i + 1 : end], end + 1
                    x, i = take_arg(body_i)
                    out.append(f"root({_conv_math(root)}, {_conv_math(x)})")
                else:
                    x, i = take_arg(i)
                    out.append(f"sqrt({_conv_math(x)})")
            elif cmd in _ACCENT:
                x, i = take_arg(i)
                out.append(f"{_ACCENT[cmd]}({_conv_math(x)})")
            elif cmd in _FONT:
                x, i = take_arg(i)
                kind = _FONT[cmd]
                if kind == "TEXT":
                    out.append(f'"{_qstr(x.strip())}"')
                elif kind == "OP":
                    out.append(f'op("{_qstr(x.strip())}")')
                else:
                    out.append(f"{kind}({_conv_math(x)})")
            elif cmd in ("underbrace", "overbrace"):
                x, i = take_arg(i)
                out.append(f"{cmd}({_conv_math(x)})")
            elif cmd == "tag":
                x, i = take_arg(i)
                out.append(f' #h(1fr) "({x.strip()})"')
            elif cmd in _SYM:
                out.append(f" {_SYM[cmd]} ")
            else:
                raise _UnmappedMath(cmd)
        elif c == "{":
            grp, i = _take_braced(s, i)
            out.append(f"({_conv_math(grp)})")
        elif c == "}":
            i += 1
        elif c in "_^":
            arg, i = take_arg(i + 1)
            out.append(f"{c}({_conv_math(arg)})")
        elif c == "&":
            out.append(" & ")
            i += 1
        elif c.isalpha():
            # A run of 2+ letters is a single identifier in Typst math (and
            # errors if undefined), whereas LaTeX renders it as letters. In
            # these documents such runs are words/acronyms (Emissions, GWP,
            # CO), so render them as upright text; single letters stay italic
            # variables.
            j = i
            while j < n and s[j].isalpha():
                j += 1
            run = s[i:j]
            if run in _TYPST_SYNTHESIZED_WORDS:
                # `_convert_environments` lowers a matrix/cases environment to LITERAL
                # Typst call syntax (`mat(delim: "[", …)`) before this second pass runs
                # over the whole string to resolve any LaTeX commands still inside the
                # rows (a `\leq` inside a `cases` body, say). Without this guard the
                # heuristic above — meant for a genuine word/acronym typed inside the
                # SOURCE equation — quotes `mat`/`cases`/`delim` as prose too, corrupting
                # the very call syntax the environment lowering just built
                # (`"mat"("delim": …)`, not a function call at all).
                out.append(run)
            else:
                out.append(run if len(run) == 1 else f'"{run}"')
            i = j
            # A digit glued to a letter forms a Typst identifier (`N20`,
            # `x2` → "unknown variable"); separate them.
            if i < n and s[i].isdigit():
                out.append(" ")
        else:
            out.append(c)
            i += 1

    return re.sub(r"\s+", " ", "".join(out)).strip()


_ENV_RE = re.compile(r"\\begin\{(\w+)\*?\}(.*?)\\end\{\1\*?\}", re.DOTALL)
_MAT_DELIM = {
    "bmatrix": '"["', "pmatrix": '"("', "Bmatrix": '"{"',
    "matrix": "#none", "vmatrix": '"|"',
}


def _convert_environments(latex: str) -> str:
    """Lower LaTeX math environments to Typst constructs before token conversion."""

    def repl(m: re.Match) -> str:
        env, inner = m.group(1), m.group(2).strip()
        if env in ("aligned", "align", "gathered", "gather", "split"):
            return inner  # `&` align + `\\` break work directly in a Typst block equation
        if env == "cases":
            rows = [r.strip() for r in re.split(r"\\\\", inner) if r.strip()]
            return "cases(" + ", ".join(rows) + ")"
        if env in _MAT_DELIM:
            rows = [r.strip() for r in re.split(r"\\\\", inner) if r.strip()]
            body = "; ".join(rows)
            return f"mat(delim: {_MAT_DELIM[env]}, {body})"
        if env == "array":
            body = re.sub(r"^\{[^}]*\}", "", inner).strip()  # drop column spec
            rows = [r.strip() for r in re.split(r"\\\\", body) if r.strip()]
            return "mat(delim: #none, " + "; ".join(rows) + ")"
        raise _UnmappedMath(f"begin{{{env}}}")

    prev = None
    out = latex
    while prev != out:
        prev = out
        out = _ENV_RE.sub(repl, out)
    return out


def latex_to_typst_math(latex: str) -> str | None:
    """Translate a LaTeX math fragment to Typst math, or return None if it uses
    something we don't map (caller emits verbatim)."""
    try:
        conv = _conv_math(_convert_environments(latex))
    except (_UnmappedMath, ValueError, IndexError) as e:
        log.warning("unmapped math (kept verbatim): %s … in %r", e, latex[:60])
        return None
    # Glue subscripts/superscripts to their base (drop the space the symbol
    # spacing introduced): `sum _(i=1)` → `sum_(i=1)`.
    conv = re.sub(r"\s+([_^]\()", r"\1", conv)
    # A script with no base (`$_{x}$`) is valid in LaTeX but not Typst — give
    # it an empty string base.
    conv = re.sub(r"(^|[\s(=&,])([_^]\()", r'\1""\2', conv)
    return conv


# =========================================================================== #
# Markdown → Typst markup
# =========================================================================== #

# Escape Typst markup specials. `/` is included so `//` and `/*` in prose or
# table cells aren't parsed as comments.
_TYPST_ESCAPE = {ch: "\\" + ch for ch in "\\#$*_`[]<>@/"}


def _esc(text: str) -> str:
    return "".join(_TYPST_ESCAPE.get(ch, ch) for ch in text)


def _math_to_typst(latex: str, *, display: bool) -> str:
    conv = latex_to_typst_math(latex)
    if conv is None:
        # Verbatim fallback: show the original LaTeX as raw inline code.
        return f"`${latex}$`"
    return f"$ {conv} $" if display else f"${conv}$"


_INLINE_PATTERNS = re.compile(
    # Math `$…$` must not be glued to a word char or `/` (avoids matching
    # literal `$` in URLs / prose, e.g. `…/$department/…/$file/…`).
    r"(?P<dmath>(?<![\w/])\$\$.+?\$\$(?!\w))"
    r"|(?P<imath>(?<![\w/])\$[^$\n]+?\$(?!\w))"
    r"|(?P<code>`[^`\n]+?`)"
    r"|(?P<img>!\[(?P<alt>[^\]]*)\]\((?P<isrc>[^)]+)\))"
    r"|(?P<link>\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)]+)\))"
    r"|(?P<bold>\*\*(?P<btext>.+?)\*\*)"
    r"|(?P<sub><sub>(?P<subt>.*?)</sub>)"
    r"|(?P<sup><sup>(?P<supt>.*?)</sup>)"
    r"|(?P<br><br\s*/?>)"
    r"|(?P<stag></?(?:strong|b)>)"
    r"|(?P<etag></?(?:em|i)>)",
    re.DOTALL,
)


def _inline(text: str) -> str:
    """Convert markdown/HTML inline constructs to Typst, escaping plain runs."""
    out: list[str] = []
    pos = 0
    for m in _INLINE_PATTERNS.finditer(text):
        if m.start() > pos:
            out.append(_esc(text[pos : m.start()]))
        if m.group("dmath") is not None:
            out.append(_math_to_typst(m.group("dmath")[2:-2].strip(), display=False))
        elif m.group("imath") is not None:
            out.append(_math_to_typst(m.group("imath")[1:-1].strip(), display=False))
        elif m.group("code") is not None:
            out.append(m.group("code"))  # backticks are raw in Typst too
        elif m.group("img") is not None:
            out.append(f'#box(image("{m.group("isrc")}"))')
        elif m.group("link") is not None:
            out.append(f'#link("{m.group("lurl")}")[{_esc(m.group("ltext"))}]')
        elif m.group("bold") is not None:
            out.append(f"*{_inline(m.group('btext'))}*")
        elif m.group("sub") is not None:
            out.append(f"#sub[{_inline(m.group('subt'))}]")
        elif m.group("sup") is not None:
            out.append(f"#super[{_inline(m.group('supt'))}]")
        elif m.group("br") is not None:
            out.append(" \\\n")
        # stag / etag (stray <strong>/<em> halves): dropped.
        pos = m.end()
    if pos < len(text):
        out.append(_esc(text[pos:]))
    return "".join(out)


def _html_table_to_typst(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return ""
    rows = table.find_all("tr")
    if not rows:
        return ""
    ncols = max((len(r.find_all(["td", "th"])) for r in rows), default=1)
    cells: list[str] = []
    for r in rows:
        tds = r.find_all(["td", "th"])
        for td in tds:
            inner = _inline(td.decode_contents().strip())
            cells.append(f"[{inner}]")
        for _ in range(ncols - len(tds)):  # pad ragged rows
            cells.append("[]")
    body = ", ".join(cells)
    return f"#table(\n  columns: {ncols},\n  {body},\n)"


# A markdown PIPE table — our own `text/data-table` segments emit either this or a literal
# HTML `<table>` (`corpus._cli.view._body_html` renders both shapes for the same reason;
# `_html_table_to_typst` above is the fork's original HTML path). `_ROW_RE` matches any line
# that starts and ends with `|`; `_RULE_RE` picks out the `|---|:--:|` separator row so it is
# dropped rather than rendered as an empty first data row.
_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_RULE_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _cells(line: str) -> list[str]:
    """Split a pipe-table row. A `||` pair is an EMPTY cell (the data-table convention), so
    splitting on the delimiter — not on non-empty runs — is what keeps columns aligned."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _md_table_to_typst(rows: list[str]) -> str:
    """A contiguous run of pipe-table lines (header + optional rule + body) → Typst `#table`."""
    body_rows = [r for r in rows if not _RULE_RE.match(r)]
    if not body_rows:
        return ""
    head_cells = _cells(body_rows[0])
    ncols = len(head_cells)
    cells = [f"[*{_inline(c)}*]" for c in head_cells]
    for row in body_rows[1:]:
        row_cells = _cells(row)
        row_cells += [""] * (ncols - len(row_cells))  # pad ragged rows
        cells += [f"[{_inline(c)}]" for c in row_cells[:ncols]]
    body = ", ".join(cells)
    return f"#table(\n  columns: {ncols},\n  {body},\n)"


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ULIST_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST_RE = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")

# An ADMONITION blockquote's opener line: `[!KIND] optional title text`. `KIND` picks the
# callout's border/fill color (`_ADMONITION_COLOR`); an unrecognized kind still renders,
# just in the default gray — a new kind never needs a code change to be visible. Plain
# markdown viewers (and GitHub, for a known subset) render the surrounding `>` as an
# ordinary blockquote; the marker is inert prose to them.
_ADMONITION_RE = re.compile(r"^\[!([A-Za-z][A-Za-z0-9_-]*)\]\s*(.*)$")
_ADMONITION_COLOR: dict[str, str] = {
    "PASSTHROUGH": "gray",
    "PLACEMENT": "gray",
    "UNRESOLVED": "purple",
    "LINT-ERROR": "red",
    "LINT-WARNING": "orange",
    "LINT-INFO": "blue",
}


def _blockquote_to_typst(lines: list[str]) -> str:
    """One blockquote's already-unwrapped lines → Typst. An admonition (first line matches
    `_ADMONITION_RE`) becomes a colored, left-bordered callout box — the "clearly-styled
    placeholder" / "visually distinct redline" `corpus.export`'s pass-through notes and
    annotated-mode lint findings need; anything else is an ordinary `#quote`."""
    m = _ADMONITION_RE.match(lines[0]) if lines else None
    if m is None:
        return f"#quote(block: true)[{_inline(' '.join(lines))}]"
    kind, title_rest = m.group(1).upper(), m.group(2)
    color = _ADMONITION_COLOR.get(kind, "gray")
    title = title_rest or kind.replace("-", " ").title()
    rest = " ".join(lines[1:]).strip()
    body = f"*{_inline(title)}*" + (f" --- {_inline(rest)}" if rest else "")
    return (
        f"#block(width: 100%, stroke: (left: 2.5pt + {color}), "
        f"inset: (left: 10pt, top: 6pt, bottom: 6pt, right: 6pt), "
        f"fill: {color}.lighten(88%))[{body}]"
    )


def markdown_to_typst(body: str) -> str:
    """Convert an exported portable-markdown body to Typst markup."""
    lines = body.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)

    def flush_para(buf: list[str]) -> None:
        if buf:
            out.append(_inline(" ".join(s.strip() for s in buf).strip()))
            out.append("")

    para: list[str] = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            flush_para(para)
            para = []
            fence = [line]
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                fence.append(lines[i])
                i += 1
            if i < n:
                fence.append(lines[i])
                i += 1
            out.append("\n".join(fence))
            out.append("")
            continue

        # HTML table block
        if stripped.startswith("<table"):
            flush_para(para)
            para = []
            block = [line]
            i += 1
            while i < n and "</table>" not in lines[i]:
                block.append(lines[i])
                i += 1
            if i < n:
                block.append(lines[i])
                i += 1
            out.append(_html_table_to_typst("\n".join(block)))
            out.append("")
            continue

        # markdown pipe table (consume a contiguous run)
        if _ROW_RE.match(line):
            flush_para(para)
            para = []
            block = []
            while i < n and _ROW_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            out.append(_md_table_to_typst(block))
            out.append("")
            continue

        # display math on its own line(s)
        if stripped.startswith("$$"):
            flush_para(para)
            para = []
            chunk = stripped
            # single-line $$...$$
            if chunk.count("$$") >= 2:
                inner = chunk[chunk.index("$$") + 2 : chunk.rindex("$$")].strip()
                i += 1
            else:
                buf = [chunk[2:]]
                i += 1
                while i < n and "$$" not in lines[i]:
                    buf.append(lines[i])
                    i += 1
                if i < n:
                    buf.append(lines[i].replace("$$", ""))
                    i += 1
                inner = "\n".join(buf).strip()
            conv = latex_to_typst_math(inner)
            out.append(f"$ {conv} $" if conv is not None else f"```\n${inner}$\n```")
            out.append("")
            continue

        # heading
        hm = _HEADING_RE.match(line)
        if hm:
            flush_para(para)
            para = []
            level = len(hm.group(1))
            out.append(f"{'=' * level} {_inline(hm.group(2).strip())}")
            out.append("")
            i += 1
            continue

        # image on its own line → figure with caption
        im = re.match(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)\s*$", stripped)
        if im:
            flush_para(para)
            para = []
            alt = im.group("alt").strip()
            cap = f", caption: [{_inline(alt)}]" if alt else ""
            out.append(f'#figure(image("{im.group("src")}", width: 90%){cap})')
            out.append("")
            i += 1
            continue

        # list (consume a contiguous run)
        if _ULIST_RE.match(line) or _OLIST_RE.match(line):
            flush_para(para)
            para = []
            while i < n and (_ULIST_RE.match(lines[i]) or _OLIST_RE.match(lines[i])):
                um = _ULIST_RE.match(lines[i])
                om = _OLIST_RE.match(lines[i])
                if um:
                    indent, content = um.group(1), um.group(2)
                    marker = "-"
                else:
                    indent, content = om.group(1), om.group(2)
                    marker = "+"
                out.append(f"{indent}{marker} {_inline(content.strip())}")
                i += 1
            out.append("")
            continue

        # horizontal rule
        if stripped in ("---", "***", "___"):
            flush_para(para)
            para = []
            out.append("#line(length: 100%)")
            out.append("")
            i += 1
            continue

        # blank line ends a paragraph
        if stripped == "":
            flush_para(para)
            para = []
            i += 1
            continue

        # blockquote — plain, or an admonition callout (see `_blockquote_to_typst`)
        if stripped.startswith(">"):
            flush_para(para)
            para = []
            quote = [stripped.lstrip("> ").rstrip()]
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip("> "))
                i += 1
            out.append(_blockquote_to_typst(quote))
            out.append("")
            continue

        para.append(line)
        i += 1

    flush_para(para)
    return "\n".join(out).strip() + "\n"


# =========================================================================== #
# Document assembly + compile
# =========================================================================== #

_PREAMBLE = """\
#set page(margin: 2cm, numbering: "1")
#set text(size: 10pt)
#set par(justify: true)
#show heading: set block(above: 1.2em, below: 0.6em)
#set table(stroke: 0.5pt)
"""


def _split_frontmatter(text: str) -> tuple[dict, str]:
    import yaml

    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm = yaml.safe_load(text[4 : end + 1]) or {}
            return (fm if isinstance(fm, dict) else {}), text[end + 5 :].lstrip("\n")
    return {}, text


def _title_block(fm: dict) -> str:
    title = str(fm.get("title") or "")
    parts = []
    if title:
        parts.append(f"#align(center)[#text(size: 16pt, weight: \"bold\")[{_esc(title)}]]")
    source = fm.get("source")
    if source:
        parts.append(f'#align(center)[#text(size: 8pt)[#link("{source}")]]')
    parts.append("")
    return "\n".join(parts)


def record_typst(md_text: str, *, standalone: bool) -> str:
    """Render one exported markdown file to a Typst document body (or full doc)."""
    fm, body = _split_frontmatter(md_text)
    doc = _title_block(fm) + "\n" + markdown_to_typst(body)
    return (_PREAMBLE + "\n" + doc) if standalone else doc


def compile_pdf(typ_path: Path, pdf_path: Path, *, root: Path) -> bool:
    """Compile a .typ to PDF with the system typst. Returns success."""
    if not typst_available():
        return False
    try:
        subprocess.run(
            [TYPST_BIN, "compile", "--root", str(root), str(typ_path), str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.warning("typst compile failed for %s:\n%s", typ_path.name, e.stderr.strip())
        return False
