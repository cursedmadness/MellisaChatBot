"""Проверки хендлеров без config, Telegram и рабочей базы."""
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiogram


def load_waifu():
    package = ModuleType("routers")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "routers")]
    db = MagicMock()
    with patch.dict(sys.modules, {"routers": package, "database": db}):
        for name in ("routers.utils", "routers.waifu_cat"):
            sys.modules.pop(name, None)
        return importlib.import_module("routers.waifu_cat")


waifu = load_waifu()


def message():
    return SimpleNamespace(from_user=SimpleNamespace(id=1, first_name="Alice", username="alice"), answer=AsyncMock())


class WaifuHandlersTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_row_reloads_full_cat(self):
        row = {"user_id": 1, "cat_name": "Alice"}
        fresh = {"user_id": 1, "satiety": 30, "last_satiety_update": "2026-01-01"}
        with patch.object(waifu, "decay_waifu_satiety", AsyncMock(return_value=fresh)) as decay:
            self.assertTrue(await waifu._apply_satiety_decay(row))
        decay.assert_awaited_once_with(1)
        self.assertEqual(row["satiety"], 30)

    async def test_feed_delegates_to_atomic_operation_and_escapes_name(self):
        msg = message()
        result = {"status": "ok", "cat_name": "<bad>&", "trust": 10,
                  "left_qty": 0, "item_key": "korm_waifu"}
        with patch.object(waifu, "feed_waifu_atomic", AsyncMock(return_value=result)) as feed:
            await waifu.feed_waifu_korm(msg)
        self.assertEqual(feed.await_count, 1)
        text = msg.answer.await_args.args[0]
        self.assertIn("&lt;bad&gt;&amp;", text)
        self.assertNotIn("<bad>", text)

    async def test_feed_cooldown_no_success_message(self):
        msg = message()
        with patch.object(waifu, "feed_waifu_atomic", AsyncMock(return_value={"status": "cooldown", "remaining_seconds": 3600})):
            await waifu.feed_waifu_korm(msg)
        msg.answer.assert_awaited_once()
        self.assertIn("Следующее кормление", msg.answer.await_args.args[0])

    async def test_food_claim_uses_persistent_user_and_atomic_claim(self):
        msg = message()
        with patch.object(waifu, "add_user", AsyncMock()) as add, patch.object(waifu, "claim_daily_food", AsyncMock(return_value=False)) as claim:
            await waifu.get_daily_food_command(msg)
        add.assert_awaited_once_with(1, "Alice", "alice")
        self.assertEqual(claim.await_count, 1)
        self.assertIn("уже получали", msg.answer.await_args.args[0])

    def test_profile_escapes_names(self):
        text = waifu._format_waifu_profile({"cat_name": "<bad>", "mood": "<&>"})
        self.assertIn("&lt;bad&gt;", text)
        self.assertNotIn("<bad>", text)


if __name__ == "__main__":
    unittest.main()
