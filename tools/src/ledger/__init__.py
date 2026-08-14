"""The ledger package — deterministic tooling for the knowledge layer.

Implements the ledger validation contract (`spec/ledger.md` §13) and the
ledger's generated views, surfaced through the umbrella CLI as `ath ledger …`
(there is deliberately no bare `ledger` command). The interpretive work —
authoring facts and interpretations — is agent territory; everything here is
a pure function of the repos.
"""
