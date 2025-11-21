import asyncio
import logging

from app.bot import create_client, register_handlers, run_client

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    client = create_client()
    register_handlers(client)
    await run_client(client)


if __name__ == "__main__":
    asyncio.run(main())
