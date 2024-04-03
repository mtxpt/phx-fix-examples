import argparse
import logging
import queue
import yaml
from pathlib import Path

from phx.utils import setup_logger, set_file_loging_handler, make_dirs
from phx.fix.app import App, AppRunner, FixSessionConfig
from phx.strategy.random import RandomStrategy


def temp_dir() -> Path:
    local = Path(__file__).parent.resolve()
    return local.parent.parent.parent.parent.absolute() / "temp"


if __name__ == "__main__":
    fix_settings_file = "fix-settings.cfg"
    strategy_config_file = f"strategy.yaml"

    parser = argparse.ArgumentParser(description="FIX Client")
    parser.add_argument(
        "fix_settings_file", type=str, nargs='?',
        default=fix_settings_file,
        help="Name of quickfix settings file")
    parser.add_argument(
        "strategy_config_file", type=str, nargs='?',
        default=strategy_config_file,
        help="Name of strategy config file")
    args = parser.parse_args()

    config = yaml.safe_load(open(strategy_config_file))
    export_dir = temp_dir() / "random"
    make_dirs(export_dir)
    logger = set_file_loging_handler(
        setup_logger("fix_service", level=logging.INFO),
        export_dir / "fix_service.log"
    )
    message_queue = queue.Queue()
    fix_configs = FixSessionConfig(
        sender_comp_id="test",
        target_comp_id="proxy",
        user_name="trader",
        password="secret",
        auth_by_key=True,
        account="T1",
        socket_connect_port="1238",
        socket_connect_host="127.0.0.1",
    )
    fix_session_settings = fix_configs.get_fix_session_settings()

    app = App(message_queue, fix_session_settings, logger, export_dir)
    app_runner = AppRunner(app, fix_session_settings, fix_configs.get_session_id(), logger)

    strategy = RandomStrategy(app_runner, config, logger)
    strategy.dispatch()
