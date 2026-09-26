import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import database

async def main():
    await database.setup_database()
    await database.set_setting("action_trigger", "create_backup_channel")
    print("Action trigger set to create_backup_channel successfully!")

if __name__ == "__main__":
    asyncio.run(main())
