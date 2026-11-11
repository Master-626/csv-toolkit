# CSV Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

## 简介

CSV Toolkit 是一个命令行工具，也可以当作 Python 库使用。它能合并多个 CSV、按某一列拆成多个文件、按条件筛选行、按列排序，以及把 CSV 转成 JSON。每次操作都只写入新文件，不会覆盖已经存在的文件。

```bash
pip install .
csv-toolkit filter -i users.csv -o adults.csv --condition "age >= 18"
pip install -e ".[dev]" && pytest
```

读取 CSV 时会忽略文件开头的 UTF-8 BOM。合并时列顺序跟第一个文件，之后的文件只追加新列；`--deduplicate` 把缺失单元格和空单元格视为相同。按列拆分时，缺失值和空值一起写入 `empty.csv`，文本 `None` 仍写入 `None.csv`。排序默认是区分大小写的文本序；加上 `--numeric` 后按精确十进制数值排序，因此 `2` 会排在 `10` 前面。

## Purpose

CSV Toolkit merges, splits, filters, and sorts CSV files, and converts them to JSON. Use it from the `csv-toolkit` command or import the same operations in Python. Every operation writes a new file and refuses to replace an existing one.

## Features

- **Merge** — combine CSV files and optionally drop duplicate rows
- **Split** — write one file for each distinct value in a column
- **Filter** — keep rows that match a comparison such as `age >= 18`
- **Sort** — order by one or more columns, as text or as exact decimals
- **Convert** — write the rows as JSON
- **Python API** — call the same operations from code

## Installation

Python 3.8 or newer is required. Click is the only runtime dependency.

```bash
git clone https://github.com/Master-626/csv-toolkit.git
cd csv-toolkit
pip install .
```

The `csv-toolkit` command is then on `PATH`. `csv-toolkit --help` lists commands, and `csv-toolkit COMMAND --help` lists that command's options. `csv-toolkit --version` prints the installed version.

Install the development extras to run tests and the linter:

```bash
pip install -e ".[dev]"
```

## Output safety

Every operation creates **new** output files. Existing files, directories, and
symlinks (including dangling links and aliases of an input file) are refused;
there is no implicit overwrite or in-place mode. Choose a new destination when
rerunning an operation. This also applies to the Python API's `write_csv`.

CSV and JSON outputs are completely written to a temporary file beside the
destination before atomic, no-overwrite publication. A serialization, write, or
publication error does not leave a partial result or replace existing data.
The destination filesystem must support hard links. This is not a durability
guarantee against power loss or protection against concurrent directory changes.
An output directory created for the operation may remain empty on failure.

Input CSVs with duplicate headers, extra fields, or malformed quoting are
rejected instead of silently dropping data. Missing trailing cells remain
supported. Quoted cell line endings are preserved. CLI errors use a nonzero
exit status and do not print a success message.

Input files are read as UTF-8. A leading byte-order mark, including the one
Excel writes for UTF-8 CSV, is ignored, so the first column keeps its real name.

## Usage

### Merge CSVs

Options: `-i` / `--inputs` (repeat once per file), `-o` / `--output`, `--deduplicate`.

```bash
csv-toolkit merge -i data1.csv -i data2.csv -o merged.csv --deduplicate
```

Columns follow the first input. Columns that appear only in a later file are appended in that file's order. Merging a file does not alphabetize its header.

`--deduplicate` keeps the first copy of a row. Comparison uses the values that will be written: a missing cell, an empty cell, and a column absent from one of the inputs are all empty. Distinct text stays distinct, including `2` and `02`.

### Filter Rows

Options: `-i` / `--input`, `-o` / `--output`, `--condition`.

```bash
csv-toolkit filter -i users.csv -o adults.csv --condition "age >= 18"

# Exclude a city
csv-toolkit filter -i users.csv -o other_cities.csv --condition "city != Beijing"
```

Conditions use three whitespace-separated parts: `column operator value`.
Supported operators are `==`, `!=`, `<`, `<=`, `>`, and `>=`. Column names and
values containing whitespace are not supported. Numeric values use exact
decimal comparisons, including large integers and scientific notation; other
values use case-sensitive lexicographic text comparisons. Numeric filters skip
blank, missing, nonnumeric, and nonfinite cells. Text filters skip missing cells
but compare explicit empty cells as empty strings. Nonfinite numeric condition
values (such as `NaN` or `Infinity`), numeric exponents outside the supported
decimal range, unknown columns, and unsupported operators raise an error before
writing output.

### Sort

Options: `-i` / `--input`, `-o` / `--output`, `--by` (repeat for each column), `--descending`, `--numeric`.

```bash
# Sort by score descending
csv-toolkit sort -i users.csv -o sorted_users.csv --by score --descending

# Numeric order: 2 before 10, including integers larger than a float
csv-toolkit sort -i users.csv -o by_score.csv --by score --numeric
```

Sorting is stable. The default is case-sensitive **text** ordering (`10` sorts before `2`).
Repeat `--by` for multiple columns. All named columns must exist, even for a
header-only file; the Python API also rejects an empty column list. Missing
trailing cells sort like empty strings. Equal keys retain their input order,
including when sorting descending.

`--numeric` compares finite decimal values exactly, using the same numeric rules as filters. Blank, missing, and nonnumeric cells form one group and use case-sensitive text order inside that group. That group comes first in an ascending sort. `--descending` reverses the whole key, so numbers come first and nonnumeric cells come last. `--numeric` applies to every `--by` column. A column whose values are all nonnumeric still sorts as text.

### Split by Column

Options: `-i` / `--input`, `-o` / `--output-dir`, `--by`.

```bash
csv-toolkit split -i data.csv -o ./output --by city
```

Split keeps every distinct column value in its own file. Names use letters,
numbers, and underscores; empty values use `empty.csv`, and Windows device
names such as `CON` gain a leading underscore. If names collide (including
differences in case), numeric suffixes such as `_2` keep them distinct. Names
are assigned in first-seen row order, reserving other groups' unsuffixed names.
A missing cell in the split column is grouped with an empty cell, because both
are written as empty fields, and that group uses `empty.csv`. The literal text
`None` is an ordinary value and uses `None.csv`.

Existing output files, directories, and symlinks are never overwritten. A
conflicting destination, including the input file itself, stops the split;
choose an empty output directory or move the conflicting files first. The
column must exist. All CSV data is staged before outputs are published, and
files created by the split are removed if publication fails. The destination
filesystem must support hard links for atomic, no-overwrite publication.
This is not a multi-file transaction against process termination or concurrent
directory changes; cleanup failures are reported explicitly.

### Convert Format

Options: `-i` / `--input`, `-o` / `--output`, `-f` / `--format`. The only format is `json`.

```bash
csv-toolkit convert -i data.csv -o data.json --format json
```

JSON is a list of objects in input order. Missing cells are JSON `null`. An existing destination is left untouched.

## Python API

```python
from csv_toolkit import convert_csv, filter_csv, merge_csv, sort_csv, split_csv

filter_csv(input_path="input.csv", output_path="filtered.csv", condition="age >= 18")

merge_csv(
    input_paths=["data1.csv", "data2.csv"],
    output_path="merged.csv",
    deduplicate=True,
)

sort_csv(input_path="data.csv", output_path="sorted.csv", by=["score"], ascending=False)
sort_csv(input_path="data.csv", output_path="by_score.csv", by=["score"], numeric=True)

split_csv(input_path="data.csv", output_dir="output", by_column="city")
convert_csv(input_path="data.csv", output_path="data.json", output_format="json")
```

`numeric` is keyword-only. The other parameters match the command options above.

## Testing

Supported Python versions are 3.8 through 3.13. From a checkout:

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

GitHub Actions runs ruff and pytest on those versions, including a run with the minimum declared Click and pytest versions.

## License

MIT License
