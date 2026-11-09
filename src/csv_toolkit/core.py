"""
Core CSV processing logic.
"""

from __future__ import annotations

import csv
import errno
import json
import operator
import os
import tempfile
import unicodedata
from contextlib import contextmanager
from decimal import Context, Decimal, InvalidOperation
from pathlib import Path
from typing import List


def read_csv(file_path: Path) -> tuple[List[str], List[dict]]:
    """Read CSV file and return headers and rows."""
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        headers = reader.fieldnames or []
        if len(set(headers)) != len(headers):
            raise ValueError(f"Duplicate CSV column names in {file_path}")
        rows = []
        for row in reader:
            if None in row:
                raise ValueError(
                    f"Too many CSV fields in {file_path} at line {reader.line_num}"
                )
            rows.append(row)
    return headers, rows


@contextmanager
def _new_output(file_path: Path):
    """Stage a complete UTF-8 file and publish without replacing any entry."""
    file_path = Path(file_path)
    # lexists also rejects dangling symlinks, unlike Path.exists(). The final
    # hard link enforces the same no-clobber rule against a concurrent writer.
    if os.path.lexists(file_path):
        raise FileExistsError(
            errno.EEXIST,
            "Refusing to overwrite an existing destination",
            str(file_path),
        )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".csv-toolkit-", dir=file_path.parent
    ) as staging:
        staged = Path(staging) / "output"
        with staged.open("x", encoding="utf-8", newline="") as stream:
            yield stream
        os.link(staged, file_path)


def write_csv(file_path: Path, headers: List[str], rows: List[dict]):
    """Write a complete CSV file without overwriting an existing destination."""
    with _new_output(file_path) as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def merge_csv(input_paths: List[str], output_path: str, deduplicate: bool = False):
    """Merge multiple CSV files into one."""
    if not input_paths:
        raise ValueError("At least one input CSV file is required")
    all_rows = []
    all_headers = set()

    for path in input_paths:
        headers, rows = read_csv(Path(path))
        all_headers.update(headers)
        all_rows.extend(rows)

    if deduplicate:
        seen = set()
        unique_rows = []
        for row in all_rows:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                unique_rows.append(row)
        all_rows = unique_rows

    write_csv(Path(output_path), sorted(all_headers), all_rows)
    return len(all_rows)


def filter_csv(input_path: str, output_path: str, condition: str):
    """Filter with ==, !=, <, <=, >, or >= using numeric or text comparisons.

    A numeric right-hand value selects exact, finite decimal comparisons;
    otherwise comparisons are case-sensitive and lexicographic. Missing cells
    never match. Numeric comparisons also skip nonnumeric or nonfinite cells.
    """
    headers, rows = read_csv(Path(input_path))

    parts = condition.split()
    if len(parts) != 3:
        raise ValueError("Condition format: 'column operator value' (e.g. 'age >= 18')")

    column, op, value = parts
    comparisons = {
        "==": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }
    if op not in comparisons:
        raise ValueError(
            f"Unsupported filter operator: {op!r}; use ==, !=, <, <=, >, or >="
        )
    if column not in headers:
        raise ValueError(f"Unknown filter column: {column!r}")
    compare = comparisons[op]

    # A private context keeps invalid-number handling independent of the
    # caller's decimal traps. Decimal construction and comparison are exact,
    # including integers larger than float's 53-bit precision.
    number_context = Context(traps=[InvalidOperation])
    try:
        numeric_value = Decimal(value, context=number_context)
    except InvalidOperation:
        # Numeric syntax with an exponent beyond Decimal's representation must
        # not silently switch to text ordering. Float is only a syntax probe;
        # its rounded result is never used for a comparison.
        try:
            float(value)
        except ValueError:
            numeric_value = None
        else:
            raise ValueError(
                "Numeric filter value is outside the supported decimal range"
            )
    if numeric_value is not None and not numeric_value.is_finite():
        raise ValueError("Numeric filter value must be finite")

    filtered = []
    for row in rows:
        cell_value = row.get(column)
        if cell_value is None:
            continue
        if numeric_value is None:
            matches = compare(cell_value, value)
        else:
            try:
                number = Decimal(cell_value, context=number_context)
            except InvalidOperation:
                continue
            if not number.is_finite():
                continue
            matches = compare(number, numeric_value)
        if matches:
            filtered.append(row)

    write_csv(Path(output_path), headers, filtered)
    return len(filtered)


def sort_csv(input_path: str, output_path: str, by: List[str], ascending: bool = True):
    """Stably sort text columns; missing cells sort like empty strings."""
    headers, rows = read_csv(Path(input_path))
    if not by:
        raise ValueError("At least one sort column is required")
    for column in by:
        if column not in headers:
            raise ValueError(f"Unknown sort column: {column!r}")

    def sort_key(row):
        return [row.get(col) or "" for col in by]

    rows.sort(key=sort_key, reverse=not ascending)
    write_csv(Path(output_path), headers, rows)
    return len(rows)


def _split_name_key(name: str) -> str:
    """Compare output names conservatively, including case-insensitive disks."""
    return unicodedata.normalize("NFC", name).casefold()


def _split_filenames(keys):
    """Keep readable names, adding suffixes without stealing another group's name."""
    reserved_devices = {"con", "prn", "aux", "nul"}
    reserved_devices.update(
        f"{prefix}{n}" for prefix in ("com", "lpt") for n in "123456789¹²³"
    )
    stems = []
    for key in keys:
        stem = "".join(c if c.isalnum() else "_" for c in str(key)) or "empty"
        if stem.casefold() in reserved_devices:
            stem = "_" + stem
        stems.append(stem)

    reserved = {_split_name_key(f"{stem}.csv") for stem in stems}
    used = set()
    next_suffix = {}
    filenames = []
    for stem in stems:
        filename = f"{stem}.csv"
        if _split_name_key(filename) in used:
            stem_key = _split_name_key(stem)
            suffix = next_suffix.get(stem_key, 2)
            while True:
                filename = f"{stem}_{suffix}.csv"
                name_key = _split_name_key(filename)
                if name_key not in reserved and name_key not in used:
                    break
                suffix += 1
            next_suffix[stem_key] = suffix + 1
        used.add(_split_name_key(filename))
        filenames.append(filename)
    return filenames


def _check_split_destinations(output_path: Path, filenames):
    """Reject every existing directory entry, including dangling symlinks."""
    if not output_path.exists():
        return
    existing = {_split_name_key(path.name): path for path in output_path.iterdir()}
    for filename in filenames:
        if _split_name_key(filename) in existing:
            raise FileExistsError(
                errno.EEXIST,
                "Refusing to overwrite an existing split destination",
                str(existing[_split_name_key(filename)]),
            )


def split_csv(input_path: str, output_dir: str, by_column: str):
    """Split into unique files without replacing existing files or the input.

    All data is staged before publishing. On an ordinary write/publish failure,
    remove files created by this call, leaving pre-existing entries untouched.
    """
    headers, rows = read_csv(Path(input_path))
    if by_column not in headers:
        raise ValueError(f"Unknown split column: {by_column!r}")

    groups = {}
    for row in rows:
        key = row.get(by_column, "unknown")
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    if not groups:
        return 0

    output_path = Path(output_dir)
    filenames = _split_filenames(groups)
    _check_split_destinations(output_path, filenames)
    output_path.mkdir(parents=True, exist_ok=True)

    # Stage on the same filesystem so hard-link publication is atomic and never
    # replaces a destination that appears after the preflight check.
    with tempfile.TemporaryDirectory(
        prefix=".csv-toolkit-", dir=output_path
    ) as staging:
        staged_paths = [Path(staging) / str(index) for index in range(len(groups))]
        for staged, group_rows in zip(staged_paths, groups.values()):
            write_csv(staged, headers, group_rows)

        published = []
        try:
            _check_split_destinations(output_path, filenames)
            for staged, filename in zip(staged_paths, filenames):
                destination = output_path / filename
                os.link(staged, destination)
                published.append((staged, destination))
        except BaseException:
            cleanup_failures = []
            for staged, destination in reversed(published):
                try:
                    # Avoid removing a replacement observed during cleanup,
                    # including a symlink installed by a different writer.
                    if os.path.samestat(staged.stat(), os.lstat(destination)):
                        destination.unlink()
                except FileNotFoundError:
                    pass
                except OSError as error:
                    cleanup_failures.append(f"{destination}: {error}")
            if cleanup_failures:
                raise OSError(
                    "Split failed; could not clean up: " + "; ".join(cleanup_failures)
                )
            raise

    return len(groups)


def convert_csv(input_path: str, output_path: str, output_format: str):
    """Convert CSV to JSON without replacing an existing destination."""
    if output_format != "json":
        raise ValueError(f"Unsupported format: {output_format}")
    _, rows = read_csv(Path(input_path))
    with _new_output(Path(output_path)) as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    return len(rows)
