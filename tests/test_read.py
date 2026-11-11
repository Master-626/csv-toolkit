import pytest

from csv_toolkit.core import filter_csv, read_csv, sort_csv, split_csv


def test_leading_bom_does_not_rename_columns(tmp_path):
    source = tmp_path / "input.csv"
    source.write_bytes(
        "\ufeffcity,name\nShanghai,Bob\nBeijing,Alice\n".encode("utf-8")
    )

    assert read_csv(source)[0] == ["city", "name"]
    assert read_csv(source)[1][0]["city"] == "Shanghai"

    filtered = tmp_path / "filtered.csv"
    assert filter_csv(str(source), str(filtered), "city == Beijing") == 1
    assert filtered.read_bytes().startswith(b"city,name")
    assert not filtered.read_bytes().startswith(b"\xef\xbb\xbf")
    assert [row["name"] for row in read_csv(filtered)[1]] == ["Alice"]

    sorted_out = tmp_path / "sorted.csv"
    sort_csv(str(source), str(sorted_out), ["city"])
    assert [row["city"] for row in read_csv(sorted_out)[1]] == [
        "Beijing",
        "Shanghai",
    ]

    split_out = tmp_path / "split"
    assert split_csv(str(source), str(split_out), "city") == 2
    assert {path.name for path in split_out.iterdir()} == {
        "Beijing.csv",
        "Shanghai.csv",
    }


def test_invalid_utf8_is_rejected(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_bytes(b"name\n\xff\n")
    with pytest.raises(UnicodeDecodeError):
        read_csv(source)
