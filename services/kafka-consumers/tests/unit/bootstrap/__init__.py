"""Unit tests for the shared bootstrap/ package.

REQUIRED — do not delete.  Test modules are named after what they cover, so a
`test_config.py` here and a `test_config.py` for any consumer added later share a
basename; without the __init__.py chain, pytest's default import mode fails
collection with "import file mismatch".  With it, the module names resolve as
tests.unit.bootstrap.test_config and tests.unit.<area>.test_config.

One module per module under test: test_config.py, test_consumers.py,
test_launcher.py, test_lifecycle.py.  ARCHITECTURE.md §3.6 lists what each is
responsible for asserting, and what is deliberately left uncovered.
"""
