"""
Core CSV processing logic.
"""

import csv
import json
from pathlib import Path
from typing import List, Optional


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


def split_csv(input_path: str, output_dir: str, by_column: str):
    """Split CSV into multiple files based on column values."""
    headers, rows = read_csv(Path(input_path))

    groups = {}
    for row in rows:
        key = row.get(by_column, "unknown")
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    output_path = Path(output_dir)
    count = 0
    for key, group_rows in groups.items():
        safe_key = "".join(c if c.isalnum() else "_" for c in str(key))
        write_csv(output_path / f"{safe_key}.csv", headers, group_rows)
        count += 1

    return count


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
