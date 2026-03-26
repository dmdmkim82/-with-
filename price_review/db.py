from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pandas as pd

from .parser import PriceRecord, parse_pdf


def connect(db_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path | str) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_month TEXT NOT NULL,
                source_file TEXT NOT NULL,
                UNIQUE (report_month, source_file)
            );

            CREATE TABLE IF NOT EXISTS materials (
                item_code TEXT PRIMARY KEY,
                section_key TEXT NOT NULL,
                section_name TEXT NOT NULL,
                section_order INTEGER NOT NULL,
                spec TEXT NOT NULL,
                spec_value REAL NOT NULL,
                variant TEXT NOT NULL,
                variant_order INTEGER NOT NULL,
                unit TEXT NOT NULL,
                detail TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS material_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_code TEXT NOT NULL,
                report_month TEXT NOT NULL,
                price REAL NOT NULL,
                source_file TEXT NOT NULL,
                UNIQUE (item_code, report_month),
                FOREIGN KEY (item_code) REFERENCES materials(item_code)
            );
            """
        )


def rebuild_database(db_path: Path | str, pdf_paths: list[Path | str]) -> dict[str, int]:
    parsed_records: list[PriceRecord] = []

    for pdf_path in pdf_paths:
        parsed_records.extend(parse_pdf(pdf_path))

    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS material_prices;
            DROP TABLE IF EXISTS materials;
            DROP TABLE IF EXISTS reports;
            """
        )

    initialize_database(db_path)

    with closing(connect(db_path)) as connection:
        insert_records(connection, parsed_records)

        summary = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM reports) AS report_count,
                (SELECT COUNT(*) FROM materials) AS material_count,
                (SELECT COUNT(*) FROM material_prices) AS price_count
            """
        ).fetchone()

    return {
        "report_count": int(summary["report_count"]),
        "material_count": int(summary["material_count"]),
        "price_count": int(summary["price_count"]),
    }


def insert_records(connection: sqlite3.Connection, records: list[PriceRecord]) -> None:
    report_rows = sorted({(record.report_month, record.source_file) for record in records})
    material_rows = {
        record.item_code: (
            record.item_code,
            record.section_key,
            record.section_name,
            record.section_order,
            record.spec,
            record.spec_value,
            record.variant,
            record.variant_order,
            record.unit,
            record.detail,
        )
        for record in records
    }
    price_rows = [
        (record.item_code, record.report_month, record.price, record.source_file)
        for record in records
    ]

    connection.executemany(
        "INSERT INTO reports (report_month, source_file) VALUES (?, ?)",
        report_rows,
    )
    connection.executemany(
        """
        INSERT INTO materials (
            item_code,
            section_key,
            section_name,
            section_order,
            spec,
            spec_value,
            variant,
            variant_order,
            unit,
            detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        list(material_rows.values()),
    )
    connection.executemany(
        """
        INSERT INTO material_prices (item_code, report_month, price, source_file)
        VALUES (?, ?, ?, ?)
        """,
        price_rows,
    )
    connection.commit()


def get_summary(db_path: Path | str) -> dict[str, str | int]:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM reports) AS report_count,
                (SELECT COUNT(*) FROM materials) AS material_count,
                (SELECT COUNT(*) FROM material_prices) AS price_count,
                (SELECT MIN(report_month) FROM reports) AS first_month,
                (SELECT MAX(report_month) FROM reports) AS last_month
            """
        ).fetchone()

    return {
        "report_count": int(row["report_count"] or 0),
        "material_count": int(row["material_count"] or 0),
        "price_count": int(row["price_count"] or 0),
        "first_month": row["first_month"],
        "last_month": row["last_month"],
    }


def get_master_dataframe(db_path: Path | str) -> pd.DataFrame:
    with closing(connect(db_path)) as connection:
        dataframe = pd.read_sql_query(
            """
            WITH ranked_prices AS (
                SELECT
                    mp.item_code,
                    mp.report_month,
                    mp.price,
                    ROW_NUMBER() OVER (
                        PARTITION BY mp.item_code
                        ORDER BY mp.report_month DESC
                    ) AS row_no
                FROM material_prices mp
            )
            SELECT
                m.item_code,
                m.section_key,
                m.section_name,
                m.section_order,
                m.spec,
                m.spec_value,
                m.variant,
                m.variant_order,
                m.unit,
                m.detail,
                MAX(CASE WHEN rp.row_no = 1 THEN rp.report_month END) AS latest_month,
                MAX(CASE WHEN rp.row_no = 1 THEN rp.price END) AS latest_price,
                MAX(CASE WHEN rp.row_no = 2 THEN rp.report_month END) AS previous_month,
                MAX(CASE WHEN rp.row_no = 2 THEN rp.price END) AS previous_price
            FROM materials m
            LEFT JOIN ranked_prices rp ON rp.item_code = m.item_code
            GROUP BY
                m.item_code,
                m.section_key,
                m.section_name,
                m.section_order,
                m.spec,
                m.spec_value,
                m.variant,
                m.variant_order,
                m.unit,
                m.detail
            ORDER BY m.section_order, m.spec_value, m.variant_order
            """,
            connection,
        )
    return dataframe


def get_timeseries_dataframe(db_path: Path | str, item_codes: list[str]) -> pd.DataFrame:
    if not item_codes:
        return pd.DataFrame()

    placeholders = ", ".join("?" for _ in item_codes)
    query = f"""
        SELECT
            mp.item_code,
            m.section_name,
            m.spec,
            m.variant,
            mp.report_month,
            mp.price,
            m.unit
        FROM material_prices mp
        JOIN materials m ON m.item_code = mp.item_code
        WHERE mp.item_code IN ({placeholders})
        ORDER BY m.section_order, m.spec_value, m.variant_order, mp.report_month
    """

    with closing(connect(db_path)) as connection:
        dataframe = pd.read_sql_query(query, connection, params=item_codes)
    return dataframe
