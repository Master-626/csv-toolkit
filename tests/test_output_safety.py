import csv
import errno
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from csv_toolkit import core
from csv_toolkit.cli import main

OPERATIONS = ["filter", "sort", "merge", "convert", "write"]


def run_operation(operation, source, output):
    if operation == "filter":
        return core.filter_csv(str(source), str(output), "age >= 18")
    if operation == "sort":
        return core.sort_csv(str(source), str(output), ["age"])
    if operation == "merge":
        return core.merge_csv([str(source), str(source)], str(output), True)
    if operation == "convert":
        return core.convert_csv(str(source), str(output), "json")
    headers, rows = core.read_csv(source)
    return core.write_csv(output, headers, rows)


def make_source(path):
    path.write_bytes(b"name,age\nAlice,17\nBob,25\n")
    return path


def symlink(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Symlinks unavailable: {error}")


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "kind", ["file", "directory", "symlink", "dangling", "hardlink", "source"]
)
def test_existing_destinations_are_untouched(tmp_path, operation, kind):
    source = make_source(tmp_path / "input.csv")
    original = source.read_bytes()
    output = tmp_path / "result.csv"
    missing = tmp_path / "missing.csv"
    if kind == "file":
        output.write_bytes(b"preserve output")
    elif kind == "directory":
        output.mkdir()
        (output / "keep").write_bytes(b"keep")
    elif kind == "symlink":
        symlink(output, source)
    elif kind == "dangling":
        symlink(output, missing)
    elif kind == "hardlink":
        os.link(source, output)
    else:
        output = source
    entries = set(tmp_path.iterdir())

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        run_operation(operation, source, output)

    assert source.read_bytes() == original
    assert set(tmp_path.iterdir()) == entries
    if kind == "file":
        assert output.read_bytes() == b"preserve output"
    elif kind == "directory":
        assert (output / "keep").read_bytes() == b"keep"
    elif kind in ["symlink", "dangling"]:
        assert output.is_symlink()
        assert not missing.exists()
    else:
        assert output.read_bytes() == original


@pytest.mark.parametrize("operation", OPERATIONS)
def test_directory_alias_cannot_overwrite_input(tmp_path, operation):
    real = tmp_path / "real"
    real.mkdir()
    source = make_source(real / "input.csv")
    original = source.read_bytes()
    alias = tmp_path / "alias"
    symlink(alias, real, directory=True)
    with pytest.raises(FileExistsError):
        run_operation(operation, source, alias / source.name)
    assert source.read_bytes() == original
    assert list(real.iterdir()) == [source]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "kind", ["file", "directory", "symlink", "dangling", "hardlink"]
)
def test_destination_race_does_not_clobber(tmp_path, monkeypatch, operation, kind):
    source = make_source(tmp_path / "input.csv")
    original = source.read_bytes()
    output = tmp_path / "result.csv"
    real_link = core.os.link
    missing = tmp_path / "missing.csv"

    def race(staged, destination):
        assert destination == output
        if kind == "file":
            output.write_bytes(b"concurrent writer")
        elif kind == "directory":
            output.mkdir()
        elif kind == "symlink":
            symlink(output, source)
        elif kind == "dangling":
            symlink(output, missing)
        else:
            real_link(source, output)
        return real_link(staged, destination)

    monkeypatch.setattr(core.os, "link", race)
    with pytest.raises(FileExistsError):
        run_operation(operation, source, output)
    assert source.read_bytes() == original
    assert set(tmp_path.iterdir()) == {source, output}
    if kind == "file":
        assert output.read_bytes() == b"concurrent writer"
    elif kind == "directory":
        assert output.is_dir()
    elif kind == "dangling":
        assert output.is_symlink() and not missing.exists()
    else:
        assert output.read_bytes() == original


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("publication failed"),
        OSError(errno.EOPNOTSUPP, "hard links unavailable"),
        KeyboardInterrupt(),
    ],
)
def test_publication_failure_leaves_no_output(
    tmp_path, monkeypatch, operation, failure
):
    source = make_source(tmp_path / "input.csv")
    original = source.read_bytes()
    output = tmp_path / "result.csv"

    def fail(staged, destination):
        # Publication must only be attempted once data is complete and closed.
        assert Path(staged).read_bytes()
        raise failure

    monkeypatch.setattr(core.os, "link", fail)
    with pytest.raises(type(failure)):
        run_operation(operation, source, output)
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == original


@pytest.mark.parametrize("operation", OPERATIONS)
def test_serialization_failure_leaves_no_partial_output(
    tmp_path, monkeypatch, operation
):
    source = make_source(tmp_path / "input.csv")
    original = source.read_bytes()
    output = tmp_path / "result.csv"

    if operation == "convert":

        def fail_dump(rows, stream, **kwargs):
            stream.write('[{"partial": ')
            raise OSError(errno.ENOSPC, "disk full")

        monkeypatch.setattr(core.json, "dump", fail_dump)
    else:

        def fail_rows(writer, rows):
            writer.writerow(rows[0])
            raise OSError(errno.ENOSPC, "disk full")

        monkeypatch.setattr(core.csv.DictWriter, "writerows", fail_rows)
    with pytest.raises(OSError, match="disk full"):
        run_operation(operation, source, output)
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == original


@pytest.mark.parametrize("operation", OPERATIONS)
def test_successful_outputs_are_complete(tmp_path, operation):
    source = make_source(tmp_path / "input.csv")
    original = source.read_bytes()
    output = tmp_path / "new" / "result.csv"
    run_operation(operation, source, output)
    expected = [{"name": "Alice", "age": "17"}, {"name": "Bob", "age": "25"}]
    if operation == "convert":
        assert json.loads(output.read_text(encoding="utf-8")) == expected
    else:
        headers, rows = core.read_csv(output)
        assert set(headers) == {"name", "age"}
        assert rows == (expected[1:] if operation == "filter" else expected)
    assert list(output.parent.iterdir()) == [output]
    assert source.read_bytes() == original


@pytest.mark.parametrize("operation", ["merge", "filter", "sort", "convert", "split"])
@pytest.mark.parametrize("failure", ["existing", "missing_input", "malformed"])
def test_cli_reports_errors_without_success(tmp_path, operation, failure):
    source = make_source(tmp_path / "input.csv")
    if failure == "malformed":
        source.write_bytes(b'name,age\n"unterminated,25\n')
    original = source.read_bytes()
    if failure == "missing_input":
        source = tmp_path / "missing.csv"
    output = tmp_path / "result.csv"
    if operation == "split":
        output.mkdir()
        if failure == "existing":
            (output / "17.csv").write_bytes(b"preserve output")
    elif failure == "existing":
        output.write_bytes(b"preserve output")
    args = [operation, "-i", str(source), "-o", str(output)]
    args += {
        "merge": [],
        "filter": ["--condition", "age >= 18"],
        "sort": ["--by", "age"],
        "convert": ["--format", "json"],
        "split": ["--by", "age"],
    }[operation]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "✅" not in result.output
    assert "Traceback" not in result.output
    if failure != "missing_input":
        assert source.read_bytes() == original
    if operation == "split":
        if failure == "existing":
            assert list(output.iterdir()) == [output / "17.csv"]
            assert (output / "17.csv").read_bytes() == b"preserve output"
        else:
            assert list(output.iterdir()) == []
    elif failure == "existing":
        assert output.read_bytes() == b"preserve output"
    else:
        assert not output.exists()


def test_convert_unsupported_format_has_no_side_effects(tmp_path):
    source = make_source(tmp_path / "input.csv")
    output = tmp_path / "new" / "result"
    with pytest.raises(ValueError, match="Unsupported format"):
        core.convert_csv(str(source), str(output), "excel")
    assert not output.parent.exists()


def test_merge_empty_inputs_has_no_side_effects(tmp_path):
    output = tmp_path / "new" / "result"
    with pytest.raises(ValueError, match="At least one input"):
        core.merge_csv([], str(output))
    assert not output.parent.exists()


def test_merge_cannot_overwrite_later_input(tmp_path):
    first = make_source(tmp_path / "first.csv")
    second = make_source(tmp_path / "second.csv")
    originals = [first.read_bytes(), second.read_bytes()]
    with pytest.raises(FileExistsError):
        core.merge_csv([str(first), str(second)], str(second))
    assert [first.read_bytes(), second.read_bytes()] == originals


@pytest.mark.parametrize(
    "content,error",
    [
        (b"name,name\nAlice,Bob\n", ValueError),
        (b"name,age\nAlice,25,extra\n", ValueError),
        (b'name,age\n"unterminated,25\n', csv.Error),
    ],
)
@pytest.mark.parametrize("operation", OPERATIONS + ["split"])
def test_malformed_input_does_not_create_outputs(tmp_path, content, error, operation):
    source = tmp_path / "input.csv"
    source.write_bytes(content)
    output = tmp_path / "new" / "result.csv"
    with pytest.raises(error):
        if operation == "split":
            core.split_csv(str(source), str(output), "name")
        else:
            run_operation(operation, source, output)
    assert not output.parent.exists()
    assert source.read_bytes() == content


@pytest.mark.parametrize("newline", ["\r\n", "\r", "\n"])
def test_quoted_cell_newlines_are_preserved(tmp_path, newline):
    source = tmp_path / "input.csv"
    source.write_bytes(('name,note\r\nAlice,"a' + newline + 'b"\r\n').encode())
    headers, rows = core.read_csv(source)
    assert rows == [{"name": "Alice", "note": "a" + newline + "b"}]
    csv_output = tmp_path / "out.csv"
    core.write_csv(csv_output, headers, rows)
    assert core.read_csv(csv_output) == (headers, rows)
    json_output = tmp_path / "out.json"
    core.convert_csv(str(source), str(json_output), "json")
    assert json.loads(json_output.read_text(encoding="utf-8")) == rows
