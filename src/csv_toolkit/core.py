"""
Core CSV processing logic.
"""

from __future__ import annotations

import csv
import errno
import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import List


def read_csv(file_path: Path) -> tuple[List[str], List[dict]]:
    """Read CSV file and return headers and rows."""
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def write_csv(file_path: Path, headers: List[str], rows: List[dict]):
    """Write rows to CSV file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def merge_csv(input_paths: List[str], output_path: str, deduplicate: bool = False):
    """Merge multiple CSV files into one."""
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
    """Filter CSV rows by condition. Simple condition: column operator value."""
    headers, rows = read_csv(Path(input_path))

    # Parse simple condition: "age >= 18"
    parts = condition.split()
    if len(parts) != 3:
        raise ValueError("Condition format: 'column operator value' (e.g. 'age >= 18')")

    column, op, value = parts

    # Try numeric comparison
    try:
        value = float(value)
        filtered = []
        for row in rows:
            try:
                cell_value = float(row.get(column, 0))
                if op == ">=" and cell_value >= value:
                    filtered.append(row)
                elif op == "<=" and cell_value <= value:
                    filtered.append(row)
                elif op == ">" and cell_value > value:
                    filtered.append(row)
                elif op == "<" and cell_value < value:
                    filtered.append(row)
                elif op == "==" and cell_value == value:
                    filtered.append(row)
            except (ValueError, TypeError):
                continue
    except ValueError:
        # String comparison
        filtered = [row for row in rows if row.get(column, "") == value]

    write_csv(Path(output_path), headers, filtered)
    return len(filtered)


def sort_csv(input_path: str, output_path: str, by: List[str], ascending: bool = True):
    """Sort CSV by specified columns."""
    headers, rows = read_csv(Path(input_path))

    def sort_key(row):
        return [row.get(col, "") for col in by]

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
    """Convert CSV to other formats (json, excel)."""
    headers, rows = read_csv(Path(input_path))

    output_p = Path(output_path)
    output_p.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        with open(output_p, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    return len(rows)
