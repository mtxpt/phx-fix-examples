import argparse
import logging
import queue
import yaml
from datetime import datetime
from pathlib import Path

# external Phoenix FIX foundation library - refer to requirements.txt
from phx.utils import setup_logger, set_file_loging_handler, make_dirs
from phx.fix.app import App, AppRunner, FixSessionConfig
from phx.fix.model.auth import FixAuthenticationMethod

# internal Phoenix FIX example library
from src.phx.strategy.random import RandomStrategy


def temp_dir() -> Path:
    local = Path(__file__).parent.resolve()
    return local.absolute() / "temp"


def fix_schema_file() -> str:
    local = Path(__file__).parent.resolve()
    return str(local.parent.parent.absolute() / "fix" / "specs" / "FIX44.xml")


if __name__ == "__main__":
    strategy_config_file = f"random_strategy.yaml"
    LOG_TIMESTAMP = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    parser = argparse.ArgumentParser(description="Random Strategy")
    parser.add_argument(
        "strategy_config_file", type=str, nargs='?',
        default=strategy_config_file,
        help="Name of strategy config file")
    args = parser.parse_args()

    config = yaml.safe_load(open(args.strategy_config_file))
    make_dirs(temp_dir())
    export_dir = temp_dir() / "random"
    make_dirs(export_dir)
    logger = set_file_loging_handler(
        setup_logger("random_strategy", level=logging.INFO),
        temp_dir() / f"random_strategy_{LOG_TIMESTAMP}.log"
    )
    message_queue = queue.Queue()
    fix_configs = FixSessionConfig(
        sender_comp_id="test",
        target_comp_id="phoenix-prime",
        user_name="trader",
        password="secret",
        fix_auth_method=FixAuthenticationMethod.HMAC_SHA256,
        account="T1",
        socket_connect_port="1238",
        socket_connect_host="127.0.0.1",
        fix_schema_dict=fix_schema_file(),
    )
    fix_session_settings = fix_configs.get_fix_session_settings()

    app = App(message_queue, fix_session_settings, logger, export_dir)
    app_runner = AppRunner(app, fix_session_settings, fix_configs.get_session_id(), logger)

    strategy = RandomStrategy(app_runner, config, logger)
    strategy.strategy_loop()

    logger.info("strategy finished")
