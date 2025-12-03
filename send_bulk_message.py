#!/usr/bin/env python3
"""
Bulk Telegram sender:
- Reads Telegram user_ids from MongoDB.
- Sends a text message to each, optionally with an image.
- Handles rate limiting, RetryAfter, and common exceptions.

Usage examples:
  python bulk_telegram_sender.py --message "Hello from the bot!"
  python bulk_telegram_sender.py --message "Promo" --image "/path/to/pic.jpg"
  python bulk_telegram_sender.py --message "With URL image" --image "https://example.com/pic.jpg" --limit 100 --dry-run

Env vars (recommended):
  TELEGRAM_BOT_TOKEN=<your bot token>
  MONGO_URI=mongodb+srv://user:pass@cluster/dbname
  MONGO_DB=<db name>
  MONGO_COLLECTION=<collection name holding user ids>
"""

import argparse
import asyncio
import os
import sys
from typing import Iterable, List, Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from telegram import Bot
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError, TimedOut
from telegram.constants import ParseMode

# ---- Config defaults ----
DEFAULT_ID_FIELD = "user_id"   # Change if your field differs
DEFAULT_RATE = 15              # messages per second target (Telegram hard caps vary)
DEFAULT_CONCURRENCY = 1        # parallel tasks


def get_env(name: str, required: bool = False, default: Optional[str] = None) -> str:
    val = os.getenv(name, default)
    if required and not val:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(2)
    return val


def fetch_user_ids(uri: str, db: str, collection: str, id_field: str, limit: Optional[int]) -> List[int]:
    try:
        client = MongoClient(uri)
        coll = client[db][collection]
        cursor = coll.find(
            {id_field: {"$exists": True}},
            {id_field: 1, "_id": 0},
            limit=limit if isinstance(limit, int) and limit > 0 else 0,
        )
        ids: List[int] = []
        for doc in cursor:
            uid = doc.get(id_field)
            if isinstance(uid, (int,)) or (isinstance(uid, str) and uid.isdigit()):
                ids.append(int(uid))
        return list(dict.fromkeys(ids))  # de-duplicate, preserve order
    except PyMongoError as e:
        print(f"[MongoDB] Error: {e}", file=sys.stderr)
        sys.exit(1)


async def send_one(
    bot: Bot,
    user_id: int,
    text: str,
    image: Optional[str],
    parse_mode: Optional[str],
    rate_delay: float,
    semaphore: asyncio.Semaphore,
):
    # simple pacing per message
    await asyncio.sleep(rate_delay)

    async with semaphore:
        try:
            if image:
                # sendPhoto supports local file path or URL
                if image.startswith("http://") or image.startswith("https://"):
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=image,
                        caption=text if text else None,
                        parse_mode=parse_mode,
                    )
                else:
                    with open(image, "rb") as f:
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=f,
                            caption=text if text else None,
                            parse_mode=parse_mode,
                        )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )
            return (user_id, "ok", None)
        except RetryAfter as e:
            # Telegram is rate limiting: back off then retry once
            await asyncio.sleep(e.retry_after + 1)
            try:
                if image:
                    if image.startswith("http://") or image.startswith("https://"):
                        await bot.send_photo(chat_id=user_id, photo=image, caption=text or None, parse_mode=parse_mode)
                    else:
                        with open(image, "rb") as f:
                            await bot.send_photo(chat_id=user_id, photo=f, caption=text or None, parse_mode=parse_mode)
                else:
                    await bot.send_message(chat_id=user_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)
                return (user_id, "ok_after_retry", None)
            except Exception as e2:
                return (user_id, "failed_after_retry", str(e2))
        except Forbidden as e:
            # Bot blocked or user hasn't started the bot
            return (user_id, "forbidden", str(e))
        except (BadRequest, NetworkError, TimedOut) as e:
            return (user_id, "error", str(e))
        except Exception as e:
            return (user_id, "error", repr(e))


async def main_async(args):
    token = args.token or get_env("TELEGRAM_BOT_TOKEN", required=True)
    mongo_uri = args.mongo_uri or get_env("MONGO_URI", required=True)
    mongo_db = args.mongo_db or get_env("MONGO_DB", required=True)
    mongo_collection = args.mongo_collection or get_env("MONGO_COLLECTION", required=True)

    ids = fetch_user_ids(
        uri=mongo_uri,
        db=mongo_db,
        collection=mongo_collection,
        id_field=args.id_field,
        limit=args.limit,
    )

    # ids = ["6522546241"]

    if not ids:
        print("No user IDs found. Check your collection and id_field.")
        return

    print(f"Found {len(ids)} unique user ids.")

    if args.dry_run:
        preview = ids[: min(10, len(ids))]
        print("[DRY RUN] Would send to first IDs:", preview, "...")
        return

    bot = Bot(token=token)

    # pacing parameters
    rate = max(1, args.rate)  # messages per second
    delay_per_msg = 1.0 / rate
    concurrency = max(1, args.concurrency)

    parse_mode = None
    if args.parse_mode:
        # Safe choices: "HTML" or "MARKDOWN_V2"
        if args.parse_mode.upper() in ("HTML", "MARKDOWN_V2"):
            parse_mode = getattr(ParseMode, args.parse_mode.upper())
        else:
            print("Unsupported parse mode. Use 'HTML' or 'MARKDOWN_V2'. Ignoring.")

    sem = asyncio.Semaphore(concurrency)

    tasks = [
        asyncio.create_task(
            send_one(
                bot=bot,
                user_id=uid,
                text=args.message,
                image=args.image,
                parse_mode=parse_mode,
                rate_delay=delay_per_msg,
                semaphore=sem,
            )
        )
        for uid in ids
    ]

    ok = 0
    forbidden = 0
    failed = 0
    after_retry = 0

    for coro in asyncio.as_completed(tasks):
        uid, status, err = await coro
        if status in ("ok", "ok_after_retry"):
            ok += 1
            if status == "ok_after_retry":
                after_retry += 1
        elif status == "forbidden":
            forbidden += 1
            print(f"[{uid}] Forbidden (blocked or never started bot).")
        else:
            failed += 1
            print(f"[{uid}] Failed: {err}")

    print("\n--- SUMMARY ---")
    print(f"Delivered: {ok} (including {after_retry} after retry)")
    print(f"Forbidden/blocked: {forbidden}")
    print(f"Failed: {failed}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Send a bulk Telegram message to user IDs from MongoDB.")
    p.add_argument("--token", help="Telegram bot token (or set TELEGRAM_BOT_TOKEN).")
    p.add_argument("--mongo-uri", help="MongoDB URI (or set MONGO_URI).")
    p.add_argument("--mongo-db", help="MongoDB DB name (or set MONGO_DB).")
    p.add_argument("--mongo-collection", help="MongoDB collection name (or set MONGO_COLLECTION).")
    p.add_argument("--id-field", default=DEFAULT_ID_FIELD, help=f"Field name containing Telegram user id (default: {DEFAULT_ID_FIELD}).")
    p.add_argument("--message", required=True, help="Text message to send. For caption when --image is provided.")
    p.add_argument("--image", help="Optional image path or URL to send (sendPhoto).")
    p.add_argument("--parse-mode", choices=["HTML", "MARKDOWN_V2"], help="Optional parse mode for formatting.")
    p.add_argument("--limit", type=int, help="Optional limit of IDs to send to.")
    p.add_argument("--rate", type=int, default=DEFAULT_RATE, help=f"Target messages per second (default: {DEFAULT_RATE}).")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help=f"Parallel sends (default: {DEFAULT_CONCURRENCY}).")
    p.add_argument("--dry-run", action="store_true", help="Do not send anything; just print summary.")
    return p


def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()