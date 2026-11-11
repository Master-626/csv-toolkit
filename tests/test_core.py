from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from click.testing import CliRunner

from csv_toolkit import __version__
from csv_toolkit.cli import main
from csv_toolkit.core import filter_csv, merge_csv, sort_csv


@pytest.fixture
def sample_csv(tmp_path: Path):
    """Create a sample CSV file for testing."""
    csv_file = tmp_path / "users.csv"
    csv_file.write_text("name,age,city\nAlice,25,Beijing\nBob,30,Shanghai\nCharlie,20,Beijing\n")
    return csv_file


def test_filter_csv(sample_csv, tmp_path):
    """Test CSV filtering."""
    output = tmp_path / "filtered.csv"
    count = filter_csv(str(sample_csv), str(output), "age >= 25")
    assert count == 2


def test_sort_csv(sample_csv, tmp_path):
    """Test CSV sorting."""
    output = tmp_path / "sorted.csv"
    sort_csv(str(sample_csv), str(output), by=["age"], ascending=True)
    assert output.exists()


def test_merge_csv(sample_csv, tmp_path):
    """Test CSV merging."""
    output = tmp_path / "merged.csv"
    count = merge_csv([str(sample_csv), str(sample_csv)], str(output))
    assert count == 6  # 3 + 3 rows


def test_package_version_matches_metadata():
    try:
        installed = version("csv-toolkit")
    except PackageNotFoundError:
        pytest.skip("csv-toolkit is not installed")
    assert __version__ == installed


def test_cli_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
