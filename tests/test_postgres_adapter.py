"""Unit coverage for SQLite-compatible PostgreSQL SQL translation."""
import unittest
from unittest.mock import patch

from src.db.connection import _HybridRow, _translate_sql, get_connection


class TestPostgresAdapter(unittest.TestCase):
    def test_qmark_parameters_and_sqlite_timestamps_are_translated(self):
        sql = "SELECT * FROM products WHERE name LIKE ? AND notes = '?' AND id = ?"
        translated = _translate_sql(sql, ("%hut%", 2))
        self.assertEqual(
            translated,
            "SELECT * FROM products WHERE name ILIKE %s AND notes = '?' AND id = %s",
        )
        self.assertEqual(_translate_sql("UPDATE x SET t=datetime('now')"), "UPDATE x SET t=CURRENT_TIMESTAMP")

    def test_named_parameters_are_translated_without_touching_casts(self):
        translated = _translate_sql("INSERT INTO x (a, b) VALUES (:value, now()::text)", {"value": 3})
        self.assertEqual(translated, "INSERT INTO x (a, b) VALUES (%(value)s, now()::text)")

    def test_percent_wildcards_inside_sql_literals_are_escaped_for_psycopg(self):
        translated = _translate_sql("SELECT * FROM x WHERE notes LIKE 'Revision #%';", (1,))
        self.assertEqual(translated, "SELECT * FROM x WHERE notes ILIKE 'Revision #%%';")

    def test_postgres_rows_support_name_and_position_access(self):
        row = _HybridRow(("id", "name"), (7, "Pizza Hut"))
        self.assertEqual(row["id"], 7)
        self.assertEqual(row[0], 7)
        self.assertEqual(dict(row), {"id": 7, "name": "Pizza Hut"})

    def test_postgres_connection_requires_tls_and_has_bounded_timeout(self):
        with patch("src.db.connection.get_database_url", return_value="postgresql://redacted"):
            with patch("psycopg.connect", return_value=object()) as connect:
                get_connection()
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs["connect_timeout"], 10)
        self.assertEqual(kwargs["sslmode"], "require")


if __name__ == "__main__":
    unittest.main()
