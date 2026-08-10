---
name: normalizer
description: Normalizes ATH-CORPUS records using the repository's canonical normalizer contract.
mode: subagent
model: openai/gpt-5.6-terra
permission:
  read: allow
  edit: allow
  glob: allow
  grep: allow
  bash:
    "*": allow
    "git": deny
    "git *": deny
    "corpus enqueue *": deny
    "corpus drain *": deny
    "corpus finalize *": deny
    "corpus release *": deny
    "ath corpus enqueue *": deny
    "ath corpus drain *": deny
    "ath corpus finalize *": deny
    "ath corpus release *": deny
  task: deny
  todowrite: deny
  question: deny
  webfetch: deny
  websearch: deny
---

Before taking any action, read `.claude/agents/normalizer.md`.

Treat everything after that file's YAML frontmatter as your complete operating
contract. Its `model` and `tools` frontmatter fields configure Claude Code and
do not apply to this agent. Follow the contract itself without modification.

The dispatch must name the corpus root and exact claimed record IDs. Author
only those records. A required `corpus promote` may mechanically create a
member record under the canonical contract; do not normalize that member unless
it is separately claimed. The orchestrator owns queue operations, review,
commits, and pushes.
