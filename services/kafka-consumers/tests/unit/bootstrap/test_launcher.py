"""bootstrap/launcher.py — argument parsing, name validation, module loading.

The name validation is a security control, not ergonomics: the value reaches
importlib.import_module(), so an unvalidated one is arbitrary module import
inside the container.
"""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

from bootstrap import launcher

# tests/unit/bootstrap/test_launcher.py -> bootstrap -> unit -> tests -> service root.
# Four levels, not three: these tests moved from bootstrap/tests/ and now sit one
# directory deeper.
SERVICE_ROOT = Path(__file__).resolve().parents[3]


def _make_consumer_dir(root: Path, name: str, *, with_main: bool = True) -> None:
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    if with_main:
        (package / "main.py").touch()


class TestAvailableConsumers:
    def test_enumerates_only_directories_holding_a_main_py(self, tmp_path, monkeypatch):
        _make_consumer_dir(tmp_path, "good_consumer")
        _make_consumer_dir(tmp_path, "no_main_consumer", with_main=False)
        (tmp_path / "loose_file.py").touch()
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path)

        assert launcher.available_consumers() == ["good_consumer"]

    def test_skips_illegally_named_directories(self, tmp_path, monkeypatch):
        _make_consumer_dir(tmp_path, "ok_one")
        _make_consumer_dir(tmp_path, "Bad_Caps")
        _make_consumer_dir(tmp_path, "_leading_underscore")
        _make_consumer_dir(tmp_path, "9numeric")
        _make_consumer_dir(tmp_path, "has-dash")
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path)

        assert launcher.available_consumers() == ["ok_one"]

    def test_returns_empty_when_the_directory_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path / "nope")
        assert launcher.available_consumers() == []

    def test_points_at_the_real_consumers_directory(self):
        # The module moved from the service root into bootstrap/, so the path
        # walks up one extra level.  A wrong CONSUMERS_DIR makes every name
        # unknown and every consumer unlaunchable.
        assert launcher.CONSUMERS_DIR == SERVICE_ROOT / "consumers"
        assert "payperuse_consumer" in launcher.available_consumers()


class TestArgumentParsing:
    def test_list_prints_the_available_consumers_and_returns(self, tmp_path, monkeypatch, capsys):
        _make_consumer_dir(tmp_path, "alpha_consumer")
        _make_consumer_dir(tmp_path, "beta_consumer")
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path)

        launcher.main(["--list"])

        assert capsys.readouterr().out.split() == ["alpha_consumer", "beta_consumer"]

    def test_no_arguments_is_a_usage_error(self):
        # No environment fallback and no default: a deployment that forgets
        # --consumer must fail loudly rather than run the wrong consumer.
        with pytest.raises(SystemExit) as excinfo:
            launcher.main([])
        assert excinfo.value.code == 2

    def test_consumer_and_list_are_mutually_exclusive(self):
        with pytest.raises(SystemExit) as excinfo:
            launcher.main(["--consumer", "x", "--list"])
        assert excinfo.value.code == 2


class TestNameValidation:
    @pytest.fixture(autouse=True)
    def _one_valid_consumer(self, tmp_path, monkeypatch):
        _make_consumer_dir(tmp_path, "real_consumer")
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path)

    @pytest.mark.parametrize(
        "name",
        [
            "unknown_consumer",  # well-formed but not present
            "consumers.real_consumer",  # dotted path
            "os.path",  # dotted path at an arbitrary module
            "../../etc",  # traversal
            "../real_consumer",  # traversal
            "Real_Consumer",  # uppercase
            "real-consumer",  # dash
            "",  # empty
            "9real",  # leading digit
        ],
    )
    def test_rejected_names_exit_two(self, name, capsys):
        with pytest.raises(SystemExit) as excinfo:
            launcher.main(["--consumer", name])
        assert excinfo.value.code == 2
        assert "real_consumer" in capsys.readouterr().err  # lists the valid names

    def test_a_rejected_name_is_never_imported(self, monkeypatch):
        def explode(module_name):
            raise AssertionError(f"import must not be attempted: {module_name}")

        monkeypatch.setattr(launcher.importlib, "import_module", explode)
        with pytest.raises(SystemExit):
            launcher.main(["--consumer", "../../etc"])


class TestModuleLoading:
    @pytest.fixture(autouse=True)
    def _valid_name_and_quiet_logging(self, tmp_path, monkeypatch):
        _make_consumer_dir(tmp_path, "real_consumer")
        monkeypatch.setattr(launcher, "CONSUMERS_DIR", tmp_path)
        # configure_logging() clears root handlers; keep it away from the suite.
        import ai4i_core.logging

        monkeypatch.setattr(ai4i_core.logging, "configure_logging", lambda **kwargs: None)

    def test_a_module_without_run_exits_two(self, monkeypatch, capsys):
        monkeypatch.setattr(
            launcher.importlib, "import_module", lambda _: types.ModuleType("stub")
        )
        with pytest.raises(SystemExit) as excinfo:
            launcher.main(["--consumer", "real_consumer"])
        assert excinfo.value.code == 2
        assert "no callable run()" in capsys.readouterr().err

    def test_a_non_callable_run_exits_two(self, monkeypatch):
        module = types.ModuleType("stub")
        module.run = "not callable"
        monkeypatch.setattr(launcher.importlib, "import_module", lambda _: module)
        with pytest.raises(SystemExit) as excinfo:
            launcher.main(["--consumer", "real_consumer"])
        assert excinfo.value.code == 2

    def test_runs_the_modules_run_coroutine(self, monkeypatch):
        called = []
        module = types.ModuleType("stub")
        module.GROUP_ID = "some-group"

        async def run():
            called.append(True)

        module.run = run
        monkeypatch.setattr(launcher.importlib, "import_module", lambda _: module)

        launcher.main(["--consumer", "real_consumer"])

        assert called == [True]

    def test_imports_the_module_under_the_consumers_package(self, monkeypatch):
        seen = []
        module = types.ModuleType("stub")

        async def run():
            pass

        module.run = run

        def spy(module_name):
            seen.append(module_name)
            return module

        monkeypatch.setattr(launcher.importlib, "import_module", spy)
        launcher.main(["--consumer", "real_consumer"])

        assert seen == ["consumers.real_consumer.main"]

    def test_keyboard_interrupt_is_a_clean_exit(self, monkeypatch):
        module = types.ModuleType("stub")

        async def run():
            raise KeyboardInterrupt

        module.run = run
        monkeypatch.setattr(launcher.importlib, "import_module", lambda _: module)

        launcher.main(["--consumer", "real_consumer"])  # must not raise


class TestNoConfigImport:
    def test_importing_the_launcher_pulls_in_no_config_and_needs_no_environment(self):
        """Guards against the coupling one-process-per-consumer exists to remove.

        Settings read the environment, so a launcher that imported shared or
        foreign config would let consumer A's missing variable break consumer
        B's process.  Run in a subprocess with a scrubbed environment: this
        test's own process already has one (see conftest.py).
        """
        code = (
            "import sys\n"
            "import bootstrap.launcher\n"
            "leaked = [m for m in sys.modules if m.endswith('config')"
            " and (m.startswith('bootstrap') or m.startswith('consumers'))]\n"
            "assert not leaked, leaked\n"
            "assert bootstrap.launcher.available_consumers()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=SERVICE_ROOT,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(SERVICE_ROOT)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_the_root_entrypoint_is_a_thin_delegate(self):
        source = (SERVICE_ROOT / "main.py").read_text()
        assert "from bootstrap.launcher import main" in source
        #TODO: readjust the number of lines in main.py
        assert len(source.strip().splitlines()) <= 10
