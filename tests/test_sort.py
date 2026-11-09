import pytest
from click.testing import CliRunner

from csv_toolkit import core
from csv_toolkit.cli import main


@pytest.mark.parametrize("content", ["", "name,age\n", "name,age\nAlice,25\n"])
@pytest.mark.parametrize("columns", [[], ["missing"], ["age", "missing"]])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_sort_keys_preserve_output(tmp_path, content, columns, existing):
    source = tmp_path / "input.csv"
    source.write_text(content, encoding="utf-8")
    output = tmp_path / "new" / "out.csv"
    if existing:
        output.parent.mkdir()
        output.write_bytes(b"preserve output")
    with pytest.raises(ValueError, match="sort column"):
        core.sort_csv(str(source), str(output), columns)
    if existing:
        assert output.read_bytes() == b"preserve output"
    else:
        assert not output.parent.exists()
    assert source.read_text(encoding="utf-8") == content


@pytest.mark.parametrize(
    "ascending,expected",
    [
        (True, ["Missing", "Blank", "Ten", "Two", "Equal"]),
        (False, ["Two", "Equal", "Ten", "Missing", "Blank"]),
    ],
)
def test_stable_text_sort_handles_missing_cells(tmp_path, ascending, expected):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,age\nTwo,2\nMissing\nTen,10\nBlank,\nEqual,2\n", encoding="utf-8"
    )
    output = tmp_path / "out.csv"
    assert core.sort_csv(str(source), str(output), ["age"], ascending) == 5
    assert [row["name"] for row in core.read_csv(output)[1]] == expected


def test_multi_column_sort(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("group,name\nb,Charlie\na,Bob\na,Alice\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    assert core.sort_csv(str(source), str(output), ["group", "name"]) == 3
    assert [row["name"] for row in core.read_csv(output)[1]] == [
        "Alice",
        "Bob",
        "Charlie",
    ]


def test_header_only_sort_keeps_headers(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,age\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    assert core.sort_csv(str(source), str(output), ["age"]) == 0
    assert core.read_csv(output) == (["name", "age"], [])


def test_cli_unknown_sort_column_fails_without_overwriting(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,age\nAlice,25\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    output.write_bytes(b"preserve output")
    result = CliRunner().invoke(
        main, ["sort", "-i", str(source), "-o", str(output), "--by", "missing"]
    )
    assert result.exit_code == 1
    assert "Unknown sort column" in result.output
    assert "Sorted by" not in result.output
    assert output.read_bytes() == b"preserve output"
