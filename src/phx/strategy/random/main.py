import argparse
import queue
import yaml

from phx.utils import PathBase, setup_logger
from phx.fix.app import App, AppRunner, FixSessionConfig
from phx.strategy.random import RandomStrategy

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
    path_base = PathBase()
    temp_dir = path_base.temp
    logger = setup_logger("fix_service")
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

    app = App(message_queue, fix_session_settings, logger, temp_dir)
    app_runner = AppRunner(app, fix_session_settings, fix_configs.get_session_id(), logger)

    strategy = RandomStrategy(app_runner, config, logger)
    strategy.dispatch()
