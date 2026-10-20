"""ScholarMind core domain package.

This package is deliberately framework-free: it must not import FastAPI, SQLAlchemy
sessions, Celery, or any LLM vendor SDK. Everything here is plain Python and is
independently unit-testable (see ``tests/architecture/test_core_purity.py``).

Modules
-------
ingestion      Fetching official sources safely and snapshotting them immutably.
extraction     Extracting typed facts with character spans into their source snapshot.
normalization  Normalizing cycles, dates, countries, degree levels and funding components.
eligibility    Rule-based eligibility evaluation with tri-state verdicts.
retrieval      Lexical + dense retrieval, RRF fusion, chunking and reranking hooks.
generation     Evidence-constrained answer generation and citation validation.
freshness      Snapshot diffing, change classification and conflict detection.
evaluation     Offline evaluation harness, metrics and baselines.
reporting      Exportable reports, checklists and comparison output.
"""

__version__ = "1.0.0"
