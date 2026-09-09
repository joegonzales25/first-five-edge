import math
import unittest

import numpy as np
import pandas as pd

from nfl_model_history import db_values, insert_values, safe_float


class CapturingConnection:
    def __init__(self):
        self.params = None

    def execute(self, _query, params):
        self.params = params


class NflModelHistoryTests(unittest.TestCase):
    def test_safe_float_rejects_missing_and_non_finite_values(self):
        for value in [pd.NA, np.nan, math.inf, -math.inf]:
            with self.subTest(value=value):
                self.assertIsNone(safe_float(value))

    def test_db_values_normalize_pandas_and_numpy_scalars(self):
        self.assertEqual(
            db_values([pd.NA, np.nan, np.float64(math.inf), np.int64(3)]),
            [None, None, None, 3],
        )

    def test_insert_sanitizes_all_columns_at_database_boundary(self):
        connection = CapturingConnection()

        insert_values(
            connection,
            {
                "game_id": "2026_01_AWY_HME",
                "challenger_coverage": np.nan,
                "challenger_model_margin": np.float64(math.inf),
            },
        )

        self.assertEqual(
            connection.params,
            ["2026_01_AWY_HME", None, None],
        )


if __name__ == "__main__":
    unittest.main()
