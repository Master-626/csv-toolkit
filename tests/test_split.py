import csv
import errno
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from csv_toolkit import core
from csv_toolkit.cli import main


def make_source(path, values):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["group", "id"])
        writer.writerows((value, index) for index, value in enumerate(values))
    return path


def assert_groups_preserved(output, values):
    found_rows = []
    files = list(output.glob("*.csv"))
    assert len(files) == len(set(values))
    for path in files:
        headers, rows = core.read_csv(path)
        assert headers == ["group", "id"]
        assert len({row["group"] for row in rows}) == 1
        found_rows.extend((row["group"], int(row["id"])) for row in rows)
    assert sorted(found_rows) == sorted(
        (value, index) for index, value in enumerate(values)
    )
    assert len(list(output.iterdir())) == len(files)


@pytest.mark.parametrize(
    "values,expected",
    [
        (["a-b", "a b", "a-b"], {"a_b.csv", "a_b_2.csv"}),
        (["a/b", "a\\b", "a_b_2"], {"a_b.csv", "a_b_3.csv", "a_b_2.csv"}),
        (["Paris", "paris", "PARIS_2"], {"Paris.csv", "paris_3.csv", "PARIS_2.csv"}),
        (["", "empty", ""], {"empty.csv", "empty_2.csv"}),
        (
            ["CON", "con", "aux", "COM1"],
            {"_CON.csv", "_con_2.csv", "_aux.csv", "_COM1.csv"},
        ),
        (["COM¹", "LPT²", "lpt³"], {"_COM¹.csv", "_LPT².csv", "_lpt³.csv"}),
        (["Straße", "STRASSE"], {"Straße.csv", "STRASSE_2.csv"}),
        (["../a", "/a", "北京"], {"___a.csv", "_a.csv", "北京.csv"}),
    ],
)
def test_split_preserves_colliding_groups(tmp_path, values, expected):
    source = make_source(tmp_path / "source.csv", values)
    original = source.read_bytes()
    for dirname in ("first", "second"):
        output = tmp_path / dirname
        assert core.split_csv(str(source), str(output), "group") == len(set(values))
        assert {path.name for path in output.iterdir()} == expected
        assert_groups_preserved(output, values)
    assert source.read_bytes() == original


@pytest.mark.parametrize("existing_name", ["later.csv", "LATER.csv"])
def test_existing_destination_fails_before_any_output(tmp_path, existing_name):
    source = make_source(tmp_path / "source.csv", ["first", "later"])
    output = tmp_path / "out"
    output.mkdir()
    existing = output / existing_name
    existing.write_bytes(b"important existing data")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        core.split_csv(str(source), str(output), "group")

    assert existing.read_bytes() == b"important existing data"
    assert list(output.iterdir()) == [existing]


def test_existing_directory_is_not_overwritten(tmp_path):
    source = make_source(tmp_path / "source.csv", ["first", "later"])
    output = tmp_path / "out"
    existing = output / "later.csv"
    existing.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    assert list(output.iterdir()) == [existing]
    assert existing.is_dir()


def create_symlink(link, target, is_directory=False):
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Symlinks unavailable: {error}")


@pytest.mark.parametrize("dangling", [False, True])
def test_existing_symlink_is_not_followed(tmp_path, dangling):
    source = make_source(tmp_path / "source.csv", ["first", "later"])
    original = source.read_bytes()
    output = tmp_path / "out"
    output.mkdir()
    link = output / "later.csv"
    target = tmp_path / "missing.csv" if dangling else source
    create_symlink(link, target)

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    assert link.is_symlink()
    assert list(output.iterdir()) == [link]
    assert source.read_bytes() == original
    if dangling:
        assert not target.exists()


@pytest.mark.parametrize("value", ["source", "SOURCE"])
def test_source_in_output_directory_is_preserved(tmp_path, value):
    source = make_source(tmp_path / "source.csv", ["first", value])
    original = source.read_bytes()

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(tmp_path), "group")

    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


def test_source_is_preserved_through_directory_alias(tmp_path):
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    alias = tmp_path / "alias"
    create_symlink(alias, real_directory, is_directory=True)
    source = make_source(real_directory / "source.csv", ["first", "source"])
    original = source.read_bytes()

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(alias), "group")

    assert source.read_bytes() == original
    assert list(real_directory.iterdir()) == [source]


def test_source_hardlink_in_output_is_preserved(tmp_path):
    source = make_source(tmp_path / "source.csv", ["first", "alias"])
    original = source.read_bytes()
    output = tmp_path / "out"
    output.mkdir()
    alias = output / "alias.csv"
    os.link(source, alias)

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    assert source.read_bytes() == original
    assert alias.read_bytes() == original
    assert list(output.iterdir()) == [alias]


def test_missing_column_has_no_output_side_effects(tmp_path):
    source = make_source(tmp_path / "source.csv", ["a", "b"])
    output = tmp_path / "out"

    with pytest.raises(ValueError, match="Unknown split column"):
        core.split_csv(str(source), str(output), "missing")

    assert not output.exists()


def test_header_only_csv_creates_no_outputs(tmp_path):
    source = make_source(tmp_path / "source.csv", [])
    output = tmp_path / "out"
    assert core.split_csv(str(source), str(output), "group") == 0
    assert not output.exists()


def test_repeat_split_does_not_overwrite_outputs(tmp_path):
    source = make_source(tmp_path / "source.csv", ["a-b", "a b"])
    output = tmp_path / "out"
    core.split_csv(str(source), str(output), "group")
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_staging_write_failure_leaves_no_outputs(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    original = source.read_bytes()
    output = tmp_path / "out"
    real_write = core.write_csv
    calls = 0

    def fail_second_write(path, headers, rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"partial output")
            raise OSError(errno.ENOSPC, "Simulated full disk")
        real_write(path, headers, rows)

    monkeypatch.setattr(core, "write_csv", fail_second_write)
    with pytest.raises(OSError, match="Simulated full disk"):
        core.split_csv(str(source), str(output), "group")

    assert list(output.iterdir()) == []
    assert source.read_bytes() == original


def test_destination_added_during_staging_is_rechecked(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    output = tmp_path / "out"
    real_write = core.write_csv

    def add_destination(path, headers, rows):
        real_write(path, headers, rows)
        (output / "SECOND.csv").write_bytes(b"another writer")

    monkeypatch.setattr(core, "write_csv", add_destination)
    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    assert list(output.iterdir()) == [output / "SECOND.csv"]
    assert (output / "SECOND.csv").read_bytes() == b"another writer"


def test_directory_scans_do_not_grow_with_group_count(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source.csv", [str(i) for i in range(100)])
    output = tmp_path / "out"
    output.mkdir()
    real_iterdir = Path.iterdir
    scans = 0

    def count_scans(path):
        nonlocal scans
        if path == output:
            scans += 1
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", count_scans)
    assert core.split_csv(str(source), str(output), "group") == 100
    assert scans == 2


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("Simulated publication failure"),
        OSError(errno.EOPNOTSUPP, "Hard links unavailable"),
        KeyboardInterrupt(),
    ],
)
def test_publish_failure_rolls_back_created_outputs(tmp_path, monkeypatch, failure):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    original = source.read_bytes()
    output = tmp_path / "out"
    output.mkdir()
    unrelated = output / "keep.txt"
    unrelated.write_bytes(b"keep")
    real_link = os.link

    def fail_second_publish(staged, destination):
        if destination.name == "second.csv":
            raise failure
        real_link(staged, destination)

    monkeypatch.setattr(core.os, "link", fail_second_publish)
    with pytest.raises(type(failure)):
        core.split_csv(str(source), str(output), "group")

    assert list(output.iterdir()) == [unrelated]
    assert unrelated.read_bytes() == b"keep"
    assert source.read_bytes() == original


def test_overlong_filename_failure_rolls_back_outputs(tmp_path):
    source = make_source(tmp_path / "source.csv", ["first", "a" * 400])
    original = source.read_bytes()
    output = tmp_path / "out"

    with pytest.raises(OSError):
        core.split_csv(str(source), str(output), "group")

    assert list(output.iterdir()) == []
    assert source.read_bytes() == original


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_destination_created_after_preflight_is_not_overwritten(
    tmp_path, monkeypatch, kind
):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    original = source.read_bytes()
    output = tmp_path / "out"
    real_link = os.link

    def race_publish(staged, destination):
        if destination.name == "second.csv":
            if kind == "file":
                destination.write_bytes(b"another writer")
            else:
                create_symlink(destination, source)
        real_link(staged, destination)

    monkeypatch.setattr(core.os, "link", race_publish)
    with pytest.raises(FileExistsError):
        core.split_csv(str(source), str(output), "group")

    raced = output / "second.csv"
    assert list(output.iterdir()) == [raced]
    assert raced.read_bytes() == (b"another writer" if kind == "file" else original)
    assert raced.is_symlink() == (kind == "symlink")
    assert source.read_bytes() == original


def test_rollback_does_not_remove_an_output_replaced_by_another_writer(
    tmp_path, monkeypatch
):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    output = tmp_path / "out"
    real_link = os.link

    def replace_first_then_fail(staged, destination):
        if destination.name == "second.csv":
            first = output / "first.csv"
            first.unlink()
            first.write_bytes(b"replacement from another writer")
            raise PermissionError("Simulated publication failure")
        real_link(staged, destination)

    monkeypatch.setattr(core.os, "link", replace_first_then_fail)
    with pytest.raises(PermissionError):
        core.split_csv(str(source), str(output), "group")

    first = output / "first.csv"
    assert list(output.iterdir()) == [first]
    assert first.read_bytes() == b"replacement from another writer"


def test_rollback_failure_is_reported(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source.csv", ["first", "second"])
    output = tmp_path / "out"
    real_link = os.link
    real_unlink = Path.unlink

    def fail_second_publish(staged, destination):
        if destination.name == "second.csv":
            raise PermissionError("Simulated publication failure")
        real_link(staged, destination)

    def fail_cleanup(path, *args, **kwargs):
        if path == output / "first.csv":
            raise PermissionError("Simulated cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(core.os, "link", fail_second_publish)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(OSError, match="could not clean up.*first.csv") as error:
        core.split_csv(str(source), str(output), "group")

    assert isinstance(error.value.__context__, PermissionError)
    assert list(output.iterdir()) == [output / "first.csv"]


def test_cli_reports_safe_split_failure_without_success(tmp_path):
    source = make_source(tmp_path / "source.csv", ["first", "source"])
    original = source.read_bytes()
    result = CliRunner().invoke(
        main, ["split", "-i", str(source), "-o", str(tmp_path), "--by", "group"]
    )

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Refusing to overwrite" in result.output
    assert "Split into" not in result.output
    assert "Traceback" not in result.output
    assert source.read_bytes() == original


def test_cli_split_success_reports_actual_file_count(tmp_path):
    values = ["a-b", "a b", "a_b_2"]
    source = make_source(tmp_path / "source.csv", values)
    output = tmp_path / "out"
    result = CliRunner().invoke(
        main, ["split", "-i", str(source), "-o", str(output), "--by", "group"]
    )

    assert result.exit_code == 0, result.output
    assert "Split into 3 files" in result.output
    assert_groups_preserved(output, values)
