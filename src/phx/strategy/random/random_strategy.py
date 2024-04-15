import time
from datetime import datetime, timezone
from enum import Enum
from logging import Logger

import pandas as pd
import quickfix as fix

from phx.api import DependencyAction, PhxApi
from phx.fix.app import AppRunner
from phx.fix.utils import fix_message_string, flip_trading_dir
from phx.utils import TO_PIPS
from phx.utils.price_utils import price_round_down, price_round_up
from phx.utils.time import utcnow


class TradingMode(str, Enum):
    MARKET_ORDERS = "market_orders"
    PASSIVE_LIMIT_ORDERS = "aggressive_limit_orders"


def generic_callback(msg, logger):
    logger.info(f"Callback msg_type:{type(msg).__name__} {msg=}")


class RandomStrategy:
    def __init__(
            self,
            app_runner: AppRunner,
            config: dict,
            logger: Logger,
    ):
        self.logger = logger
        self.config = config
        self.exchange = self.config.get("exchange")
        self.trading_symbols = self.config.get("trading_symbols")
        callbacks = {
            "ExecReport": generic_callback,
            "OrderBookSnapshot": generic_callback,
            "OrderCancelReject": generic_callback,
            "OrderMassCancelReport": generic_callback,
            "PositionReports": generic_callback,
            "Reject": generic_callback,
            "SecurityReport": generic_callback,
            "Trades": generic_callback,
        }
        self.phx_api = PhxApi(
            app_runner=app_runner,
            config=config,
            exchange=self.exchange,
            mkt_symbols=self.trading_symbols,
            trading_symbols=self.trading_symbols,
            logger=self.logger,
            callbacks=callbacks,
        )

        # time settings
        self.start_time = utcnow()
        self.timeout = pd.Timedelta(config.get("timeout", "00:00:30"))
        self.last_trade_time = pd.Timestamp(0, tz="UTC")
        self.trade_interval = pd.Timedelta(config.get("trade_interval", "5s"))

        # order settings
        self.quantity = config["quantity"]
        self.trading_mode = TradingMode.PASSIVE_LIMIT_ORDERS
        self.aggressiveness_in_pips = 2
        self.current_trading_direction = fix.Side_BUY

    def get_symbols_to_trade(self):
        return list(self.trading_symbols)

    def check_if_completed(self):
        now = utcnow()
        end = self.start_time + self.timeout
        completed = (now >= end)
        self.logger.info(
            f"check_if_completed: {self.start_time=} "
            f"{end=} {now=} {completed=}"
        )
        return completed

    def is_ready_to_trade(self) -> bool:
        """
        Example of a function that checks that API received all data necessary to trade.

        Returns
        -------
        True if all data received and algo ready to trade,
        False otherwise
        """
        fn = self.is_ready_to_trade.__name__
        is_ready = True
        # check that per-symbol data (ob snapshot and working orders) is ready
        for symbol in self.trading_symbols:
            ticker = (self.exchange, symbol)
            for action in [DependencyAction.ORDERBOOK_SNAPSHOTS, DependencyAction.WORKING_ORDERS]:
                if ticker not in self.phx_api.dependency_actions.get(action):
                    is_ready = False
                    self.logger.info(
                        f"{fn} {ticker=} not in {action=} "
                        f"{self.phx_api.dependency_actions.get(action)}"
                    )
        # check that per-exchange data (securities and positions) is ready
        for action in [DependencyAction.SECURITY_REPORTS, DependencyAction.POSITION_SNAPSHOTS]:
            if self.exchange not in self.phx_api.dependency_actions.get(action):
                is_ready = False
                self.logger.info(
                    f"{fn} {self.exchange=} not in {action=} "
                    f"{self.phx_api.dependency_actions.get(action)}"
                )
        # Check rate limit
        if self.phx_api.rate_limiter.free_capacity(datetime.now(timezone.utc)) == 0:
            is_ready = False
            self.logger.info(
                f"{fn} {self.exchange=} no free rate limit capacity"
            )
        if is_ready:
            self.logger.info(
                f"{fn} {self.exchange=} {self.trading_symbols=} READY TO TRADE"
            )
        return is_ready

    def strategy_loop(self):
        fn = self.strategy_loop.__name__
        api_finished = False
        try:
            while not api_finished:
                if not self.phx_api.to_stop:
                    if self.is_ready_to_trade():
                        self.trade()
                    time_is_out = self.check_if_completed()
                    if time_is_out:
                        self.phx_api.to_stop = True
                else:
                    self.logger.info(f"{fn}: API Stopped. Waiting to be finished...")
                self.logger.info(f"{fn}: sleep for {self.trade_interval.total_seconds()} seconds")
                time.sleep(self.trade_interval.total_seconds())
                api_finished = (self.phx_api.is_finished())
                if api_finished:
                    self.logger.info(f"{fn}: API finished.")
        except Exception as e:
            self.logger.error(f"{fn}: Exception: {e}")
            self.phx_api.to_stop = True

    def get_trading_direction(self):
        direction = self.current_trading_direction
        self.current_trading_direction = flip_trading_dir(self.current_trading_direction)
        return direction

    def submit_market_orders(self):
        fn = self.submit_market_orders.__name__
        direction = self.get_trading_direction()
        symbols = self.get_symbols_to_trade()
        account = self.phx_api.fix_interface.get_account()
        start_time = datetime.now(timezone.utc)
        for symbol in symbols:
            ticker = (self.exchange, symbol)
            book = self.phx_api.order_books.get(ticker)
            if book and book.mid_price:
                sent_order = False
                while not sent_order:
                    if self.phx_api.rate_limiter.has_capacity(datetime.now(timezone.utc), 1):
                        self.phx_api.rate_limiter.consume(datetime.now(timezone.utc))
                        order, msg = self.phx_api.fix_interface.new_order_single(
                            self.exchange,
                            symbol,
                            direction,
                            self.quantity,
                            ord_type=fix.OrdType_MARKET,
                            account=account,
                        )
                        self.logger.info(
                            f"{fn}: {self.exchange=}/{symbol=}: MKT {direction}"
                            f" order submitted {fix_message_string(msg)}"
                        )
                        sent_order = True
                    else:
                        self.logger.info(f"{fn}: no rate limit capacity")
                        since_start = pd.Timedelta(datetime.now(timezone.utc) - start_time)
                        if since_start > self.trade_interval:
                            self.logger.info(f"{fn}: waited {since_start} since start. Abandon.")
                            return
                        else:
                            self.logger.info(f"{fn}: sleep for 1 second")
                            time.sleep(1)
            else:
                self.logger.info(f"{fn}: {self.exchange=}/{symbol=}: mid-price missing!")

    def submit_limit_orders(self):
        fn = self.submit_limit_orders.__name__
        direction = self.get_trading_direction()
        symbols = self.get_symbols_to_trade()
        account = self.phx_api.fix_interface.get_account()
        start_time = datetime.now(timezone.utc)
        for symbol in symbols:
            ticker = (self.exchange, symbol)
            book = self.phx_api.order_books.get(ticker, None)
            min_tick_size = self.phx_api.get_security_attribute(ticker, 'min_price_increment')
            if book and min_tick_size:
                top_bid = book.top_bid_price
                top_ask = book.top_ask_price
                if top_bid and top_ask:
                    if direction == fix.Side_SELL:
                        price = price_round_down(top_ask * (1 + TO_PIPS * self.aggressiveness_in_pips), min_tick_size)
                        dir_str = "sell"
                    else:
                        price = price_round_up(top_bid * (1 - TO_PIPS * self.aggressiveness_in_pips), min_tick_size)
                        dir_str = "buy"
                    self.logger.info(
                        f"{fn}: {self.exchange}/{symbol}: top of book {(top_bid, top_ask)} => "
                        f"passive {dir_str} order {self.quantity} @ {price}"
                    )
                    sent_order = False
                    while not sent_order:
                        if self.phx_api.rate_limiter.has_capacity(datetime.now(timezone.utc), 1):
                            self.phx_api.rate_limiter.consume(datetime.now(timezone.utc))
                            order, msg = self.phx_api.fix_interface.new_order_single(
                                self.exchange,
                                symbol,
                                direction,
                                self.quantity,
                                price,
                                ord_type=fix.OrdType_LIMIT,
                                account=account,
                            )
                            self.logger.info(
                                f"{fn}: {self.exchange}/{symbol}: passive {dir_str} "
                                f" order submitted:{fix_message_string(msg)}"
                            )
                            sent_order = True
                        else:
                            self.logger.info(f"{fn}: no rate limit capacity")
                            since_start = pd.Timedelta(datetime.now(timezone.utc) - start_time)
                            if since_start > self.trade_interval:
                                self.logger.info(f"{fn}: waited {since_start} since start. Abandon.")
                                return
                            else:
                                self.logger.info(f"{fn}: sleep for 1 second")
                                time.sleep(1)
                else:
                    self.logger.info(
                        f"{fn}: order book for {self.exchange=}/{symbol=} {top_bid=} {top_ask=}"
                    )
            else:
                self.logger.warning(
                    f"{fn}: empty either order book for {self.exchange=}/{symbol=} or {min_tick_size=}"
                )

    def trade(self):
        now = pd.Timestamp.utcnow()
        if now > self.last_trade_time + self.trade_interval:
            self.logger.info(f"====> run trading step {now}")
            self.last_trade_time = now
            if self.trading_mode == TradingMode.MARKET_ORDERS:
                self.submit_market_orders()
                self.trading_mode = TradingMode.PASSIVE_LIMIT_ORDERS
            elif self.trading_mode == TradingMode.PASSIVE_LIMIT_ORDERS:
                self.submit_limit_orders()
                self.trading_mode = TradingMode.MARKET_ORDERS
