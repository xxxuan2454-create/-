"""Unit tests for US market support (Plan A)."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from data.markets import (
    MARKET_CN,
    MARKET_US,
    currency_symbol,
    detect_market,
    is_cn_market,
    is_us_market,
    market_label,
    normalize_us_ticker,
)


class TestMarkets(unittest.TestCase):
    def test_detect_cn_codes(self):
        self.assertEqual(detect_market("600519.SS"), MARKET_CN)
        self.assertEqual(detect_market("000858.SZ"), MARKET_CN)
        self.assertEqual(detect_market("430047.BJ"), MARKET_CN)

    def test_detect_us_codes(self):
        self.assertEqual(detect_market("AAPL"), MARKET_US)
        self.assertEqual(detect_market("BRK-B"), MARKET_US)
        self.assertEqual(detect_market("spy"), MARKET_US)

    def test_normalize_us_ticker(self):
        self.assertEqual(normalize_us_ticker(" aapl "), "AAPL")

    def test_currency_symbol(self):
        self.assertEqual(currency_symbol(MARKET_CN), "¥")
        self.assertEqual(currency_symbol(MARKET_US), "$")
        self.assertEqual(currency_symbol(code="600519.SS"), "¥")
        self.assertEqual(currency_symbol(code="MSFT"), "$")

    def test_market_helpers(self):
        self.assertTrue(is_cn_market("600519.SS"))
        self.assertFalse(is_cn_market("NVDA"))
        self.assertTrue(is_us_market("NVDA"))
        self.assertEqual(market_label(MARKET_US), "美股")


class TestStockList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"

        import config
        self._orig_db = config.DB_PATH
        config.DB_PATH = self.db_path

        import db.models as models
        self._orig_get_conn = models.get_connection

        def _test_conn():
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn

        models.get_connection = _test_conn

        import importlib
        import data.stock_list as stock_list

        self.stock_list = importlib.reload(stock_list)

        self.cn_csv = Path(self.tmp.name) / "cn.csv"
        self.us_csv = Path(self.tmp.name) / "us.csv"
        self.cn_csv.write_text(
            "code,name,exchange\n600519.SS,贵州茅台,SSE\n",
            encoding="utf-8",
        )
        self.us_csv.write_text(
            "code,name,exchange\nAAPL,Apple Inc,NASDAQ\nMSFT,Microsoft Corporation,NASDAQ\n",
            encoding="utf-8",
        )
        self.stock_list._CN_CSV = self.cn_csv
        self.stock_list._US_CSV = self.us_csv

    def tearDown(self):
        import config
        import db.models as models

        config.DB_PATH = self._orig_db
        models.get_connection = self._orig_get_conn
        self.tmp.cleanup()

    def test_sync_and_search_by_market(self):
        total = self.stock_list.sync_full_stock_list()
        self.assertEqual(total, 3)
        self.assertEqual(self.stock_list.get_stock_count(MARKET_CN), 1)
        self.assertEqual(self.stock_list.get_stock_count(MARKET_US), 2)

        cn_hits = self.stock_list.search_all_stocks("茅台", market=MARKET_CN)
        self.assertEqual(len(cn_hits), 1)
        self.assertEqual(cn_hits[0]["code"], "600519.SS")

        us_hits = self.stock_list.search_all_stocks("Apple", market=MARKET_US)
        self.assertEqual(len(us_hits), 1)
        self.assertEqual(us_hits[0]["code"], "AAPL")

        cross = self.stock_list.search_all_stocks("Apple", market=MARKET_CN)
        self.assertEqual(cross, [])


class TestFetcher(unittest.TestCase):
    @unittest.skipUnless(HAS_PANDAS, "pandas not installed")
    def test_us_skips_akshare(self):
        from data import fetcher

        with patch.object(fetcher, "fetch_stock_history_ak") as mock_ak:
            mock_ak.return_value = pd.DataFrame()
            with patch.object(fetcher, "_read_cache", return_value=None):
                with patch.object(fetcher, "_with_timeout") as mock_timeout:
                    idx = pd.date_range("2024-01-01", periods=3, freq="D")
                    df = pd.DataFrame(
                        {
                            "open": [1.0, 2.0, 3.0],
                            "high": [1.1, 2.1, 3.1],
                            "low": [0.9, 1.9, 2.9],
                            "close": [1.0, 2.0, 3.0],
                            "volume": [100, 200, 300],
                        },
                        index=idx,
                    )
                    mock_timeout.return_value = df
                    with patch.object(fetcher, "_write_cache"):
                        result = fetcher.fetch_stock_history("AAPL", period="1mo")
        mock_ak.assert_not_called()
        self.assertFalse(result.empty)
        self.assertIn("close", result.columns)

    @unittest.skipUnless(HAS_PANDAS, "pandas not installed")
    def test_cache_restore_sets_date_index(self):
        from data import fetcher

        cache = {
            "data": [
                {
                    "date": "2024-01-01",
                    "open": 1.0,
                    "high": 1.1,
                    "low": 0.9,
                    "close": 1.0,
                    "volume": 100,
                },
                {
                    "date": "2024-01-02",
                    "open": 2.0,
                    "high": 2.1,
                    "low": 1.9,
                    "close": 2.0,
                    "volume": 200,
                },
            ]
        }
        df = fetcher._dataframe_from_cache(cache)
        self.assertIsInstance(df.index, pd.DatetimeIndex)
        self.assertEqual(len(df), 2)


class TestRealtime(unittest.TestCase):
    def test_get_realtime_routes_us_to_yfinance(self):
        from data import realtime

        with patch.object(realtime, "fetch_realtime_tencent", return_value={}) as mock_tc:
            with patch.object(
                realtime,
                "fetch_realtime_yfinance",
                return_value={"AAPL": {"current_price": 150.0}},
            ) as mock_yf:
                out = realtime.get_realtime_quotes(["AAPL"])
        mock_tc.assert_not_called()
        mock_yf.assert_called_once_with(["AAPL"])
        self.assertIn("AAPL", out)


if __name__ == "__main__":
    unittest.main()
