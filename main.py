import argparse
import asyncio

from config.settings import Settings
from core import logger
from monitor.gift_monitor import GiftMonitor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="斗鱼直播间礼物监控")
    parser.add_argument("--room", type=int, action="append", help="直播间 ID，可多次指定")
    return parser.parse_args()


async def amain(settings: Settings) -> None:
    monitor = GiftMonitor(settings)
    await monitor.run()


def main() -> None:
    args = parse_args()
    settings = Settings()
    if args.room:
        settings.add_rooms(args.room)
    logger.setup_logging(settings.log_dir, settings.log_retention_days)
    try:
        asyncio.run(amain(settings), loop_factory=asyncio.SelectorEventLoop)
    except KeyboardInterrupt:
        logger.log_system("monitor stopped by user")


if __name__ == "__main__":
    main()
