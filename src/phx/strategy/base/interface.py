import abc
from enum import IntEnum
import pandas as pd
from typing import Union, Optional, Tuple, Union

from phx.fix.model import Logon, Create, Logout, Heartbeat
from phx.fix.model import OrderBookSnapshot, OrderBookUpdate, Trades
from phx.fix.model import ExecReport, PositionReports, SecurityReport, TradeCaptureReport
from phx.fix.model import GatewayNotReady, NotConnected, Reject, BusinessMessageReject, MarketDataRequestReject
from phx.fix.model import PositionRequestAck, TradeCaptureReportRequestAck
from phx.fix.model import OrderMassCancelReport, MassStatusExecReport, MassStatusExecReportNoOrders


class StrategyExecState(IntEnum):
    STOPPED = 0
    LOGING_IN = 1
    LOGGED_IN = 2
    STARTING = 3
    STARTED = 4
    STOPPING = 5
    LOGGED_OUT = 6
    FINISHED = 7


class RoundingDirection(IntEnum):
    UP = 0
    DOWN = 1


class StrategyInterface(abc.ABC):

    @abc.abstractmethod
    def trade(self):
        pass

    @abc.abstractmethod
    def run(self) -> bool:
        pass

    @abc.abstractmethod
    def dispatch(self):
        pass

    @abc.abstractmethod
    def exec_state_evaluation(self):
        pass

    @abc.abstractmethod
    def check_if_can_start(self):
        pass

    @abc.abstractmethod
    def starting(self):
        pass

    @abc.abstractmethod
    def check_if_started(self) -> bool:
        pass

    @abc.abstractmethod
    def stopping(self):
        pass

    @abc.abstractmethod
    def check_if_stopped(self) -> bool:
        pass

    @abc.abstractmethod
    def check_if_completed(self) -> bool:
        pass

    @abc.abstractmethod
    def request_security_data(self):
        pass

    @abc.abstractmethod
    def subscribe_market_data(self):
        pass

    @abc.abstractmethod
    def request_working_orders(self):
        pass

    @abc.abstractmethod
    def request_position_snapshot(self):
        pass

    @abc.abstractmethod
    def subscribe_position_updates(self):
        pass

    @abc.abstractmethod
    def subscribe_trade_capture_reports(self):
        pass

    @abc.abstractmethod
    def now(self) -> pd.Timestamp:
        pass

    @abc.abstractmethod
    def start_timers(self):
        pass

    @abc.abstractmethod
    def stop_timers(self):
        pass

    @abc.abstractmethod
    def on_timer(self):
        pass

    @abc.abstractmethod
    def on_logon(self, msg: Logon):
        pass

    @abc.abstractmethod
    def on_create(self, msg: Create):
        pass

    @abc.abstractmethod
    def on_logout(self, msg: Logout):
        pass

    @abc.abstractmethod
    def on_heartbeat(self, msg: Heartbeat):
        pass

    @abc.abstractmethod
    def on_connection_error(self, msg: Union[NotConnected, GatewayNotReady]):
        pass

    @abc.abstractmethod
    def on_reject(self, msg: Reject):
        pass

    @abc.abstractmethod
    def on_business_message_reject(self, msg: BusinessMessageReject):
        pass

    @abc.abstractmethod
    def on_market_data_request_reject(self, msg: MarketDataRequestReject):
        pass

    @abc.abstractmethod
    def on_security_report(self, msg: SecurityReport):
        pass

    @abc.abstractmethod
    def on_position_request_ack(self, msg: PositionRequestAck):
        pass

    @abc.abstractmethod
    def on_position_reports(self, msg: PositionReports):
        pass

    @abc.abstractmethod
    def on_trade_capture_report_request_ack(self, msg: TradeCaptureReportRequestAck):
        pass

    @abc.abstractmethod
    def on_trade_capture_report(self, msg: TradeCaptureReport):
        pass

    @abc.abstractmethod
    def on_exec_report(self, msg: ExecReport):
        pass

    @abc.abstractmethod
    def on_status_exec_report(self, msg: ExecReport):
        pass

    @abc.abstractmethod
    def on_mass_status_exec_report(self, msg: Union[MassStatusExecReport, MassStatusExecReportNoOrders]):
        pass

    @abc.abstractmethod
    def on_reject_exec_report(self, msg: ExecReport):
        pass

    @abc.abstractmethod
    def on_order_mass_cancel_report(self, msg: OrderMassCancelReport):
        pass

    @abc.abstractmethod
    def on_order_book_snapshot(self, msg: OrderBookSnapshot):
        pass

    @abc.abstractmethod
    def on_order_book_update(self, msg: OrderBookUpdate):
        pass

    @abc.abstractmethod
    def on_trades(self, msg: Trades):
        pass

    @abc.abstractmethod
    def round(
            self,
            price: float,
            direction: RoundingDirection,
            ticker: Tuple[str, str],
            min_tick_size=None
    ) -> Optional[float]:
        pass

    @abc.abstractmethod
    def tick_round(
            self,
            price,
            ticker: Tuple[str, str],
            min_tick_size=None
    ) -> float:
        pass
