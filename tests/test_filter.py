import csv
from decimal import InvalidOperation, localcontext

import pytest
from click.testing import CliRunner

from csv_toolkit.cli import main
from csv_toolkit.core import filter_csv, read_csv


@pytest.fixture
def source_csv(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,score,city\n"
        "Alice,18,Alpha\n"
        "Bob,25,Beta\n"
        "Charlie,30,Gamma\n"
        "Dana,25,Beta\n",
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize("column,value", [("score", "25"), ("city", "Beta")])
@pytest.mark.parametrize(
    "operator,expected",
    [
        ("==", ["Bob", "Dana"]),
        ("!=", ["Alice", "Charlie"]),
        ("<", ["Alice"]),
        ("<=", ["Alice", "Bob", "Dana"]),
        (">", ["Charlie"]),
        (">=", ["Bob", "Charlie", "Dana"]),
    ],
)
def test_all_filter_operators(source_csv, tmp_path, column, value, operator, expected):
    original = source_csv.read_bytes()
    output = tmp_path / "out" / "result.csv"
    count = filter_csv(str(source_csv), str(output), f"{column} {operator} {value}")
    headers, rows = read_csv(output)

    assert headers == ["name", "score", "city"]
    assert [row["name"] for row in rows] == expected
    assert count == len(expected)
    assert source_csv.read_bytes() == original


@pytest.mark.parametrize(
    "condition,error",
    [
        ("score = 25", "Unsupported filter operator"),
        ("score <> 25", "Unsupported filter operator"),
        ("city <> Beta", "Unsupported filter operator"),
        ("city contains Beta", "Unsupported filter operator"),
        ("score => 25", "Unsupported filter operator"),
        ("missing >= 0", "Unknown filter column"),
        ("missing != Beta", "Unknown filter column"),
        ("", "Condition format"),
        ("score", "Condition format"),
        ("score >=", "Condition format"),
        ("score>=25", "Condition format"),
        ("score >= 25 extra", "Condition format"),
        ("city == New York", "Condition format"),
    ],
)
@pytest.mark.parametrize("existing_output", [False, True])
def test_invalid_filter_does_not_touch_output(
    source_csv, tmp_path, condition, error, existing_output
):
    original = source_csv.read_bytes()
    output = tmp_path / "out" / "result.csv"
    if existing_output:
        output.parent.mkdir()
        output.write_bytes(b"preserve existing output")

    with pytest.raises(ValueError, match=error):
        filter_csv(str(source_csv), str(output), condition)

    assert source_csv.read_bytes() == original
    if existing_output:
        assert output.read_bytes() == b"preserve existing output"
    else:
        assert not output.parent.exists()


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Inf", "-Infinity"])
def test_nonfinite_condition_is_rejected(source_csv, tmp_path, value):
    output = tmp_path / "result.csv"
    output.write_bytes(b"preserve existing output")
    with pytest.raises(ValueError, match="must be finite"):
        filter_csv(str(source_csv), str(output), f"score != {value}")
    assert output.read_bytes() == b"preserve existing output"


@pytest.mark.parametrize(
    "value", ["1e9999999999999999999999", "1e-9999999999999999999999"]
)
def test_out_of_range_numeric_condition_does_not_become_text(
    source_csv, tmp_path, value
):
    output = tmp_path / "result.csv"
    output.write_bytes(b"preserve existing output")
    with pytest.raises(ValueError, match="outside the supported decimal range"):
        filter_csv(str(source_csv), str(output), f"score > {value}")
    assert output.read_bytes() == b"preserve existing output"


@pytest.mark.parametrize(
    "values,condition,expected",
    [
        (
            ["9007199254740992", "9007199254740993"],
            "value == 9007199254740993",
            ["9007199254740993"],
        ),
        (
            ["9007199254740992", "9007199254740993"],
            "value != 9007199254740993",
            ["9007199254740992"],
        ),
        (
            ["1.0000000000000000000000001", "1.0000000000000000000000002"],
            "value > 1.0000000000000000000000001",
            ["1.0000000000000000000000002"],
        ),
        (["2", "2.0", "02", "2e0", "3"], "value == 2", ["2", "2.0", "02", "2e0"]),
        (["-10", "-2.5", "0", "2.5"], "value < -2e0", ["-10", "-2.5"]),
        (["1e999", "1e1000"], "value < 1e1000", ["1e999"]),
    ],
)
def test_numeric_comparisons_are_exact(tmp_path, values, condition, expected):
    source = tmp_path / "input.csv"
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["value"])
        writer.writerows([value] for value in values)
    output = tmp_path / "result.csv"

    count = filter_csv(str(source), str(output), condition)

    assert [row["value"] for row in read_csv(output)[1]] == expected
    assert count == len(expected)


@pytest.mark.parametrize("operator", ["==", "!=", "<", "<=", ">", ">="])
def test_numeric_filters_skip_missing_and_invalid_cells(tmp_path, operator):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,value\nblank,\nmissing\ntext,nope\nnan,NaN\nsnan,sNaN\n"
        "inf,Infinity\nnegative-inf,-Inf\nequal,25\nother,30\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.csv"
    filter_csv(str(source), str(output), f"value {operator} 25")

    names = [row["name"] for row in read_csv(output)[1]]
    expected = {
        "==": ["equal"],
        "!=": ["other"],
        "<": [],
        "<=": ["equal"],
        ">": ["other"],
        ">=": ["equal", "other"],
    }
    assert names == expected[operator]


def test_text_filters_distinguish_missing_and_empty_cells(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "name,city\nmissing\nblank,\nlowercase,beta\nmatch,Beta\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.csv"

    assert filter_csv(str(source), str(output), "city != Beta") == 2
    assert [row["name"] for row in read_csv(output)[1]] == ["blank", "lowercase"]


def test_decimal_context_does_not_change_filter_results(source_csv, tmp_path):
    output = tmp_path / "result.csv"
    with localcontext() as context:
        context.prec = 1
        context.traps[InvalidOperation] = False
        context.clear_flags()
        assert filter_csv(str(source_csv), str(output), "city != Beta") == 2
        assert [row["name"] for row in read_csv(output)[1]] == ["Alice", "Charlie"]
        numeric_output = tmp_path / "numeric.csv"
        assert filter_csv(str(source_csv), str(numeric_output), "score > 18") == 3
        assert not context.flags[InvalidOperation]


def test_header_only_filter_keeps_header(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name,score\n", encoding="utf-8")
    output = tmp_path / "result.csv"
    assert filter_csv(str(source), str(output), "score != 25") == 0
    assert read_csv(output) == (["name", "score"], [])


@pytest.mark.parametrize("content", ["", "name,score\n"])
def test_unknown_column_rejected_without_data_rows(tmp_path, content):
    source = tmp_path / "input.csv"
    source.write_text(content, encoding="utf-8")
    output = tmp_path / "result.csv"
    with pytest.raises(ValueError, match="Unknown filter column"):
        filter_csv(str(source), str(output), "missing >= 0")
    assert not output.exists()


def test_cli_filter_reports_correct_count(source_csv, tmp_path):
    output = tmp_path / "result.csv"
    result = CliRunner().invoke(
        main,
        [
            "filter",
            "-i",
            str(source_csv),
            "-o",
            str(output),
            "--condition",
            "city != Beta",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "2 rows match" in result.output
    assert [row["name"] for row in read_csv(output)[1]] == ["Alice", "Charlie"]


@pytest.mark.parametrize("condition", ["city <> Beta", "missing >= 0", "score != NaN"])
def test_cli_filter_reports_validation_error(source_csv, tmp_path, condition):
    output = tmp_path / "result.csv"
    output.write_bytes(b"preserve existing output")
    result = CliRunner().invoke(
        main,
        ["filter", "-i", str(source_csv), "-o", str(output), "--condition", condition],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Filtered:" not in result.output
    assert "Traceback" not in result.output
    assert output.read_bytes() == b"preserve existing output"


def test_cli_filter_reports_input_io_error(tmp_path):
    output = tmp_path / "result.csv"
    result = CliRunner().invoke(
        main,
        [
            "filter",
            "-i",
            str(tmp_path / "missing.csv"),
            "-o",
            str(output),
            "--condition",
            "score >= 25",
        ],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Filtered:" not in result.output
    assert "Traceback" not in result.output
    assert not output.exists()
