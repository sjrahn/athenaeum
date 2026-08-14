"""Athenaeum orchestrator tooling — the `ath` umbrella.

`ath` drives the system as a whole from the orchestrator repo: member
sync/status against the `athenaeum.yaml` manifest, plus a delegation shim to
the `corpus` CLI (`ath corpus …` ≡ `corpus …`). The distribution carries no
consumer tooling: the codex kit lives with the codex estate (v15).
"""
