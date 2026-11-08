# CSV Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A powerful CSV data processing toolkit. Merge, split, filter, sort, and convert CSV files from the command line.

## 🌟 Features

- 🔗 **Merge** - Combine multiple CSV files into one
- ✂️ **Split** - Split CSV into multiple files by column value
- 🔍 **Filter** - Filter rows by condition (e.g. age >= 18)
- ↕️ **Sort** - Sort by one or more columns
- 🔄 **Convert** - Convert CSV to JSON format
- 🐍 **Python API** - Use as a library in your code

## 📦 Installation

```bash
git clone https://github.com/Master-626/csv-toolkit.git
cd csv-toolkit
pip install .
```

## 🚀 Usage

### Merge CSVs
```bash
csv-toolkit merge -i data1.csv data2.csv -o merged.csv --deduplicate
```

### Filter Rows
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
```bash
# Sort by score descending
csv-toolkit sort -i users.csv -o sorted_users.csv --by score --descending
```

### Split by Column
```bash
csv-toolkit split -i data.csv -o ./output --by city
```

Split keeps every distinct column value in its own file. Names use letters,
numbers, and underscores; empty values use `empty.csv`, and Windows device
names such as `CON` gain a leading underscore. If names collide (including
differences in case), numeric suffixes such as `_2` keep them distinct. Names
are assigned in first-seen row order, reserving other groups' unsuffixed names.

Existing output files, directories, and symlinks are never overwritten. A
conflicting destination, including the input file itself, stops the split;
choose an empty output directory or move the conflicting files first. The
column must exist. All CSV data is staged before outputs are published, and
files created by the split are removed if publication fails. The destination
filesystem must support hard links for atomic, no-overwrite publication.
This is not a multi-file transaction against process termination or concurrent
directory changes; cleanup failures are reported explicitly.

### Convert Format
```bash
# CSV to JSON
csv-toolkit convert -i data.csv -o data.json --format json
```

## 🐍 Python API

```python
from csv_toolkit import merge_csv, filter_csv, sort_csv

# Filter data
filter_csv(input_path="input.csv", output_path="filtered.csv", condition="age >= 18")

# Merge multiple files
merge_csv(input_paths=["data1.csv", "data2.csv"], output_path="merged.csv", deduplicate=True)

# Sort
sort_csv(input_path="data.csv", output_path="sorted.csv", by=["score"], ascending=False)
```

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT License
