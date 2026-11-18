"""Repository regressions. Every test uses SQLite :memory:, never users.db/.env."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def load_database():
    config = types.ModuleType("config")
    config.MAX_RICE_PER_USER = 6
    spec = importlib.util.spec_from_file_location("database_under_test", Path(__file__).resolve().parents[1] / "database.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"config": config}):
        spec.loader.exec_module(module)
    module.DB_NAME = ":memory:"
    return module


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = load_database()
        self.conn = await self.db.init_db()
        await self.db.create_table()
        await self.db.add_new_columns()
        await self.db.add_user(1, "Alice", "alice")

    async def asyncTearDown(self):
        await self.db.close_db()

    async def test_concurrent_inventory_increments(self):
        await asyncio.gather(*(self.db.upsert_hebao_item(1, "probe", "Probe", delta=1) for _ in range(20)))
        items = await self.db.get_hebao_items(1)
        self.assertEqual(next(x["quantity"] for x in items if x["item_key"] == "probe"), 20)
        await self.db.upsert_hebao_item(1, "probe", delta=-100)
        self.assertFalse(any(x["item_key"] == "probe" for x in await self.db.get_hebao_items(1)))

    async def test_daily_claim_once_under_concurrency(self):
        results = await asyncio.gather(*(self.db.claim_daily_food(1, "korm_waifu", "Корм") for _ in range(10)))
        self.assertEqual(sum(results), 1)
        items = await self.db.get_hebao_items(1)
        self.assertEqual(next(x["quantity"] for x in items if x["item_key"] == "korm_waifu"), 5)
        self.assertFalse(await self.db.claim_daily_food(999, "korm_waifu", "Корм"))

    async def test_feed_debit_and_cooldown_are_atomic(self):
        await self.db.create_waifu_for_user(1)
        await self.db.upsert_hebao_item(1, "miska_risa", set_value=0)
        await self.db.upsert_hebao_item(1, "korm_waifu", set_value=1)
        results = await asyncio.gather(*(self.db.feed_waifu_atomic(1, 100, 5) for _ in range(2)))
        self.assertEqual(sorted(x["status"] for x in results), ["cooldown", "ok"])
        self.assertEqual((await self.db.get_waifu_by_user(1))["trust"], 10)
        self.assertEqual(await self.db.get_hebao_items(1), [])

    async def test_legacy_rice_visible_and_edible(self):
        await self.db.create_waifu_for_user(1)
        await self.conn.execute("DELETE FROM hebao_items WHERE user_id=1")
        await self.conn.execute("UPDATE waifu_cat SET miska_risa=3 WHERE user_id=1")
        await self.conn.commit()
        self.assertEqual((await self.db.get_hebao_overview(1))[0]["quantity"], 3)
        result = await self.db.feed_waifu_atomic(1, 100, 5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["left_qty"], 2)
        self.assertEqual((await self.db.get_hebao_overview(1))[0]["quantity"], 2)

    async def test_decay_preserves_partial_interval_and_accepts_background_row(self):
        await self.db.create_waifu_for_user(1)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await self.db.update_cat_state(1, last_satiety_update=start.isoformat())
        await self.db.decay_waifu_satiety(1, start+timedelta(hours=9))
        cat = await self.db.decay_waifu_satiety(1, start+timedelta(hours=18))
        self.assertEqual(cat["satiety"], 70)
        self.assertEqual(datetime.fromisoformat(cat["last_satiety_update"]), start+timedelta(hours=15))

    async def test_warning_accumulation(self):
        for _ in range(3):
            self.assertTrue(await self.db.add_warning(1, -100, "test", 2))
        self.assertEqual(await self.db.get_warnings_count(1, -100), 3)
        self.assertTrue(await self.db.remove_warning(1, -100, 2))
        self.assertEqual(await self.db.get_warnings_count(1, -100), 2)

    async def test_old_warning_schema_migration_keeps_records(self):
        await self.conn.execute("DROP TABLE user_warnings")
        await self.conn.execute("""CREATE TABLE user_warnings(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, reason TEXT,
            warned_by INTEGER NOT NULL, warned_at TEXT, UNIQUE(user_id,chat_id))""")
        await self.conn.execute("INSERT INTO user_warnings VALUES(1,1,-100,'old',2,'2026-01-01')")
        await self.conn.commit()
        await self.db.add_new_columns()
        await self.db.add_warning(1, -100, "new", 2)
        self.assertEqual(await self.db.get_warnings_count(1, -100), 2)

    async def test_marriage_deleted_before_cat_and_user(self):
        await self.db.create_waifu_for_user(1)
        cat = await self.db.get_waifu_by_user(1)
        await self.db.register_marriage(1, cat["cats_id"])
        self.assertTrue(await self.db.delete_waifu_by_user(1))
        self.assertIsNone(await self.db.get_marriage(1))
        await self.db.create_waifu_for_user(1)
        cat = await self.db.get_waifu_by_user(1)
        await self.db.register_marriage(1, cat["cats_id"])
        self.assertTrue(await self.db.delete_user_completely("alice"))
        self.assertIsNone(await self.db.get_user_profile(1))
        self.assertEqual(await (await self.conn.execute("PRAGMA foreign_key_check")).fetchall(), [])

    async def test_cat_migration_keeps_trust_and_marriage(self):
        await self.conn.execute("DROP TABLE marriages")
        await self.conn.execute("DROP TABLE waifu_cat")
        await self.conn.execute("""CREATE TABLE waifu_cat(cats_id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL, cat_name TEXT,
            category_cats TEXT CHECK(category_cats IN ('loli','students','MILF')),
            date_cat TEXT, satiety INTEGER DEFAULT 100, miska_risa INTEGER DEFAULT 0,
            mood TEXT,image_cats TEXT,age_days INTEGER DEFAULT 1,last_age_update TEXT,
            last_satiety_update TEXT,last_feed_time TEXT,trust INTEGER DEFAULT 0)""")
        await self.conn.execute("INSERT INTO waifu_cat(cats_id,user_id,category_cats,trust) VALUES(1,1,'loli',42)")
        await self.conn.execute("""CREATE TABLE marriages(marriage_id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id),
            cat_id INTEGER NOT NULL REFERENCES waifu_cat(cats_id),marriage_date TEXT)""")
        await self.conn.execute("INSERT INTO marriages VALUES(1,1,1,'2026-01-01')")
        await self.conn.commit()
        await self.db.add_new_columns()
        cat = await self.db.get_waifu_by_user(1)
        self.assertEqual(cat["trust"], 42)
        self.assertEqual(cat["category_cats"], "kitten")
        self.assertIsNotNone(await self.db.get_marriage(1))
        self.assertEqual(await (await self.conn.execute("PRAGMA foreign_key_check")).fetchall(), [])
        self.assertEqual((await (await self.conn.execute("PRAGMA foreign_keys")).fetchone())[0], 1)
        await self.db.add_new_columns()  # Idempotent restart.

    async def test_monthly_activity_survives_daily_reset(self):
        await self.db.increment_user_activity(1)
        await self.db.increment_user_activity(1)
        await self.db.reset_daily_activity()
        self.assertEqual(await self.db.get_daily_top(), [])
        monthly = await self.db.get_monthly_top()
        self.assertEqual(tuple(monthly[0]), ("Alice", 2))

    async def test_cat_creation_grants_items_in_one_transaction(self):
        self.assertTrue(await self.db.create_waifu_for_user(1))
        quantities = {x["item_key"]: x["quantity"] for x in await self.db.get_hebao_items(1)}
        self.assertEqual(quantities.get("miska_risa"), 2)  # 1 от add_user + 1 от кошки
        self.assertEqual(quantities.get("korm_waifu"), 3)
        self.assertFalse(await self.db.create_waifu_for_user(1))
        quantities = {x["item_key"]: x["quantity"] for x in await self.db.get_hebao_items(1)}
        self.assertEqual(quantities.get("korm_waifu"), 3)

    async def test_concurrent_connection_init_publishes_configured_handle(self):
        handles = await asyncio.gather(*(self.db.init_db() for _ in range(10)))
        self.assertTrue(all(h is handles[0] for h in handles))
        self.assertEqual((await (await handles[0].execute("PRAGMA foreign_keys")).fetchone())[0], 1)

    async def test_existing_username_not_erased(self):
        await self.db.add_user(1, "ignored")
        self.assertEqual(await self.db.get_user_by_username("alice"), 1)

    async def test_context_rolls_back_and_unlocks_on_exception(self):
        with self.assertRaises(RuntimeError):
            async with await self.db.create_connection() as conn:
                await conn.execute("UPDATE users SET reputation=999 WHERE user_id=1")
                raise RuntimeError("abort")
        self.assertEqual(await self.db.get_user_rate(1), 300)


if __name__ == "__main__":
    unittest.main()
