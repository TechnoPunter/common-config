import logging
from multiprocessing import Pool

import pandas as pd

from commons.config.reader import cfg
from commons.consts.consts import *
from commons.dataprovider.ScripData import ScripData
from commons.dataprovider.database import DatabaseEngine
from commons.utils.Misc import get_bod_epoch, get_updated_sl

MODEL_PREFIX = 'trainer.strategies.'
FINAL_DF_COLS = [
    'scrip', 'strategy', 'tick', 'date', 'signal', 'target', 'bod_sl', 'sl_range', 'trail_sl', 'strength',
    'entry_time', 'entry_price', 'status',
    'exit_price', 'exit_time',
    'pnl', 'sl', 'sl_update_cnt', 'max_mtm', 'max_mtm_pct',
]
MTM_DF_COLS = [
    'scrip', 'strategy', 'date', 'datetime', 'signal', 'time', 'open', 'high', 'low', 'close',
    'target', 'target_met', 'entry_price', 'mtm', 'mtm_pct'
]
logger = logging.getLogger(__name__)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', None)
pd.options.mode.chained_assignment = None

MODE = "SERVER"


def get_pnl(row):
    if row.signal == 1:
        return row.exit_price - row.entry_price
    else:
        return row.entry_price - row.exit_price


def get_strength(row):
    if row.signal == 1:
        return row.target - row.entry_price
    else:
        return row.entry_price - row.target


def is_valid(row):
    if pd.isnull(row['signal']):
        return float('nan')
    elif (row['signal'] == 1 and row['target'] > row['open']) or \
            (row['signal'] == -1 and row['target'] < row['open']):
        return True
    else:
        return False


def target_met(row):
    if (row['curr_signal'] == 1 and row['curr_target'] <= row['high']) or \
            (row['curr_signal'] == -1 and row['curr_target'] >= row['low']):
        return True
    else:
        return False


def sl_hit(row):
    if (row['curr_signal'] == 1 and row['curr_sl'] >= row['low']) or \
            (row['curr_signal'] == -1 and row['curr_sl'] <= row['high']):
        return True
    else:
        return False


def calc_mtm(row, low=None, high=None):
    if row['signal'] == 1:
        mtm = high - row['entry_price']
        mtm_pct = mtm * 100 / row['entry_price']
        return round(mtm, 2), round(mtm_pct, 2)
    elif row['signal'] == -1:
        mtm = row['entry_price'] - low
        mtm_pct = mtm * 100 / row['entry_price']
        return round(mtm, 2), round(mtm_pct, 2)
    else:
        return 0.0, 0.0


def calc_mtm_df(row):
    low = row['low']
    high = row['high']
    if row.get('curr_signal') == 1:
        mtm = high - row['entry_price']
        mtm_pct = mtm * 100 / row['entry_price']
        return round(mtm, 2), round(mtm_pct, 2)
    elif row.get('curr_signal') == -1:
        mtm = row['entry_price'] - low
        mtm_pct = mtm * 100 / row['entry_price']
        return round(mtm, 2), round(mtm_pct, 2)
    else:
        return 0.0, 0.0


class FastBT:

    def __init__(self):
        self.mode = "BACKTEST"  # "NEXT-CLOSE"

    def prep_data(self, scrip, strategy, raw_pred_df: pd.DataFrame, sd: ScripData):
        logger.info(f"Entering Prep data for {scrip} with {len(raw_pred_df)} predictions")

        if len(raw_pred_df) > 1:
            # This would be a backtest prediction file
            raw_pred_df = raw_pred_df[['target', 'signal', 'time']]
            raw_pred_df['time'] = raw_pred_df['time'].shift(-1)
        else:
            # This would be Next Close file
            pass

        raw_pred_df['date'] = pd.to_datetime(raw_pred_df['time'], unit='s', utc=True)
        raw_pred_df['date'] = raw_pred_df['date'].dt.tz_convert(IST)
        raw_pred_df['date'] = raw_pred_df['date'].dt.date
        # Remove last row after offset of time
        raw_pred_df.dropna(subset=['date'], inplace=True)

        # Get 1-Min data (tick data) and join with raw_pred_df
        start_date = raw_pred_df.date.min()
        tick_data = sd.get_tick_data(scrip, from_date=start_date)
        merged_df = pd.merge(tick_data, raw_pred_df, how='left', left_on='time', right_on='time')
        merged_df['datetime'] = pd.to_datetime(merged_df['time'], unit='s', utc=True)
        merged_df['datetime'] = merged_df['datetime'].dt.tz_convert(IST)
        merged_df['date'] = merged_df['datetime'].dt.date
        merged_df.loc[merged_df.groupby(merged_df.date).apply(lambda x: x.index[-1]), 'cob_row'] = 1.0
        merged_df['cob_row'] = merged_df['cob_row'].fillna(0.0)
        # merged_df.set_index('datetime', inplace=True)

        # Get the Daily data (base data) and join with merged DF this is to get the closing price for the day
        if self.mode == "BACKTEST":
            base_data = sd.get_base_data(scrip, from_date=start_date)
        else:
            # Last candle of the day is closing price for the day! However, time of day is 1st candle's epoch
            base_data = tick_data.iloc[-1:]
            base_data.loc[:, 'time'] = tick_data.iloc[0]['time']
        base_data = base_data[['time', 'close']]
        base_data.rename(columns={"close": "day_close"}, inplace=True)
        merged_df = pd.merge(merged_df, base_data, how='left', left_on='time', right_on='time')
        if self.mode == "BACKTEST":
            # Remove 1st Row since we don't have closing from T-1
            merged_df = merged_df.iloc[1:]
        return merged_df

    @staticmethod
    def calc_stats(final_df, scrip, strategy):

        l_trades = 0
        l_pct_success = 0
        l_valid_count = 0
        l_entry_pct = 0.0
        l_pnl = 0
        l_avg_cost = 0.01
        s_trades = 0
        s_pct_success = 0
        s_valid_count = 0
        s_entry_pct = 0.0
        s_pnl = 0
        s_avg_cost = 0.01
        count = len(final_df)
        if len(final_df) > 0:
            l_trades = final_df.loc[final_df.signal == 1]
            if len(l_trades) > 0:
                l_count = len(l_trades)
                l_valid_count = len(l_trades.loc[l_trades.status != 'INVALID'])
                l_entry_pct = (l_valid_count / l_count) * 100
                l_entry_pct = round(l_entry_pct, 2)
                l_success = l_trades.loc[l_trades.status == 'TARGET-HIT']
                l_pct_success = (len(l_success) / l_valid_count) * 100
                l_pct_success = round(l_pct_success, 2)
                l_avg_cost = l_trades['entry_price'].mean()
                l_pnl = l_trades['pnl'].sum()

            s_trades = final_df.loc[final_df.signal == -1]
            if len(s_trades) > 0:
                s_count = len(s_trades)
                s_valid_count = len(s_trades.loc[s_trades.status != 'INVALID'])
                s_entry_pct = (s_valid_count / s_count) * 100
                s_entry_pct = round(s_entry_pct, 2)
                s_success = s_trades.loc[s_trades.status == 'TARGET-HIT']
                s_pct_success = (len(s_success) / s_valid_count) * 100
                s_pct_success = round(s_pct_success, 2)
                s_avg_cost = s_trades['entry_price'].mean()
                s_pnl = s_trades['pnl'].sum()
        return {
            "scrip": scrip, "strategy": MODEL_PREFIX + strategy,
            "trades": count, "entry_pct": (l_valid_count + s_valid_count) * 100 / count,
            "l_trades": len(l_trades), "l_pct_success": l_pct_success, "l_pnl": l_pnl, "l_avg_cost": l_avg_cost,
            "l_pct": l_pnl * 100 / l_avg_cost, "l_entry_pct": l_entry_pct,
            "s_trades": len(s_trades), "s_pct_success": s_pct_success, "s_pnl": s_pnl, "s_avg_cost": s_avg_cost,
            "s_pct": s_pnl * 100 / s_avg_cost, "s_entry_pct": s_entry_pct
        }

    def get_accuracy(self, accu_params):
        scrip = accu_params.get('scrip')
        strategy = accu_params.get('strategy')
        merged_df = accu_params.get('merged_df')
        # TODO: Logging
        logger.info(f"Starting get_accuracy for: {scrip} & {strategy}")
        print(f"Starting get_accuracy for: {scrip} & {strategy}")

        # Is the target still available at open i.e. 9:15 candle? If so mark full day as is_valid.
        # Remove rows which couldn't be evaluated
        merged_df['is_valid'] = merged_df.apply(is_valid, axis=1)

        # If Yes - use that as entry price for the entire day
        merged_df['entry_price'] = merged_df['open'][merged_df['is_valid'] == True]

        # Fill the data for the day
        merged_df['is_valid'] = merged_df['is_valid'].ffill()
        merged_df.dropna(subset=['is_valid'], inplace=True)
        merged_df['entry_price'] = merged_df['entry_price'].ffill()
        merged_df['curr_signal'] = merged_df['signal'].ffill()
        merged_df['day_close'] = merged_df['day_close'].ffill()
        merged_df['curr_target'] = merged_df['target'].ffill()
        merged_df['bod_sl'] = merged_df['sl'].ffill()
        merged_df['curr_trail_sl'] = merged_df['trail_sl'].ffill()

        # Check for signals & events i.e.
        # Target Met - 1st row
        # SL Hit
        # Max Profit : MTM + Max;
        # Max Loss
        trades = pd.DataFrame(columns=FINAL_DF_COLS)
        mtm_df = merged_df.copy()
        # MTM_DF_COLS = [
        #     'mtm', 'mtm_pct'
        # ]
        mtm_df = mtm_df.assign(scrip=scrip, strategy=strategy)
        mtm_df['target_met'] = mtm_df.apply(target_met, axis=1)
        mtm_df[['mtm', 'mtm_pct']] = mtm_df.apply(calc_mtm_df, axis=1, result_type='expand')
        mtm_df.reset_index(inplace=True)

        trade_idx = -1
        for idx, rec in merged_df.iterrows():
            if not (pd.isna(rec.signal)):
                # Open a position
                trade_idx += 1
                trades.loc[trade_idx, 'scrip'] = scrip
                trades.loc[trade_idx, 'strategy'] = strategy
                trades.loc[trade_idx, 'tick'] = 0.05
                trades.loc[trade_idx, 'date'] = rec.date
                trades.loc[trade_idx, 'signal'] = rec.signal
                trades.loc[trade_idx, 'target'] = rec.target
                trades.loc[trade_idx, 'bod_sl'] = rec.bod_sl
                trades.loc[trade_idx, 'sl'] = rec.bod_sl
                trades.loc[trade_idx, 'sl_range'] = abs(rec.bod_sl - rec.open)
                trades.loc[trade_idx, 'trail_sl'] = rec.trail_sl
                trades.loc[trade_idx, 'entry_price'] = rec.open
                trades.loc[trade_idx, 'entry_time'] = rec.time
                trades.loc[trade_idx, 'strength'] = get_strength(trades.iloc[trade_idx])
                trades.loc[trade_idx, 'sl_update_cnt'] = 0
                trades.loc[trade_idx, 'max_mtm'] = 0.0
                trades.loc[trade_idx, 'max_mtm_pct'] = 0.0
                if rec.is_valid:
                    trades.loc[trade_idx, 'status'] = 'OPEN'
                else:
                    trades.loc[trade_idx, 'status'] = 'INVALID'
            # Housekeeping
            if trades.iloc[trade_idx]['status'] == 'OPEN':

                rec['curr_sl'] = trades.iloc[trade_idx]['sl']
                if sl_hit(rec):
                    trades.loc[trade_idx, 'status'] = 'SL-HIT'
                    trades.loc[trade_idx, 'exit_price'] = trades.iloc[trade_idx]['sl']
                    trades.loc[trade_idx, 'exit_time'] = rec.time
                    trades.loc[trade_idx, 'pnl'] = get_pnl(trades.loc[trade_idx])
                elif target_met(rec):
                    trades.loc[trade_idx, 'status'] = 'TARGET-HIT'
                    trades.loc[trade_idx, 'exit_price'] = rec.curr_target
                    trades.loc[trade_idx, 'exit_time'] = rec.time
                    trades.loc[trade_idx, 'pnl'] = get_pnl(trades.loc[trade_idx])

            if trades.iloc[trade_idx]['status'] == 'OPEN':
                # Still open i.e. Not SL or Target Hit
                new_sl = float(get_updated_sl(trades.iloc[trade_idx], rec.low, rec.high))
                logger.debug(f"New SL {new_sl} for rec: {rec} and trades:\n{trades}")
                if new_sl != 0.0:
                    trades.loc[trade_idx, 'sl_update_cnt'] += 1
                    trades.loc[trade_idx, 'sl'] = new_sl

            mtm, mtm_pct = calc_mtm(trades.loc[trade_idx], rec.low, rec.high)
            if mtm > trades.loc[trade_idx, 'max_mtm']:
                trades.loc[trade_idx, 'max_mtm'] = mtm
                trades.loc[trade_idx, 'max_mtm_pct'] = mtm_pct

            if trades.iloc[trade_idx]['status'] == 'OPEN' and rec.cob_row == 1.0:
                trades.loc[trade_idx, 'status'] = 'COB-CLOSE'
                trades.loc[trade_idx, 'exit_price'] = rec.close
                trades.loc[trade_idx, 'exit_time'] = rec.time
                trades.loc[trade_idx, 'pnl'] = get_pnl(trades.loc[trade_idx])

        stats = self.calc_stats(trades, scrip, strategy)
        logger.info(f"Evaluated: {scrip} & {strategy} with {len(trades)} trades")
        print(f"Evaluated: {scrip} & {strategy} with {len(trades)} trades")
        return f"{scrip}:{strategy}", trades, stats, mtm_df[MTM_DF_COLS]

    def run_accuracy(self, params: list[dict]):
        logger.info(f"run_accuracy: Started with {len(params)} scrips")
        self.mode = "BACKTEST"
        sd = ScripData()

        if len(params) == 0:
            logger.error(f"Unable to proceed since Params is empty")
            return
        trades = []
        stats = []
        mtm = {}
        accuracy_params = []
        for param in params:
            strategy = param.get('strategy')
            scrip = param.get('scrip')
            raw_pred_df = param.get('raw_pred_df')
            logger.info(f"Getting dict based results for {scrip} & {strategy}")
            merged_df = self.prep_data(scrip, strategy, raw_pred_df=raw_pred_df, sd=sd)
            accuracy_params.append({"scrip": scrip, "strategy": strategy, "merged_df": merged_df})
        if MODE == "SERVER":
            try:
                logger.info(f"About to start accuracy calc with {len(accuracy_params)} objects")
                pool = Pool()
                result_set = pool.imap(self.get_accuracy, accuracy_params)
                for key, trade, stat, mtm_df in result_set:
                    trades.append(trade)
                    stats.append(stat)
                    mtm[key] = mtm_df
            except Exception as ex:
                logger.error(f"Error in Multi Processing {ex}")
        else:
            for param in accuracy_params:
                key, trade, stat, mtm_df = self.get_accuracy(param)
                trades.append(trade)
                stats.append(stat)
                mtm[key] = mtm_df
        result_trades = pd.concat(trades)
        result_trades.sort_values(by=['date', 'scrip'], inplace=True)
        result_stats = pd.DataFrame(stats)
        return result_trades, result_stats, mtm

    def run_cob_accuracy(self, params: pd.DataFrame):
        logger.info(f"run_accuracy: Started with {len(params)} scrips")
        self.mode = "NEXT-CLOSE"
        sd = ScripData()
        if len(params) == 0:
            logger.error(f"Unable to proceed since Params is empty")
            return
        trades = []
        stats = []
        mtm = {}
        accuracy_params = []
        valid_trades = params.loc[params.entry_order_status == 'ENTERED']
        logger.info(f"No. of valid trades: {len(valid_trades)}")
        for param in valid_trades.iterrows():
            _, rec = param
            df = pd.DataFrame([rec])
            strategy = rec.get('model')
            scrip = rec.get('scrip')
            logger.info(f"Getting DF based results for {scrip} & {strategy}")
            trade_date = datetime.datetime.fromtimestamp(int(rec.get('entry_ts')))
            trade_time = get_bod_epoch(trade_date.strftime('%Y-%m-%d'))
            df.loc[:, 'time'] = trade_time
            merged_df = self.prep_data(scrip, strategy, raw_pred_df=df[['target', 'signal', 'time']], sd=sd)
            accuracy_params.append({"scrip": scrip, "strategy": strategy, "merged_df": merged_df})
        if MODE == "SERVER":
            try:
                pool = Pool()
                result_set = pool.imap(self.get_accuracy, accuracy_params)
                for key, trade, stat, mtm_df in result_set:
                    trades.append(trade)
                    stats.append(stat)
                    mtm[key] = mtm_df
            except Exception as ex:
                logger.error(f"Error in Multi Processing {ex}")
        else:
            for param in accuracy_params:
                key, trade, stat, mtm_df = self.get_accuracy(param)
                trades.append(trade)
                stats.append(stat)
                mtm[key] = mtm_df
        if len(trades) > 0:
            result_trades = pd.concat(trades)
            result_trades.sort_values(by=['date', 'scrip'], inplace=True)
            result_stats = pd.DataFrame(stats)
            result_stats.dropna(subset=['scrip'], inplace=True)
        else:
            result_trades = pd.DataFrame()
            result_stats = pd.DataFrame()
        return result_trades, result_stats, mtm


if __name__ == '__main__':
    from commons.loggers.setup_logger import setup_logging

    setup_logging("fastBT.log")

    MODE = "LOCAL"
    f = FastBT()
    params_ = []
    for scrip_ in cfg['steps']['scrips']:
        for strategy_ in cfg['steps']['strats']:
            file = os.path.join(cfg['generated'], scrip_, f'trainer.strategies.{strategy_}.{scrip_}_Raw_Pred.csv')
            raw_pred_df_ = pd.read_csv(file)
            params_.append({"scrip": scrip_, "strategy": strategy_, "raw_pred_df": raw_pred_df_})

    bt_trades, bt_stats, bt_mtm = f.run_accuracy(params_)
    logger.info(f"bt_trades#: {len(bt_trades)}")
    logger.debug(f"bt_trades:\n{bt_trades}")
    logger.info(f"bt_stats#:{len(bt_stats)}")
    logger.debug(f"bt_stats:\n{bt_stats}")
    logger.info(f"bt_mtm#: {len(bt_mtm)}")

    # exit

    from commons.service.LogService import LogService

    acct = 'Trader-V2-Pralhad'
    dt_ = '2023-12-01'
    db = DatabaseEngine()
    ls = LogService(db)
    data = ls.get_log_entry_data(log_type=PARAMS_LOG_TYPE, keys=["COB"], log_date=dt_, acct=acct)
    bt_trades, bt_stats, bt_mtm = f.run_cob_accuracy(params=pd.DataFrame(data))
    logger.info(f"bt_trades#: {len(bt_trades)}")
    logger.debug(f"bt_trades:\n{bt_trades}")
    logger.info(f"bt_stats#:{len(bt_stats)}")
    logger.debug(f"bt_stats:\n{bt_stats}")
    logger.info(f"bt_mtm#: {len(bt_mtm)}")
