from decimal import InvalidOperation, localcontext

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


def test_numeric_sort_orders_exact_decimals(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,score\n"
        "ten,10\n"
        "missing\n"
        "two,2\n"
        "text,nope\n"
        "neg,-3\n"
        "big,9007199254740993\n"
        "also,2.0\n"
        "blank,\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.csv"

    assert core.sort_csv(str(source), str(output), ["score"], numeric=True) == 8
    assert [row["name"] for row in core.read_csv(output)[1]] == [
        "missing",
        "blank",
        "text",
        "neg",
        "two",
        "also",
        "ten",
        "big",
    ]


def test_numeric_sort_descending_keeps_ties_stable(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,score\n"
        "ten,10\n"
        "missing\n"
        "two,2\n"
        "text,nope\n"
        "neg,-3\n"
        "big,9007199254740993\n"
        "also,2.0\n"
        "blank,\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.csv"

    core.sort_csv(
        str(source), str(output), ["score"], ascending=False, numeric=True
    )
    assert [row["name"] for row in core.read_csv(output)[1]] == [
        "big",
        "ten",
        "two",
        "also",
        "neg",
        "text",
        "missing",
        "blank",
    ]


def test_default_sort_stays_textual(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,score\nten,10\ntwo,2\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    core.sort_csv(str(source), str(output), ["score"])
    assert [row["name"] for row in core.read_csv(output)[1]] == ["ten", "two"]


def test_numeric_sort_on_text_column_matches_text_order(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name\nBob\nAlice\nCarol\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    core.sort_csv(str(source), str(output), ["name"], numeric=True)
    assert [row["name"] for row in core.read_csv(output)[1]] == [
        "Alice",
        "Bob",
        "Carol",
    ]


def test_numeric_sort_applies_to_every_column(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "group,score,name\nb,10,later\na,10,ten\na,2,two\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.csv"

    core.sort_csv(str(source), str(output), ["group", "score"], numeric=True)
    assert [row["name"] for row in core.read_csv(output)[1]] == [
        "two",
        "ten",
        "later",
    ]


def test_numeric_sort_groups_nonfinite_with_text(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,score\na,Infinity\nb,1\nc,NaN\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    core.sort_csv(str(source), str(output), ["score"], numeric=True)
    assert [row["name"] for row in core.read_csv(output)[1]] == ["a", "c", "b"]


def test_numeric_sort_ignores_caller_decimal_context(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,score\ntext,nope\na,10\nb,2\n", encoding="utf-8")
    output = tmp_path / "out.csv"

    with localcontext() as context:
        context.prec = 1
        context.traps[InvalidOperation] = False
        context.clear_flags()
        core.sort_csv(str(source), str(output), ["score"], numeric=True)
        assert [row["name"] for row in core.read_csv(output)[1]] == [
            "text",
            "b",
            "a",
        ]
        assert not context.flags[InvalidOperation]


def test_numeric_sort_unknown_column_preserves_output(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,age\nAlice,25\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    output.write_bytes(b"keep")

    with pytest.raises(ValueError, match="Unknown sort column"):
        core.sort_csv(str(source), str(output), ["missing"], numeric=True)
    assert output.read_bytes() == b"keep"


def test_cli_numeric_sort(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,score\nten,10\ntwo,2\n", encoding="utf-8")
    output = tmp_path / "out.csv"
    result = CliRunner().invoke(
        main,
        [
            "sort",
            "-i",
            str(source),
            "-o",
            str(output),
            "--by",
            "score",
            "--numeric",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "numeric" in result.output
    assert [row["name"] for row in core.read_csv(output)[1]] == ["two", "ten"]


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
