from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.make_three_wave_validation_report import (  # noqa: E402
    MIDDLEWAVE_HOUSEHOLDS,
    ROOT,
    validate_middlewave_count,
)


class MiddlewaveCountTests(unittest.TestCase):
    def test_middlewave_summary_sum_n_matches_household_file(self):
        summary_path = ROOT / "audit" / "middlewave_nonresponse_summary.csv"
        if not summary_path.exists() or not MIDDLEWAVE_HOUSEHOLDS.exists():
            self.skipTest("private row-level middlewave artifact is not available in this checkout")
        summary = pd.read_csv(summary_path)
        household_rows = len(pd.read_parquet(MIDDLEWAVE_HOUSEHOLDS))
        self.assertEqual(validate_middlewave_count(summary, household_rows), household_rows)

    def test_middlewave_summary_count_rejects_mismatch(self):
        summary = pd.DataFrame({"N": [3, 4]})
        with self.assertRaisesRegex(AssertionError, r"sum\(N\)=7 != household rows=8"):
            validate_middlewave_count(summary, 8)


if __name__ == "__main__":
    unittest.main()
