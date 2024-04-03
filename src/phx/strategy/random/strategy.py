from enum import Enum
from logging import Logger
from typing import Tuple, Optional, Set

import pandas as pd
import quickfix as fix
from phx.fix.app import AppRunner
from phx.fix.utils import fix_message_string, flip_trading_dir
from phx.utils import TO_PIPS
from scipy.stats import bernoulli

from phx.strategy.base import StrategyBase, RoundingDirection
from phx.strategy.base.types import Ticker


class SymbolSelection(str, Enum):
    ALL_AT_ONCE = "all_at_once"
    ONE_BY_ONE = "one_by_one"


class TradingDirection(str, Enum):
    RANDOM = "random"
    ALTERNATE = "alternate"


class TradingMode(str, Enum):
    MARKET_ORDERS = "market_orders"
    AGGRESSIVE_LIMIT_ORDERS = "aggressive_limit_orders"


class InitialTradingDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"


class RandomStrategy(StrategyBase):
    def __init__(
            self,
            app_runner: AppRunner,
            config: dict,
            logger: Logger = None,
    ):
        trading_symbols: Set[Tuple[str, str]] = {tuple(ts) for ts in config["trading_symbols"]}

        super().__init__(
            app_runner,
            config,
            trading_symbols,
            trading_symbols,
            logger,
        )

        self.min_tick_size = config.get("min_tick_size", 0.1)
        self.quantity = config["quantity"]
        self.delay = pd.Timedelta(config.get("delay", "5s"))
        self.symbol_selection = SymbolSelection(config["symbol_selection"])
        self.trading_direction = TradingDirection(config["trading_direction"])
        self.initial_trading_direction = InitialTradingDirection(config["initial_trading_direction"])
        self.trading_mode = TradingMode(config["trading_mode"])
        self.aggressiveness_in_pips = config["aggressiveness_in_pips"]
        self.symbol_index = 0
        self.current_trading_direction = fix.Side_BUY \
            if self.initial_trading_direction == InitialTradingDirection.BUY else fix.Side_SELL
        self.last_trade_time = pd.Timestamp(0, tz="UTC")

    def round_down(self, price: float, key: Ticker) -> Optional[float]:
        return self.round(price, RoundingDirection.DOWN, key, self.min_tick_size)

    def round_up(self, price: float, key: Ticker) -> Optional[float]:
        return self.round(price, RoundingDirection.UP, key, self.min_tick_size)

    def get_symbols_to_trade(self):
        if self.symbol_selection == SymbolSelection.ALL_AT_ONCE:
            return self.trading_symbols
        else:
            symbols = list(self.trading_symbols)
            to_trade = [symbols[self.symbol_index]]
            self.symbol_index = (self.symbol_index + 1) % len(symbols)
            return to_trade

    def get_trading_direction(self):
        if self.trading_direction == TradingDirection.RANDOM:
            return fix.Side_BUY if bernoulli.rvs(p=0.5) == 1 else fix.Side_SELL
        else:
            direction = self.current_trading_direction
            self.current_trading_direction = flip_trading_dir(self.current_trading_direction)
            return direction

    def submit_market_orders(self):
        direction = self.get_trading_direction()
        symbols = self.get_symbols_to_trade()
        account = self.fix_interface.get_account()
        for exchange, symbol in symbols:
            key = exchange, symbol
            book = self.order_books.get(key, None)
            if book is not None and book.mid_price is not None:
                if direction == fix.Side_SELL:
                    dir_str = "sell"
                else:
                    dir_str = "buy"
                order, msg = self.fix_interface.new_order_single(
                    exchange, symbol, direction, self.quantity, ord_type=fix.OrdType_MARKET, account=account
                )
                self.logger.info(
                    f"{exchange} Symbol {symbol}: market {dir_str} submitted {fix_message_string(msg)}"
                )
            else:
                self.logger.info(f"{exchange} Symbol {symbol}: top of book empty!")

    def submit_limit_orders(self):
        direction = self.get_trading_direction()
        symbols = self.get_symbols_to_trade()
        account = self.fix_interface.get_account()
        for exchange, symbol in symbols:
            key = exchange, symbol
            book = self.order_books.get(key, None)
            if book is not None:
                top_bid = book.top_bid_price
                top_ask = book.top_ask_price
                if top_bid is not None and top_ask is not None:
                    if direction == fix.Side_SELL:
                        price = self.round_down(top_bid * (1 - TO_PIPS * self.aggressiveness_in_pips), key)
                        dir_str = "sell"
                    else:
                        price = self.round_up(top_ask * (1 + TO_PIPS * self.aggressiveness_in_pips), key)
                        dir_str = "buy"
                    self.logger.info(
                        f"{exchange} Symbol {symbol}: top of book {(top_bid, top_ask)} => "
                        f"aggressive {dir_str} {self.quantity} with limit price {price}"
                    )
                    order, msg = self.fix_interface.new_order_single(
                        exchange, symbol, direction, self.quantity, price, ord_type=fix.OrdType_LIMIT, account=account
                    )
                    self.logger.info(
                        f"{exchange} Symbol {symbol}: aggressive {dir_str} submitted {fix_message_string(msg)}"
                    )
                else:
                    self.logger.info(f"order book for {exchange} {symbol} one-sided or empty!")
            else:
                self.logger.info(f"no order book for {exchange} {symbol}")

    def trade(self):
        now = pd.Timestamp.utcnow()
        if now > self.last_trade_time + self.delay:
            self.logger.info(f"====> run trading step {now}")
            self.last_trade_time = now
            if self.trading_mode == TradingMode.MARKET_ORDERS:
                self.submit_market_orders()
            elif self.trading_mode == TradingMode.AGGRESSIVE_LIMIT_ORDERS:
                self.submit_limit_orders()
