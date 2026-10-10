#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
load_dotenv(dotenv_path=find_dotenv(usecwd=True))


def parse_args():
    parser = argparse.ArgumentParser(description="BayLang AI")
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Запуск foreground-системы выполнения задач с сервера",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.foreground:
        from foreground import run_foreground
        return await run_foreground()

    from app import AI, build_software_engineer, run_loop
    agent = build_software_engineer()
    ai = AI(agent)
    return await run_loop(ai)


if __name__ == "__main__":
    asyncio.run(main())
