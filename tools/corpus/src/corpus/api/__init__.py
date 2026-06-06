"""Read-only HTTP API over the corpus library — serves the Angular Corpus Console.

This package wraps the existing `corpus` library surface (`records`, `derived_views`,
`segments`, `schemas`, `resolver`, `store`) as a small FastAPI app. It adds NO new
parsing/derivation/resolution logic — it serializes what the library already produces.

FastAPI / uvicorn are imported only inside `corpus.api.app` / `corpus.api.__main__`,
never by the base library, so `import corpus.draft` (and the base install) stay clean
without the `[api]` extra (gotcha #24). `config.py`, `serialize.py`, and `index.py`
are pure (stdlib + `corpus`) and import without FastAPI.
"""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """Lazy re-export of the FastAPI factory (keeps FastAPI out of base imports)."""
    from corpus.api.app import create_app as _create_app

    return _create_app(*args, **kwargs)
