"""
CLI interface for csv-toolkit.
"""

import csv

import click

from .core import merge_csv, filter_csv, sort_csv, split_csv, convert_csv


@click.group()
@click.version_option()
def main():
    """CSV Toolkit - Powerful CSV data processing toolkit."""
    pass


@main.command()
@click.option("-i", "--inputs", multiple=True, required=True, help="Input CSV files")
@click.option("-o", "--output", required=True, help="Output CSV file")
@click.option("--deduplicate", is_flag=True, help="Remove duplicate rows")
def merge(inputs, output, deduplicate):
    """Merge multiple CSV files into one."""
    try:
        count = merge_csv(list(inputs), output, deduplicate)
    except (OSError, ValueError, csv.Error) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"✅ Merged {len(inputs)} files, total {count} rows -> {output}")


@main.command()
@click.option("-i", "--input", required=True, help="Input CSV file")
@click.option("-o", "--output", required=True, help="Output CSV file")
@click.option("--condition", required=True, help="Filter condition (e.g. 'age >= 18')")
def filter(input, output, condition):
    """Filter rows by condition."""
    try:
        count = filter_csv(input, output, condition)
    except (OSError, ValueError, csv.Error) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"✅ Filtered: {count} rows match -> {output}")


@main.command()
@click.option("-i", "--input", required=True, help="Input CSV file")
@click.option("-o", "--output", required=True, help="Output CSV file")
@click.option("--by", required=True, multiple=True, help="Column(s) to sort by")
@click.option("--descending", is_flag=True, help="Sort descending")
def sort(input, output, by, descending):
    """Sort CSV by column(s)."""
    try:
        sort_csv(input, output, list(by), ascending=not descending)
    except (OSError, ValueError, csv.Error) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"✅ Sorted by {', '.join(by)} -> {output}")


@main.command()
@click.option("-i", "--input", required=True, help="Input CSV file")
@click.option("-o", "--output-dir", required=True, help="Output directory")
@click.option("--by", required=True, help="Column to split by")
def split(input, output_dir, by):
    """Split CSV into multiple files by column."""
    try:
        count = split_csv(input, output_dir, by)
    except (OSError, ValueError, csv.Error) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"✅ Split into {count} files -> {output_dir}")


@main.command()
@click.option("-i", "--input", required=True, help="Input CSV file")
@click.option("-o", "--output", required=True, help="Output file")
@click.option("-f", "--format", "output_format", required=True, type=click.Choice(["json"]), help="Output format")
def convert(input, output, output_format):
    """Convert CSV to other formats."""
    try:
        count = convert_csv(input, output, output_format)
    except (OSError, ValueError, csv.Error) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"✅ Converted {count} rows to {output_format} -> {output}")


if __name__ == "__main__":
    main()
