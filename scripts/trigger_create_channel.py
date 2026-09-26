import asyncio
import database
from userbot import UserBot

async def main():
    await database.set_setting("action_trigger", "create_backup_channel")
    print("Action trigger set to create_backup_channel successfully!")

if __name__ == "__main__":
    asyncio.run(main())
