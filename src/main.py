#!/usr/bin/env python3

import asyncio
from dotenv import find_dotenv, load_dotenv
from app import AI, build_software_engineer, run_loop

load_dotenv(dotenv_path=find_dotenv(usecwd=True))


async def main():
    agent = build_software_engineer()
    ai = AI(agent)
    return await run_loop(ai)


if __name__ == "__main__":
    asyncio.run(main())
