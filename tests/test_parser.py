from pathlib import Path
import tempfile
import unittest

from price_review.db import get_master_dataframe, rebuild_database
from price_review.parser import parse_pdf


BASE_DIR = Path(__file__).resolve().parent.parent


class ParserTests(unittest.TestCase):
    def test_parse_2025_known_prices(self) -> None:
        records = parse_pdf(BASE_DIR / "202504_1075.pdf")
        lookup = {(record.section_key, record.spec, record.variant): record.price for record in records}

        self.assertEqual(lookup[("fgv_tfr_gv", "2.5SQ", "")], 921.0)
        self.assertEqual(lookup[("kiv", "240SQ", "")], 53383.0)
        self.assertEqual(lookup[("fw_cv", "150SQ", "LV 4C")], 114912.0)

    def test_parse_2026_known_prices(self) -> None:
        records = parse_pdf(BASE_DIR / "202604_1075.pdf")
        lookup = {(record.section_key, record.spec, record.variant): record.price for record in records}

        self.assertEqual(lookup[("fgv_tfr_gv", "400SQ", "")], 105357.0)
        self.assertEqual(lookup[("fw_cv", "150SQ", "HV 3C")], 146869.0)
        self.assertEqual(lookup[("al_tfr_cv", "150SQ", "4C")], 18438.0)

    def test_parse_grounding_prices(self) -> None:
        records_2025 = parse_pdf(BASE_DIR / "202504_1198 grounding.pdf")
        records_2026 = parse_pdf(BASE_DIR / "202604_1198 grounding.pdf")

        lookup_2025 = {(record.section_name, record.spec): record.price for record in records_2025}
        lookup_2026 = {(record.section_name, record.spec): record.price for record in records_2026}

        self.assertGreater(len(records_2025), 80)
        self.assertGreater(len(records_2026), 80)
        self.assertEqual(lookup_2025[("접지 자재", "MOLD | 고려 | MEDIUM")], 60000.0)
        self.assertEqual(lookup_2026[("피뢰 자재", "피 뢰 침 지 지 대 | 상사 | 5m")], 504000.0)

    def test_database_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.sqlite"
            summary = rebuild_database(
                db_path,
                [BASE_DIR / "202504_1075.pdf", BASE_DIR / "202604_1075.pdf"],
            )
            master_df = get_master_dataframe(db_path)

        self.assertEqual(summary["report_count"], 2)
        self.assertGreater(summary["material_count"], 0)
        self.assertGreater(summary["price_count"], 0)
        self.assertIn("FGV_TFR_GV__2_5SQ", set(master_df["item_code"]))


if __name__ == "__main__":
    unittest.main()
