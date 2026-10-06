from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from common import config, path


def arrow_table(file: Path) -> pa.Table:
    table = pq.read_table(file)
    for name, field in zip(table.column_names, table.schema):
        if pa.types.is_dictionary(field.type) or pa.types.is_large_string(field.type):
            table = table.set_column(table.schema.get_field_index(name), name, table[name].cast(pa.string()))
    return table.replace_schema_metadata(None)


def append_tables(inputs: list[tuple[Path, str | None]], target: Path) -> dict:
    tables = []
    for file, component in inputs:
        table = arrow_table(file)
        if component is not None:
            table = table.append_column("Income_Component", pa.array([component] * table.num_rows, type=pa.string()))
        tables.append(table)
    if not tables:
        return {"status": "no_inputs", "rows": 0}
    schema = pa.unify_schemas([t.schema for t in tables], promote_options="permissive")
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    rows = 0
    try:
        for table in tables:
            present = set(table.column_names)
            aligned = []
            for field in schema:
                col = table[field.name] if field.name in present else pa.nulls(table.num_rows, type=field.type)
                if col.type != field.type:
                    col = col.cast(field.type, safe=False)
                aligned.append(col)
            out = pa.Table.from_arrays(aligned, schema=schema)
            if writer is None:
                writer = pq.ParquetWriter(target, schema, compression="zstd", version="2.6")
            writer.write_table(out, row_group_size=250_000)
            rows += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    return {"status": "created", "rows": rows, "size_bytes": target.stat().st_size}


def main() -> int:
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    years = list(range(start, end + 1))
    combos = [
        ("household", "household_1390_1403.parquet"),
        ("members", "members_1390_1403.parquet"),
        ("food", "food_1390_1403.parquet"),
    ]
    combined_dir = path("combined")
    combined_dir.mkdir(parents=True, exist_ok=True)
    for table, output in combos:
        inputs = [(path("yearly") / str(y) / f"{table}.parquet", None) for y in years]
        result = append_tables(inputs, combined_dir / output)
        print(f"{output}: {result}", flush=True)

    income_tables = ["income_wage", "income_self_employed", "income_other", "income_subsidy"]
    income_inputs = [
        (path("yearly") / str(y) / f"{table}.parquet", table)
        for y in years
        for table in income_tables
    ]
    result = append_tables(income_inputs, combined_dir / "income_1390_1403.parquet")
    print(f"income_1390_1403.parquet: {result}", flush=True)
    subsidy_inputs = [(path("yearly") / str(y) / "income_subsidy.parquet", None) for y in years]
    result = append_tables(subsidy_inputs, combined_dir / "income_subsidy_1390_1403.parquet")
    print(f"income_subsidy_1390_1403.parquet: {result}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
