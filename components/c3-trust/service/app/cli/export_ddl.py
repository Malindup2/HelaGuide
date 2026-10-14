"""Print the PostgreSQL CREATE TABLE statements for C3's tables (for infra/postgres at integration).

    python -m app.cli.export_ddl > c3_tables.sql
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.cli._common import utf8
from app.core.db import metadata


def main() -> None:
    utf8()
    print("-- C3 tables (generated from app/core/db.py). Schema c3 already exists in infra/postgres/001_init.sql.")
    print("CREATE SCHEMA IF NOT EXISTS c3;\nSET search_path TO c3;\n")
    for table in metadata.sorted_tables:
        print(str(CreateTable(table, if_not_exists=True).compile(dialect=postgresql.dialect())).strip() + ";\n")
        for idx in table.indexes:
            print(str(CreateIndex(idx).compile(dialect=postgresql.dialect())).strip() + ";")


if __name__ == "__main__":
    main()
