from __future__ import annotations

import argparse
import importlib.util
import inspect
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
ALGORITHM_TEST_PATTERN = "test_algorithm_*.py"


@dataclass(frozen=True)
class TestResult:
    name: str
    passed: bool
    error: str | None = None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sys.path.insert(0, str(REPO_ROOT))

    results = _run_algorithm_tests(verbose=args.verbose)
    cli_ok = True
    if not args.skip_cli:
        cli_ok = _run_cli_health_smoke(verbose=args.verbose)

    failures = [result for result in results if not result.passed]
    print(f"algorithm smoke tests: {len(results) - len(failures)}/{len(results)} passed")
    if failures:
        print("")
        print("Failures")
        for failure in failures:
            print(f"- {failure.name}")
            if failure.error:
                print(failure.error.rstrip())
    if not args.skip_cli:
        print(f"algorithm CLI health smoke: {'passed' if cli_ok else 'failed'}")

    return 1 if failures or not cli_ok else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run algorithm_push smoke checks without requiring pytest."
    )
    parser.add_argument("--skip-cli", action="store_true", help="Skip CLI registry health smoke")
    parser.add_argument("--verbose", action="store_true", help="Print every passing test name")
    return parser.parse_args(argv)


def _run_algorithm_tests(*, verbose: bool) -> list[TestResult]:
    results: list[TestResult] = []
    for path in sorted(TESTS_DIR.glob(ALGORITHM_TEST_PATTERN)):
        module = _load_module(path)
        for name, func in _iter_test_functions(module):
            full_name = f"{path.name}::{name}"
            try:
                _run_test_function(func)
            except Exception:
                results.append(TestResult(full_name, passed=False, error=traceback.format_exc()))
            else:
                results.append(TestResult(full_name, passed=True))
                if verbose:
                    print(f"PASSED {full_name}")
    return results


def _load_module(path: Path) -> ModuleType:
    module_name = f"_algorithm_smoke_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _iter_test_functions(module: ModuleType):
    for name, value in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("test_") and value.__module__ == module.__name__:
            yield name, value


def _run_test_function(func) -> None:
    signature = inspect.signature(func)
    kwargs = {}
    temp_dirs: list[tempfile.TemporaryDirectory[str]] = []
    try:
        for parameter in signature.parameters.values():
            if parameter.name != "tmp_path":
                raise RuntimeError(
                    f"Unsupported fixture '{parameter.name}' in {func.__module__}.{func.__name__}"
                )
            temp_dir = tempfile.TemporaryDirectory()
            temp_dirs.append(temp_dir)
            kwargs[parameter.name] = Path(temp_dir.name)
        func(**kwargs)
    finally:
        for temp_dir in reversed(temp_dirs):
            temp_dir.cleanup()


def _run_cli_health_smoke(*, verbose: bool) -> bool:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "algorithm.sqlite3"
        import_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "algorithm_push",
                "--db-path",
                str(db_path),
                "import-defaults",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if import_result.returncode != 0:
            _print_process_failure("import-defaults", import_result)
            return False

        validate_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "algorithm_push",
                "--db-path",
                str(db_path),
                "validate-registry",
                "--strict",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if verbose:
            print(validate_result.stdout.rstrip())
        if validate_result.returncode != 0:
            _print_process_failure("validate-registry --strict", validate_result)
            return False
    return True


def _print_process_failure(label: str, result: subprocess.CompletedProcess[str]) -> None:
    print(f"{label} failed with exit code {result.returncode}")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())


if __name__ == "__main__":
    raise SystemExit(main())
