"""Every test asset for kafka-consumers lives under this package.

REQUIRED — do not delete.  The __init__.py chain (tests/, tests/unit/,
tests/unit/<area>/) is what gives each test module a unique dotted name.  Test
modules covering different areas naturally share basenames — a `test_config.py`
per package is the obvious layout — and without the chain, pytest's default
import mode fails collection with "import file mismatch" the moment a second one
appears.

The chain also fixes what lands on sys.path: pytest walks up from a test module
while __init__.py exists and inserts the FIRST directory without one, which is
the service root.  That is what makes `import bootstrap` and
`import consumers.<name>.main` resolve inside the tests.
"""
