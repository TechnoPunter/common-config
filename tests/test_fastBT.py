from tests.Utils import *
from commons.backtest.fastBT import FastBT
from commons.loggers.setup_logger import setup_logging


class TestFastBT(unittest.TestCase):
    fb = FastBT()
    scrip = "NSE_ACME"
    strategy = "TEST.ME"
    count = 100

    @staticmethod
    def __format_expected_df(df) -> pd.DataFrame:
        output_df = df.copy()
        return output_df.astype(object)

    def test_get_accuracy(self):
        """

        Scenarios:
        Group 1 : Invalid
        1.1. Invalid Entry; Long
        1.2. Invalid Entry; Short
        Group 2 : Valid - Long - Target
        2.1. Valid Entry; Long; Target Hit in > 1st Candle
        2.2. Valid Entry; Long; Target Hit in 1st Candle
        Group 3 : Valid - Short - Target
        3.1. Valid Entry; Short; Target Hit in > 1st Candle
        3.2. Valid Entry; Short; Target Hit in 1st Candle
        Group 4 : Valid - Long - SL
        4.1. Valid Entry; Long; SL Hit in > 1st Candle
        4.2. Valid Entry; Long; SL Hit in 1st Candle
        Group 5 : Valid - Short - SL
        5.1. Valid Entry; Short; SL Hit in > 1st Candle
        5.2. Valid Entry; Short; SL Hit in 1st Candle
        Group 6 : Valid - Long - Mixed
        6.1. Valid Entry; Long; Target + SL Hit in > 1st Candle
        6.2. Valid Entry; Long; Target + SL Hit in 1st Candle
        6.3. Valid Entry; Long; Target Before SL Hit in > 1st Candle
        Group 7 : Valid - Short - Mixed
        7.1. Valid Entry; Short; SL Hit in > 1st Candle
        7.2. Valid Entry; Short; SL Hit in 1st Candle
        7.3. Valid Entry; Short; Target Before SL Hit in > 1st Candle
        Group 8 : Valid - Long - Flat
        8.1. Valid Entry; Long; Flat with Profit
        8.2. Valid Entry; Long; Flat with Loss
        Group 9 : Valid - Short - Flat
        9.1. Valid Entry; Short; Flat with Profit
        9.2. Valid Entry; Short; Flat with Loss
        Group 10: Valid - Long - SL Update
        10.1. Valid Entry; Long; 0 SL Updates
        10.2. Valid Entry; Long; >0 SL Updates
        Group 11: Valid - Long - SL Update
        11.1. Valid Entry; Short; 0 SL Updates
        11.2. Valid Entry; Short; >0 SL Updates
        """
        merged_df = read_file_df("fastBT/merged_df.csv")
        expected_df = read_file_df("fastBT/expected_trade_df.csv")
        param = {"scrip": self.scrip, "strategy": self.strategy, "merged_df": merged_df, "count": self.count}
        key, trades, stat, mtm_df = self.fb.get_accuracy(param)
        pd.testing.assert_frame_equal(self.__format_expected_df(expected_df), trades)

    def test_prep_data(self):
        expected_df = read_file_df("fastBT/expected_trade_df.csv")
        expected_stats = read_file("fastBT/expected_stats.json")

        ret_val = self.fb.calc_stats(final_df=expected_df, scrip=self.scrip, strategy=self.strategy)
        self.assertEqual(ret_val, expected_stats)

    def test_calc_stats(self):
        assert True


if __name__ == "__main__":
    setup_logging("test_fastBT.log")
    unittest.main()
