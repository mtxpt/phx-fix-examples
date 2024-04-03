import abc
import math
import queue
from logging import Logger
from typing import List, Set, Dict, Tuple, Union, Optional

import pandas as pd
import quickfix as fix
from phx.fix.app.interface import FixInterface
from phx.fix.app.app_runner import AppRunner
from phx.fix.model import ExecReport, PositionReports, Security, SecurityReport, TradeCaptureReport
from phx.fix.model import GatewayNotReady, Reject, BusinessMessageReject, MarketDataRequestReject
from phx.fix.model import Logon, Create, Logout, Heartbeat
from phx.fix.model import Order, OrderBookSnapshot, OrderBookUpdate, Trades
from phx.fix.model import OrderMassCancelReport, MassStatusExecReport, MassStatusExecReportNoOrders
from phx.fix.model import PositionRequestAck, TradeCaptureReportRequestAck
from phx.fix.model.order_book import OrderBook
from phx.fix.tracker import OrderTracker, PositionTracker
from phx.fix.utils import fix_message_string
from phx.utils.thread import AlignedRepeatingTimer
from phx.utils import CHECK_MARK, CROSS_MARK

from phx.strategy.base import StrategyInterface, StrategyExecState, Ticker, RoundingDirection


def single_task(key, target_dict, current_dict, pre="  ") -> List[str]:
    rows = []
    if key in target_dict.keys():
        if key in current_dict.keys():
            rows.append(f"{pre}{CROSS_MARK} {key}")
        else:
            rows.append(f"{pre}{CHECK_MARK} {key} ")
    return rows


def set_task(key, target_dict, current_dict, pre="  ") -> List[str]:
    rows = []
    target_set = target_dict.get(key, None)
    if target_set is not None:
        remaining_set = current_dict.get(key, {})
        for task in target_set:
            mark = CROSS_MARK if task in remaining_set else CHECK_MARK
            rows.append(f"{pre}{mark} {key}[{task}]")
    return rows


class StrategyBase(StrategyInterface, abc.ABC):

    ORDERBOOK_SNAPSHOTS = "orderbook_snapshots"
    POSITION_SNAPSHOTS = "position_snapshots"
    WORKING_ORDERS = "working_orders"
    SECURITY_REPORTS = "security_reports"
    CANCEL_OPEN_ORDERS = "cancel_open_orders"

    def __init__(
            self,
            app_runner: AppRunner,
            config: dict,
            mkt_symbols: Set[Ticker],
            trading_symbols: Set[Ticker],
            logger: Logger = None,

    ):
        config = config or {}
        self.app_runner = app_runner
        self.fix_interface: FixInterface = app_runner.app
        self.message_queue: queue.Queue = app_runner.app.message_queue
        self.config: dict = config
        self.logger: Logger = logger if logger is not None else app_runner.logger
        self.start_time = pd.Timestamp.utcnow()
        self.timeout = pd.Timedelta(config.get("timeout", "00:30:00"))
        self.queue_timeout = pd.Timedelta(config.get("queue_timeout", "00:00:10"))
        self.logged_in = False
        self.completed = False
        self.timed_out = False

        # symbols to use, make sure we have really a set of tuples
        self.mkt_symbols: Set[Ticker] = {tuple(pair) for pair in mkt_symbols}
        self.trading_symbols: Set[Ticker] = {tuple(pair) for pair in trading_symbols}
        self.trading_exchanges = set([exchange for (exchange, _) in self.trading_symbols])
        self.position_report_counter: Dict[Tuple[str, str], int] = dict()

        # state variables to determine readiness for trading and stopping trading
        self.starting_reference: dict = {}
        self.starting_barriers: dict = {}
        self.stopping_reference: dict = {}
        self.stopping_barriers: dict = {}

        # set from configuration
        self.subscribe_for_position_updates = config.get("subscribe_for_position_updates", True)
        self.subscribe_for_trade_capture_reports = config.get("subscribe_for_trade_capture_reports", True)
        self.compare_order_status = config.get("compare_order_status", True)
        self.cancel_orders_on_exit = config.get("cancel_orders_on_exit", True)
        self.use_mass_cancel_request = config.get("use_mass_cancel_request", True)
        self.cancel_timeout_seconds = config.get("cancel_timeout_seconds", 5)
        self.save_before_cancel_orders_on_exit = config.get("save_before_cancel_orders_on_exit", True)
        self.print_reports = config.get("print_reports", True)

        self.timer_interval = pd.Timedelta(config.get("timer_interval", "01:00:00"))
        self.timer_alignment_freq = config.get("timer_alignment_freq", "1h")
        self.recurring_timer = AlignedRepeatingTimer(
            self.timer_interval,
            self.on_timer,
            name="strategy_timer",
            alignment_freq=self.timer_alignment_freq
        )

        # tracking position and orders
        self.position_tracker = PositionTracker("local", True, self.logger)
        self.order_tracker = OrderTracker("local", self.logger, self.position_tracker, self.print_reports)

        # order books
        self.order_books: Dict[Tuple[str, str], OrderBook] = {}

        # security list
        self.security_list: Dict[Tuple[str, str], Security] = {}

        self.exception = None

        # collecting the reports of a mass status requests
        self.mass_status_exec_reports = []

        self.current_exec_state = StrategyExecState.STOPPED

    def get_starting_barriers(self) -> dict:
        return {
            self.ORDERBOOK_SNAPSHOTS: self.mkt_symbols.copy(),
            self.POSITION_SNAPSHOTS: 1,
            self.WORKING_ORDERS: self.trading_symbols.copy(),
            self.SECURITY_REPORTS: 1
        }

    def get_stopping_barriers(self) -> dict:
        return {
            self.CANCEL_OPEN_ORDERS: self.trading_symbols.copy()
        }

    def dispatch(self):
        while not self.completed:
            try:
                # blocking here and wait for next message until timeout
                msg = self.message_queue.get(timeout=self.queue_timeout.total_seconds())

                if isinstance(msg, OrderBookUpdate):
                    self.on_order_book_update(msg)
                elif isinstance(msg, Trades):
                    self.on_trades(msg)
                elif isinstance(msg, ExecReport):
                    self.on_exec_report(msg)
                elif isinstance(msg, TradeCaptureReport):
                    self.on_trade_capture_report(msg)
                elif isinstance(msg, PositionReports):
                    self.on_position_reports(msg)
                elif isinstance(msg, Heartbeat):
                    self.on_heartbeat(msg)
                elif isinstance(msg, OrderMassCancelReport):
                    self.on_order_mass_cancel_report(msg)
                elif isinstance(msg, Reject):
                    self.on_reject(msg)
                elif isinstance(msg, BusinessMessageReject):
                    self.on_business_message_reject(msg)
                elif isinstance(msg, MarketDataRequestReject):
                    self.on_market_data_request_reject(msg)
                elif isinstance(msg, OrderBookSnapshot):
                    self.on_order_book_snapshot(msg)
                elif isinstance(msg, SecurityReport):
                    self.on_security_report(msg)
                elif isinstance(msg, PositionRequestAck):
                    self.on_position_request_ack(msg)
                elif isinstance(msg, TradeCaptureReportRequestAck):
                    self.on_trade_capture_report_request_ack(msg)
                elif isinstance(msg, GatewayNotReady):
                    self.on_gateway_not_ready(msg)
                elif isinstance(msg, Logon):
                    self.on_logon(msg)
                elif isinstance(msg, Logout):
                    self.on_logout(msg)
                elif isinstance(msg, Create):
                    self.on_create(msg)
                else:
                    self.logger.info(f"unknown message {msg}")

            except queue.Empty:
                self.logger.info(f"queue empty after waiting {self.queue_timeout.total_seconds()}s")

            except Exception as e:
                self.exception = e
                self.current_exec_state = StrategyExecState.EXCEPTION
                self.logger.exception(f"dispatch: exception {e}")

            self.exec_state_evaluation()

    def exec_state_evaluation(self):
        try:
            if self.current_exec_state == StrategyExecState.STARTED:
                self.trade()
                if self.check_completed():
                    self.stopping()

            elif self.current_exec_state == StrategyExecState.STOPPED:
                if self.check_should_start():
                    self.app_runner.start()
                    self.current_exec_state = StrategyExecState.LOGING_IN

            elif self.current_exec_state == StrategyExecState.LOGING_IN:
                if self.logged_in:
                    self.current_exec_state = StrategyExecState.LOGGED_IN
                    self.exec_state_evaluation()

            elif self.current_exec_state == StrategyExecState.LOGGED_IN:
                self.starting()

            elif self.current_exec_state == StrategyExecState.STARTING:
                if self.check_started():
                    self.current_exec_state = StrategyExecState.STARTED
                    self.exec_state_evaluation()

            elif self.current_exec_state == StrategyExecState.STOPPING:
                if self.check_stopping():
                    self.app_runner.stop()
                    if self.check_should_start():
                        self.current_exec_state = StrategyExecState.STOPPED
                    else:
                        self.current_exec_state = StrategyExecState.FINISHED

            elif self.current_exec_state == StrategyExecState.EXCEPTION:
                pass

        except Exception as e:
            self.exception = e
            self.current_exec_state = StrategyExecState.EXCEPTION
            self.logger.exception(f"exec_state_evaluation: exception {e}")
            self.exec_state_evaluation()

    def check_should_start(self):
        return not self.timed_out and not self.completed

    def starting(self):
        self.starting_barriers = self.get_starting_barriers()
        self.starting_reference = self.get_starting_barriers()
        self.request_security_data()
        self.subscribe_market_data()
        self.request_working_orders()
        self.request_position_snapshot()
        if self.subscribe_for_position_updates:
            self.subscribe_position_updates()
        if self.subscribe_for_trade_capture_reports:
            self.subscribe_trade_capture_reports()
        self.current_exec_state = StrategyExecState.STARTING

    def check_started(self):
        self.logger.debug(f"starting_barriers: {self.starting_barriers}")
        rows = sum(
            [
                single_task(self.SECURITY_REPORTS, self.starting_reference, self.starting_barriers),
                set_task(self.ORDERBOOK_SNAPSHOTS, self.starting_reference, self.starting_barriers),
                set_task(self.WORKING_ORDERS, self.starting_reference, self.starting_barriers),
                single_task(self.POSITION_SNAPSHOTS, self.starting_reference, self.starting_barriers),
            ], [])
        line = "\n".join(rows)
        self.logger.info(f"starting_barriers:\n{line}")
        return len(self.starting_barriers) == 0

    def stopping(self):
        self.stop_timers()

        if self.save_before_cancel_orders_on_exit:
            self.fix_interface.save_fix_message_history(pre=self.file_name_prefix())

        # cancel open orders if required
        if self.cancel_orders_on_exit and self.logged_in:
            self.logger.info(f"cancelling orders on exit")
            self.stopping_barriers = self.get_stopping_barriers()
            if self.use_mass_cancel_request:
                for (exchange, symbol) in self.trading_symbols:
                    msg = self.fix_interface.order_mass_cancel_request(exchange, symbol)
                    self.logger.info(f"  order mass cancel request {fix_message_string(msg)}")
            else:
                for (ord_id, order) in self.order_tracker.open_orders.items():
                    msg = self.fix_interface.order_cancel_request(order)
                    self.logger.info(f"  order cancel request {fix_message_string(msg)}")

            self.logger.info(f"start waiting for {self.cancel_timeout_seconds}s")
        else:
            self.logger.info(f"keep orders alive on exit")

        if not self.save_before_cancel_orders_on_exit:
            self.fix_interface.save_fix_message_history(pre=self.file_name_prefix())
        self.current_exec_state = StrategyExecState.STOPPING

    def check_stopping(self) -> bool:
        self.logger.debug(f"stopping_barriers: {self.stopping_barriers}")
        rows = sum(
            [
                set_task(self.CANCEL_OPEN_ORDERS, self.stopping_reference, self.stopping_barriers),
            ], [])
        line = "\n".join(rows)
        self.logger.info(f"stopping_barriers:\n{line}")
        return len(self.stopping_barriers) == 0

    def check_completed(self):
        now = self.now()
        end = self.start_time + self.timeout
        self.timed_out = now >= end
        self.completed = self.timed_out
        return self.completed

    def request_security_data(self):
        self.logger.info(f"====> requesting security list...")
        self.fix_interface.security_list_request()

        # TODO check if this gives back something
        # self.logger.info(
        #     f"====> requesting security definitions for symbols {self.trading_symbols}..."
        # )
        # for (exchange, symbol) in self.trading_symbols:
        #     self.countdown_to_ready += 1
        #     self.fix_interface.security_definition_request(exchange, symbol)

    def subscribe_market_data(self):
        self.logger.info(f"====> subscribing to market data for {self.mkt_symbols}...")
        for exchange_symbol in self.mkt_symbols:
            self.fix_interface.market_data_request([exchange_symbol], 0, content="book")
            self.fix_interface.market_data_request([exchange_symbol], 0, content="trade")

    def request_working_orders(self):
        self.logger.info(f"====> requesting working order status for {self.trading_symbols}...")
        for (exchange, symbol) in self.trading_symbols:
            msg = self.fix_interface.order_mass_status_request(
                exchange,
                symbol,
                account=None,
                mass_status_req_id=f"ms_{self.fix_interface.generate_msg_id()}",
                mass_status_req_type=fix.MassStatusReqType_STATUS_FOR_ALL_ORDERS
            )
            self.logger.debug(f"{fix_message_string(msg)}")

    def request_position_snapshot(self):
        # note that the same account alias has to be used for all the connected exchanges
        account = self.fix_interface.get_account()
        self.logger.info(f"====> requesting position snapshot for account {account} on {self.trading_exchanges}...")
        for exchange in self.trading_exchanges:
            msg = self.fix_interface.request_for_positions(
                exchange,
                account=account,
                pos_req_id=f"pos_{self.fix_interface.generate_msg_id()}",
                subscription_type=fix.SubscriptionRequestType_SNAPSHOT
            )
            self.logger.debug(f"{fix_message_string(msg)}")

    def subscribe_position_updates(self):
        # note that the same account alias has to be used for all the connected exchanges
        account = self.fix_interface.get_account()
        for (exchange, symbol) in self.trading_symbols:
            self.logger.info(f"====> subscribing position updates for symbol {symbol} on {exchange}...")
            msg = self.fix_interface.request_for_positions(
                exchange,
                account=account,
                symbol=symbol,
                pos_req_id=f"pos_{self.fix_interface.generate_msg_id()}",
                subscription_type=fix.SubscriptionRequestType_SNAPSHOT_PLUS_UPDATES
            )
            self.logger.debug(f"{fix_message_string(msg)}")

    def subscribe_trade_capture_reports(self):
        self.logger.info(f"====> requesting trade capture reports...")
        msg = self.fix_interface.trade_capture_report_request(
            trade_req_id=f"trade_capt_{self.fix_interface.generate_msg_id()}",
            trade_request_type=fix.TradeRequestType_ALL_TRADES,
            subscription_type=fix.SubscriptionRequestType_SNAPSHOT_PLUS_UPDATES
        )
        self.logger.debug(f"{fix_message_string(msg)}")

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.utcnow()
            
    def start_timers(self):
        self.logger.info(f"starting timers...")
        self.recurring_timer.start()

    def stop_timers(self):
        self.logger.info(f"stopping timers...")
        if self.recurring_timer.is_alive():
            self.recurring_timer.cancel()
            self.recurring_timer.join()
        self.logger.info(f"timers stopped")

    def on_timer(self):
        self.logger.info(f"saving dataframes and purging history")
        self.fix_interface.save_fix_message_history(pre=self.file_name_prefix(), purge_history=True)
        # TODO save other stuff
        self.logger.info(f"   \u2705 saved and purged fix message history")

    def on_logon(self, msg: Logon):
        self.logged_in = True

    def on_create(self, msg: Create):
        pass

    def on_logout(self, msg: Logout):
        self.logged_in = False

    def on_heartbeat(self, msg: Heartbeat):
        pass

    def on_gateway_not_ready(self, msg: GatewayNotReady):
        self.logger.error(f"on_gateway_not_ready: {msg}")
        self.completed = True
        self.exception = Exception("GatewayNotReady")

    def on_reject(self, msg: Reject):
        self.logger.error(
            f"on_reject: "
            f"\n  report = [{msg}] "
        )

    def on_business_message_reject(self, msg: BusinessMessageReject):
        self.logger.error(f"on_business_message_reject: {msg}")

    def on_market_data_request_reject(self, msg: MarketDataRequestReject):
        self.logger.error(f"on_market_data_request_reject: {msg}")

    def on_security_report(self, msg: SecurityReport):
        for security in msg.securities.values():
            self.security_list[(security.exchange, security.symbol)] = security
            self.logger.info(f"{security}")
        self.starting_barriers.pop(self.SECURITY_REPORTS, 0)
        self.logger.info(f"<==== security list completed")

    def on_position_request_ack(self, msg: PositionRequestAck):
        self.logger.info(f"on_position_request_ack: {msg}")

    def on_position_reports(self, msg: PositionReports):
        if self.starting_barriers.pop(self.POSITION_SNAPSHOTS, 0):
            self.position_tracker.set_snapshots(msg.reports, self.now(), overwrite=True)
            self.logger.info(
                f"<==== initial position reports completed \n"
                f"{msg.tabulate(compact=False)}"
            )
        elif self.print_reports:
            self.logger.info(
                f"<==== position reports completed \n"
                f"{msg.tabulate(compact=False)}"
            )

    def on_trade_capture_report_request_ack(self, msg: TradeCaptureReportRequestAck):
        self.logger.info(f"on_trade_capture_report_request_ack: {msg}")

    def on_trade_capture_report(self, msg: TradeCaptureReport):
        if self.print_reports:
            self.logger.info(
                f"<==== trade reports completed \n"
                f"{msg.tabulate(compact=False)}"
            )

    def on_exec_report(self, msg: ExecReport):
        if msg.exec_type == "I":
            if msg.ord_status == fix.OrdStatus_REJECTED:
                self.on_mass_status_exec_report(MassStatusExecReportNoOrders(msg.exchange, msg.symbol, msg.text))
            elif msg.is_mass_status:
                assert msg.tot_num_reports is not None and msg.last_rpt_requested is not None
                self.mass_status_exec_reports.append(msg)
                if len(self.mass_status_exec_reports) == msg.tot_num_reports and msg.last_rpt_requested:
                    self.on_mass_status_exec_report(MassStatusExecReport(self.mass_status_exec_reports))
                    self.mass_status_exec_reports = []
            else:
                self.on_status_exec_report(msg)
        elif msg.exec_type == fix.ExecType_REJECTED or msg.ord_status == fix.OrdStatus_REJECTED:
            self.on_reject_exec_report(msg)
        else:
            self.order_tracker.process(msg, self.now())

            if self.CANCEL_OPEN_ORDERS in self.stopping_barriers:
                open_orders = self.order_tracker.open_orders
                if len(open_orders) > 0:
                    order_status_count = Order.order_status_count(open_orders.values(), True)
                    self.logger.info(f"waiting to cancel {len(open_orders)} open orders: {order_status_count}")
                else:
                    self.stopping_barriers.pop(self.CANCEL_OPEN_ORDERS)
                    self.logger.info(f"<==== all open orders cancelled")

    def on_status_exec_report(self, msg: ExecReport):
        if self.print_reports:
            self.logger.info(
                f"on_status_exec_report: "
                f"execution report of order status response:\n"
                f"{ExecReport.tabulate([msg])}"
            )

    def on_mass_status_exec_report(self, msg: Union[MassStatusExecReport, MassStatusExecReportNoOrders]):
        remaining: Set[Ticker] = self.starting_barriers[self.WORKING_ORDERS]
        keys: Set[Ticker] = msg.keys()
        if keys.issubset(remaining):
            if isinstance(msg, MassStatusExecReport):
                self.order_tracker.set_snapshots(msg.reports, self.now(), overwrite=True)
                self.logger.info(
                    f"on_mass_status_exec_report: initial mass order status response:"
                    f"\nexec reports:"
                    f"\n{ExecReport.tabulate(msg.reports)}"
                    f"\npending orders:"
                    f"\n{Order.tabulate(self.order_tracker.pending_orders)}"
                    f"\nopen orders:"
                    f"\n{Order.tabulate(self.order_tracker.open_orders)}"
                    f"\nhistorical orders:"
                    f"\n{Order.tabulate(self.order_tracker.history_orders)}"
                )
            elif isinstance(msg, MassStatusExecReportNoOrders):
                if msg.text != "NO ORDERS":
                    self.logger.warning(f"unexpected text message {msg.text}")
                self.logger.info(
                    f"on_mass_status_exec_report: initial mass order status response: "
                    f"no orders for {msg.exchange} {msg.symbol}"
                )

            remaining = remaining - keys
            self.starting_barriers[self.WORKING_ORDERS] = remaining
            if len(remaining) == 0:
                self.starting_barriers.pop(self.WORKING_ORDERS, None)
                self.logger.info(f"<==== obtained working order status")
            else:
                self.logger.info(f"waiting for working orders status for {remaining}")

    def on_reject_exec_report(self, msg: ExecReport):
        self.logger.error(f"on_reject_exec_report: {msg}")

    def on_order_mass_cancel_report(self, msg: OrderMassCancelReport):
        self.logger.info(f"on_order_mass_cancel_report: {msg}")
        if self.CANCEL_OPEN_ORDERS in self.stopping_barriers:
            remaining = self.stopping_barriers[self.CANCEL_OPEN_ORDERS]
            if msg.response != fix.MassCancelResponse_CANCEL_REQUEST_REJECTED:
                remaining.remove((msg.exchange, msg.symbol))
            self.logger.info(
                f"mass cancel response {msg.response} "
                f"waiting to cancel orders for {remaining}")
            if len(remaining) == 0:
                self.stopping_barriers.pop(self.CANCEL_OPEN_ORDERS)
                self.logger.info(f"<==== all open orders cancelled")

    def on_order_book_snapshot(self, msg: OrderBookSnapshot):
        self.logger.info(f"on_order_book_snapshot: {msg.key()}")
        if self.ORDERBOOK_SNAPSHOTS in self.starting_barriers:
            remaining = self.starting_barriers[self.ORDERBOOK_SNAPSHOTS]
            remaining.remove((msg.exchange, msg.symbol))
            if len(remaining) == 0:
                self.starting_barriers.pop(self.ORDERBOOK_SNAPSHOTS)
                self.logger.info(f"<==== order book snapshots completed")
            else:
                self.logger.info(f"waiting for orderbook snapshots for {remaining}")

        self.order_books[msg.key()] = OrderBook(
            msg.exchange, msg.symbol, msg.bids, msg.asks, msg.exchange_ts, msg.local_ts
        )

    def on_order_book_update(self, msg: OrderBookUpdate):
        book = self.order_books.get(msg.key(), None)
        if book is not None:
            for price, quantity, is_bid in msg.updates:
                book.update(price, quantity, is_bid)

    def on_trades(self, msg: Trades):
        pass

    def round_down(self, price: float, direction: RoundingDirection, ticker: Ticker) -> Optional[float]:
        min_tick_size = self.security_list.get_ticker(ticker, 0)
        if price >= 0 and min_tick_size > 0:
            if direction == RoundingDirection.DOWN:
                return math.floor(price / min_tick_size) * min_tick_size
            elif direction == RoundingDirection.UP:
                return math.ceil(price / min_tick_size) * min_tick_size
            else:
                self.logger.error(f"invalid rounding direction: {direction}")

    def tick_round(self, price, ticker: Ticker, min_tick_size=None):
        min_tick_size = self.security_list.get_ticker(ticker, 0) if min_tick_size is None else min_tick_size
        if min_tick_size <= 0.0:
            return round(price)
        else:
            rem = math.trunc((price % 1) / min_tick_size)
            return math.trunc(price) + rem * min_tick_size

    def file_name_prefix(self) -> str:
        username = self.fix_interface.get_username()
        account = self.fix_interface.get_account()
        timestamp = pd.Timestamp.utcnow().strftime("%Y_%m_%d_%H%M%S")
        return f"{timestamp}_{username}_{account}"
