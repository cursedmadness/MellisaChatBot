"""Проверки приюта: репозиторий на SQLite в памяти и хендлеры без сети."""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiogram


def load_database():
    config = ModuleType("config")
    config.MAX_RICE_PER_USER = 6
    config.SHELTER_MAX_DAYS = 30
    config.SHELTER_PRICE_KORM_PER_DAY = 2
    config.SHELTER_PRICE_RICE_PER_DAY = 3
    config.SHELTER_RETURN_SATIETY_BONUS = 20
    config.DAILY_FOOD_AMOUNT = 5
    config.DAILY_FOOD_AMOUNT_IN_SHELTER = 2
    spec = importlib.util.spec_from_file_location(
        "database_shelter_under_test", Path(__file__).resolve().parents[1] / "database.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"config": config}):
        spec.loader.exec_module(module)
    module.DB_NAME = ":memory:"
    return module


def load_shelter(db_module):
    package = ModuleType("routers")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "routers")]
    config = ModuleType("config")
    config.SHELTER_MAX_DAYS = 30
    config.SHELTER_PRICE_KORM_PER_DAY = 2
    config.SHELTER_PRICE_RICE_PER_DAY = 3
    with patch.dict(
        sys.modules,
        {"routers": package, "database": db_module, "config": config, "dotenv": MagicMock()},
    ):
        for name in ("routers.utils", "routers.shelter"):
            sys.modules.pop(name, None)
        return importlib.import_module("routers.shelter")


db = load_database()
shelter = load_shelter(db)


def message(user_id=1, text=""):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, first_name="Alice", username="alice"),
        chat=SimpleNamespace(id=1, type="private"),
        text=text,
        answer=AsyncMock(),
        reply=AsyncMock(),
        bot=SimpleNamespace(),
    )


class ShelterRepoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = await db.init_db()
        await db.create_table()
        await db.add_new_columns()
        await db.add_user(1, "Alice", "alice")
        await db.create_waifu_for_user(1)
        # Чистый инвентарь: убираем выданное при регистрации.
        await self.client.execute("DELETE FROM hebao_items WHERE user_id=1")
        await self.client.commit()

    async def asyncTearDown(self):
        await db.close_db()

    async def test_place_requires_food_and_charges_correctly(self):
        result = await db.place_in_shelter_atomic(1, 2)
        self.assertEqual(result["status"], "no_food")

        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=5)
        result = await db.place_in_shelter_atomic(1, 2)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["food_paid"], 4)  # 2 корма за сутки × 2 дня
        self.assertEqual(result["left"], 1)
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["korm_waifu"], 1)

    async def test_rice_used_when_no_korm(self):
        await db.upsert_hebao_item(1, "miska_risa", "рис", set_value=10)
        result = await db.place_in_shelter_atomic(1, 1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["food_key"], "miska_risa")
        self.assertEqual(result["food_paid"], 3)

    async def test_concurrent_place_only_once(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=20)
        results = await asyncio.gather(
            *(db.place_in_shelter_atomic(1, 1) for _ in range(5))
        )
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("ok"), 1)
        self.assertEqual(statuses.count("already"), 4)
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["korm_waifu"], 18)  # списали ровно 2

    async def test_satiety_frozen_in_shelter(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        await db.place_in_shelter_atomic(1, 3)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.update_cat_state(1, satiety=50, last_satiety_update=(start - timedelta(hours=10)).isoformat())
        cat = await db.decay_waifu_satiety(1, start)
        self.assertEqual(cat["satiety"], 50)
        self.assertTrue(cat["in_shelter"])

    async def test_feeding_blocked_in_shelter(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        await db.place_in_shelter_atomic(1, 1)
        result = await db.feed_waifu_atomic(1, 100, 5)
        self.assertEqual(result["status"], "in_shelter")
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["korm_waifu"], 8)  # еду не списали

    async def test_take_returns_cat_with_proportional_bonus(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        await db.place_in_shelter_atomic(1, 2, now=start)
        await db.update_cat_state(1, satiety=40)
        # Сутки в приюте из двух — половина бонуса.
        result = await db.take_from_shelter_atomic(1, now=start + timedelta(days=1))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["satiety"], 50)
        self.assertIsNone(await db.get_shelter_entry(1))
        cat = await db.get_waifu_by_user(1)
        self.assertFalse(cat["in_shelter"])

    async def test_early_return_refunds_unused_days(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=20)
        await db.place_in_shelter_atomic(1, 10, now=start)  # списали 20 корма
        # Прошло 3 полных суток + 1 час: использовано 4 суток, вернуть должны 6.
        result = await db.take_from_shelter_atomic(1, now=start + timedelta(days=3, hours=1))
        self.assertEqual(result["unused_days"], 7)  # полные 3 суток использованы
        self.assertEqual(result["refunded"], {"korm_waifu": 14})
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["korm_waifu"], 14)

    async def test_return_immediately_refunds_everything(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "miska_risa", "рис", set_value=30)
        await db.place_in_shelter_atomic(1, 3, now=start)  # 9 риса
        await db.update_cat_state(1, satiety=40)
        # Вернули через пару минут: неполные сутки не списываются, бонуса нет.
        result = await db.take_from_shelter_atomic(1, now=start + timedelta(minutes=5))
        self.assertEqual(result["unused_days"], 3)
        self.assertEqual(result["refunded"], {"miska_risa": 9})
        self.assertEqual(result["satiety"], 40)
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["miska_risa"], 30)

    async def test_refund_after_extension_returns_latest_payment_first(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=4)
        await db.upsert_hebao_item(1, "miska_risa", "рис", set_value=30)
        await db.place_in_shelter_atomic(1, 2, now=start)  # 4 корма, корм кончился
        # Продление уходит в рис: 3 за сутки.
        await db.extend_shelter_atomic(1, 2, now=start)
        self.assertEqual(
            {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)},
            {"miska_risa": 24},
        )
        result = await db.take_from_shelter_atomic(1, now=start)
        self.assertEqual(result["unused_days"], 4)
        # Сначала возвращается последняя оплата (рис), затем более ранняя (корм).
        self.assertEqual(result["refunded"], {"miska_risa": 6, "korm_waifu": 4})
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["korm_waifu"], 4)
        self.assertEqual(items["miska_risa"], 30)

    async def test_legacy_entry_backfilled_before_extension(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "miska_risa", "рис", set_value=30)
        await db.place_in_shelter_atomic(1, 3, now=start)  # 9 риса
        # Имитируем запись, созданную до появления учёта платежей.
        await self.client.execute("DELETE FROM shelter_payments")
        await self.client.commit()
        await db.extend_shelter_atomic(1, 2, now=start)  # +6 риса
        result = await db.take_from_shelter_atomic(1, now=start)
        self.assertEqual(result["unused_days"], 5)
        self.assertEqual(result["refunded"], {"miska_risa": 15})
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items["miska_risa"], 30)

    async def test_no_refund_after_full_term(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=4)
        await db.place_in_shelter_atomic(1, 2, now=start)
        returned = await db.process_expired_shelter(start + timedelta(days=2))
        self.assertEqual(returned[0]["unused_days"], 0)
        self.assertEqual(returned[0]["refunded"], {})
        items = {i["item_key"]: i["quantity"] for i in await db.get_hebao_items(1)}
        self.assertEqual(items.get("korm_waifu", 0), 0)

    async def test_expiry_returns_cat_after_deadline(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await db.place_in_shelter_atomic(1, 1, now=start)
        self.assertEqual(await db.process_expired_shelter(start + timedelta(hours=1)), [])
        returned = await db.process_expired_shelter(start + timedelta(days=2))
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0]["user_id"], 1)
        self.assertIsNone(await db.get_shelter_entry(1))

    async def test_extend_charges_and_respects_max(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=100)
        await db.place_in_shelter_atomic(1, 2)
        result = await db.extend_shelter_atomic(1, 3)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["days"], 5)
        self.assertEqual(result["food_paid"], 6)
        too_long = await db.extend_shelter_atomic(1, 30)
        self.assertEqual(too_long["status"], "too_long")

    async def test_extend_without_entry(self):
        self.assertEqual((await db.extend_shelter_atomic(1, 1))["status"], "not_in_shelter")

    async def test_list_and_count(self):
        self.assertEqual(await db.count_shelter_cats(), 0)
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        await db.place_in_shelter_atomic(1, 1)
        self.assertEqual(await db.count_shelter_cats(), 1)
        cats = await db.get_shelter_cats()
        self.assertEqual(len(cats), 1)
        self.assertEqual(cats[0]["cat_name"], "мяу")

    async def test_deleting_cat_clears_shelter_rows(self):
        await db.upsert_hebao_item(1, "korm_waifu", "корм", set_value=10)
        await db.place_in_shelter_atomic(1, 1)
        self.assertTrue(await db.delete_waifu_by_user(1))
        self.assertEqual(await db.count_shelter_cats(), 0)
        cursor = await self.client.execute("SELECT COUNT(*) FROM shelter")
        self.assertEqual((await cursor.fetchone())[0], 0)


class ShelterHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_place_without_days_explains_usage(self):
        msg = message()
        with patch.object(shelter, "place_in_shelter_atomic", AsyncMock()) as place:
            await shelter.shelter_place(msg, None)
        place.assert_not_awaited()
        self.assertIn("/shelter_place", msg.answer.await_args.args[0])

    async def test_place_reports_missing_food(self):
        msg = message()
        result = {"status": "no_food", "need": {"korm_waifu": 4, "miska_risa": 6},
                  "have": {"korm_waifu": 1}}
        with patch.object(shelter, "place_in_shelter_atomic", AsyncMock(return_value=result)):
            await shelter.shelter_place(msg, SimpleNamespace(args="2"))
        text = msg.answer.await_args.args[0]
        self.assertIn("Не хватает еды", text)
        self.assertIn("4", text)

    async def test_place_escapes_cat_name(self):
        msg = message()
        result = {"status": "ok", "cat_name": "<script>", "days": 1,
                  "expires_at": "2026-01-02T00:00:00+00:00", "food_key": "korm_waifu",
                  "food_paid": 2, "left": 3}
        with patch.object(shelter, "place_in_shelter_atomic", AsyncMock(return_value=result)):
            await shelter.shelter_place(msg, SimpleNamespace(args="1"))
        text = msg.answer.await_args.args[0]
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    async def test_list_empty_and_filled(self):
        with patch.object(shelter, "process_expired_shelter", AsyncMock()), \
             patch.object(shelter, "get_shelter_cats", AsyncMock(return_value=[])), \
             patch.object(shelter, "count_shelter_cats", AsyncMock(return_value=0)):
            msg = message()
            await shelter.shelter_list(msg)
        self.assertIn("пуст", msg.answer.await_args.args[0])

        cats = [{"user_id": 7, "cat_name": "<bad>", "expires_at": "2026-01-05T00:00:00+00:00",
                 "satiety": 80, "nickname": "Bob"}]
        with patch.object(shelter, "process_expired_shelter", AsyncMock()), \
             patch.object(shelter, "get_shelter_cats", AsyncMock(return_value=cats)), \
             patch.object(shelter, "count_shelter_cats", AsyncMock(return_value=1)):
            msg = message()
            await shelter.shelter_list(msg)
        text = msg.answer.await_args.args[0]
        self.assertIn("&lt;bad&gt;", text)
        self.assertNotIn("<bad>", text)
        self.assertIn("кошка", text)

    async def test_my_without_entry(self):
        with patch.object(shelter, "process_expired_shelter", AsyncMock()), \
             patch.object(shelter, "get_shelter_entry", AsyncMock(return_value=None)):
            msg = message()
            await shelter.shelter_my(msg)
        self.assertIn("не в приюте", msg.answer.await_args.args[0])

    def test_price_and_left_text(self):
        prices = shelter.shelter_price(2)
        self.assertEqual(prices, {"korm_waifu": 4, "miska_risa": 6})
        future = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).isoformat()
        self.assertIn("дн.", shelter._left_text(future))
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertIn("истёк", shelter._left_text(past))


if __name__ == "__main__":
    unittest.main()
