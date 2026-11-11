from click.testing import CliRunner

from csv_toolkit.cli import main
from csv_toolkit.core import merge_csv, read_csv


def test_merge_preserves_first_seen_column_order(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("name,age,city\nAlice,30,Beijing\n", encoding="utf-8")
    second.write_text("city,country,name\nShanghai,CN,Bob\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    assert merge_csv([str(first), str(second)], str(output)) == 2

    headers, rows = read_csv(output)
    assert headers == ["name", "age", "city", "country"]
    assert rows == [
        {"name": "Alice", "age": "30", "city": "Beijing", "country": ""},
        {"name": "Bob", "age": "", "city": "Shanghai", "country": "CN"},
    ]


def test_merge_dedup_collapses_missing_and_empty_cells(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    third = tmp_path / "third.csv"
    first.write_text("name,city\nAlice,\nBob,Paris\n", encoding="utf-8")
    second.write_text("name,city\nAlice\nCarol,Paris\n", encoding="utf-8")
    third.write_text("name\nAlice\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    count = merge_csv(
        [str(first), str(second), str(third)], str(output), deduplicate=True
    )

    headers, rows = read_csv(output)
    assert headers == ["name", "city"]
    assert count == 3
    assert rows == [
        {"name": "Alice", "city": ""},
        {"name": "Bob", "city": "Paris"},
        {"name": "Carol", "city": "Paris"},
    ]


def test_merge_without_dedup_keeps_repeated_rows(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("name,city\nAlice,\n", encoding="utf-8")
    second.write_text("name,city\nAlice\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    assert merge_csv([str(first), str(second)], str(output)) == 2
    assert [row["name"] for row in read_csv(output)[1]] == ["Alice", "Alice"]


def test_merge_dedup_keeps_distinct_text(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("value\n2\n02\n2\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    assert merge_csv([str(source)], str(output), deduplicate=True) == 2
    assert read_csv(output) == (
        ["value"],
        [{"value": "2"}, {"value": "02"}],
    )


def test_merge_dedup_ignores_source_column_order(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("name,age\nAlice,30\n", encoding="utf-8")
    second.write_text("age,name\n30,Alice\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    assert merge_csv([str(first), str(second)], str(output), True) == 1
    assert read_csv(output) == (["name", "age"], [{"name": "Alice", "age": "30"}])


def test_cli_merge_dedup_reports_unique_rows(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("name,city\nAlice,\n", encoding="utf-8")
    second.write_text("name,city\nAlice\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    result = CliRunner().invoke(
        main,
        [
            "merge",
            "-i",
            str(first),
            "-i",
            str(second),
            "-o",
            str(output),
            "--deduplicate",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "total 1 rows" in result.output
    assert read_csv(output)[1] == [{"name": "Alice", "city": ""}]
