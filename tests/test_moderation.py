"""Изолированные регрессии: без конфигурации, запросов в Telegram и рабочей базы."""
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from contextlib import ExitStack
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_isolated_handlers():
    database = types.ModuleType("database")
    for path in ("routers/utils.py", "routers/moderation_commands.py", "routers/admin_commands.py"):
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "database":
                for alias in node.names:
                    setattr(database, alias.name, AsyncMock(name=alias.name))
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"database": database}))
        utils = load_module("_moderation_test_utils", "routers/utils.py")
        stack.enter_context(patch.dict(sys.modules, {"routers.utils": utils}))
        moderation = load_module("_moderation_test_handlers", "routers/moderation_commands.py")
        stack.enter_context(patch.dict(sys.modules, {"routers.moderation_commands": moderation}))
        admin = load_module("_moderation_test_admin", "routers/admin_commands.py")
    return moderation, admin


moderation, admin = load_isolated_handlers()


def make_message(text="/бан 123456 10 причина", reply=False, chat_type="supergroup"):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=42, first_name="<Admin>&"),
        chat=SimpleNamespace(id=-1001, type=chat_type, title="<Chat>&",
                             get_member=AsyncMock(), ban=AsyncMock(),
                             unban=AsyncMock(), restrict=AsyncMock()),
        reply_to_message=SimpleNamespace(from_user=SimpleNamespace(id=123456, first_name="Target")) if reply else None,
        reply=AsyncMock(), answer=AsyncMock(), bot=SimpleNamespace(id=99),
    )


class ArgumentTests(unittest.TestCase):
    def test_target_not_duration(self):
        cases = [
            ("/бан 123456", False, None, "Не указана"),
            ("/мут 123456 10 спам", False, 10, "спам"),
            ("бан @target 2 часа спам", False, 120, "спам"),
            ("/мут https://t.me/target 1 день спам", False, 1440, "спам"),
            ("/бан 30 спам", True, 30, "спам"),
            ("/мут час спам", True, 60, "спам"),
            ("/бан @target 1 неделя спам", False, 10080, "спам"),
        ]
        for text, reply, duration, reason in cases:
            with self.subTest(text=text):
                message = make_message(text, reply=reply)
                self.assertEqual(moderation.parse_moderation_args(message, None, 123456), (duration, reason))
                command = SimpleNamespace(args=text.partition(" ")[2])
                self.assertEqual(moderation.parse_moderation_args(message, command, 123456), (duration, reason))

    def test_duration_bounds(self):
        for duration in ("0", "0 минут", "367 дней", "527041"):
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(ValueError, "от 1 минуты до 366 дней"):
                    moderation.parse_moderation_args(make_message(f"/бан 123456 {duration}"), None, 123456)
        for duration, expected in [("1", 1), ("366 дней", 527040)]:
            self.assertEqual(moderation.parse_moderation_args(make_message(f"/бан 123456 {duration}"), None, 123456), (expected, "Не указана"))


class ModerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_duration_rejected_before_api_or_database(self):
        for handler in (moderation.ban_command, moderation.mute_command):
            for duration in ("0", "367 дней", "527041"):
                with self.subTest(handler=handler.__name__, duration=duration):
                    message = make_message(f"/бан 123456 {duration}")
                    with patch.object(moderation, "resolve_user_id", AsyncMock(return_value=123456)), patch.object(moderation, "add_punishment", AsyncMock()) as add_punishment:
                        await handler(message, SimpleNamespace(send_message=AsyncMock()))
                        message.chat.ban.assert_not_awaited()
                        message.chat.restrict.assert_not_awaited()
                        add_punishment.assert_not_awaited()
                        message.reply.assert_awaited_once()
                        self.assertIn("от 1 минуты до 366 дней", message.reply.await_args.args[0])

    async def test_moderator_rights(self):
        message = make_message()
        with patch.object(moderation, "is_admin", AsyncMock(return_value=False)):
            for status, restrict, allowed in [("administrator", False, False), ("administrator", True, True), ("creator", None, True), ("member", True, False)]:
                message.chat.get_member.return_value = SimpleNamespace(status=status, can_restrict_members=restrict)
                self.assertEqual(await moderation.moderator_filter(message), allowed)
        message.chat.get_member.reset_mock()
        with patch.object(moderation, "is_admin", AsyncMock(return_value=True)):
            self.assertTrue(await moderation.moderator_filter(message))
            message.chat.get_member.assert_not_awaited()

    async def test_ban_and_mute_utc_and_html(self):
        for handler, method in [(moderation.ban_command, "ban"), (moderation.mute_command, "restrict")]:
            message = make_message("/бан 123456 10 <reason>&")
            bot = SimpleNamespace(send_message=AsyncMock())
            with ExitStack() as stack:
                for name, value in [("resolve_user_id", 123456), ("add_punishment", True), ("reset_user_rating", None), ("get_user_display_name", "Target")]:
                    stack.enter_context(patch.object(moderation, name, AsyncMock(return_value=value)))
                await handler(message, bot)
                kwargs = getattr(message.chat, method).await_args.kwargs
                self.assertEqual(kwargs["until_date"].tzinfo, timezone.utc)
                self.assertEqual(moderation.add_punishment.await_args.args[-1], 10)
                self.assertEqual(moderation.add_punishment.await_args.args[3], "<reason>&")
            payload = bot.send_message.await_args.args[1]
            self.assertNotIn("<Chat>", payload)
            self.assertNotIn("<Admin>", payload)
            self.assertNotIn("<reason>", payload)

    async def test_unban_only_banned(self):
        message = make_message()
        with patch.object(moderation, "resolve_user_id", AsyncMock(return_value=123456)), patch.object(moderation, "remove_punishment", AsyncMock(return_value=True)), patch.object(moderation, "get_user_display_name", AsyncMock(return_value="Target")):
            await moderation.unban_command(message, SimpleNamespace(send_message=AsyncMock()))
        message.chat.unban.assert_awaited_once_with(user_id=123456, only_if_banned=True)

    async def test_dm_handlers_reachable_without_admin_check(self):
        self.assertFalse(moderation.moderation_router.message._handler.filters)
        for text, callback in [("причина бана", moderation.dm_ban_reason), ("причина мута", moderation.dm_mute_reason)]:
            message = make_message(text, chat_type="private")
            details = {"reason": "<reason>&", "moderator_name": "<mod>&", "expires_at": "<expiry>"}
            with patch.object(moderation, "get_last_punishment_details", AsyncMock(return_value=details)), patch.object(moderation, "is_admin", AsyncMock(side_effect=AssertionError("DM requires no admin"))):
                await moderation.moderation_router.propagate_event("message", message, bot=SimpleNamespace())
                message.reply.assert_awaited_once()
                payload = message.reply.await_args.args[0]
                self.assertIn("&lt;reason&gt;&amp;", payload)
                self.assertIn("&lt;mod&gt;&amp;", payload)
                moderation.is_admin.assert_not_awaited()

    async def test_group_handler_rejects_admin_without_restrict_permission(self):
        message = make_message("бан 123456 10")
        message.chat.get_member.return_value = SimpleNamespace(status="administrator", can_restrict_members=False)
        with patch.object(moderation, "is_admin", AsyncMock(return_value=False)), patch.object(moderation, "resolve_user_id", AsyncMock()) as resolve:
            await moderation.moderation_router.propagate_event("message", message, bot=SimpleNamespace())
            resolve.assert_not_awaited()
            message.chat.ban.assert_not_awaited()

    async def test_third_warning_autoban_utc(self):
        message = make_message("/варн 123456 <reason>&")
        bot = SimpleNamespace(send_message=AsyncMock())
        with ExitStack() as stack:
            values = [("resolve_user_id", 123456), ("add_warning", True), ("get_user_display_name", "Target"), ("get_warnings_count", 3), ("get_user_rate", 0), ("update_user_rate", False), ("add_punishment", True), ("reset_user_rating", None), ("check_and_apply_auto_moderation", None)]
            for name, value in values:
                stack.enter_context(patch.object(moderation, name, AsyncMock(return_value=value)))
            await moderation.warn_command(message, bot, SimpleNamespace(args="<reason>&"))
            message.chat.ban.assert_awaited_once()
            self.assertEqual(message.chat.ban.await_args.kwargs["until_date"].tzinfo, timezone.utc)
            self.assertIn("&lt;reason&gt;&amp;", bot.send_message.await_args.args[1])

    async def test_automute_utc(self):
        bot = SimpleNamespace(id=99, restrict_chat_member=AsyncMock(), send_message=AsyncMock())
        with patch.object(moderation, "get_user_rate", AsyncMock(return_value=0)), patch.object(moderation, "get_active_punishments", AsyncMock(return_value=[])), patch.object(moderation, "add_punishment", AsyncMock()), patch.object(moderation, "get_user_display_name", AsyncMock(return_value="Target")):
            await moderation.check_and_apply_auto_moderation(123456, -1001, bot)
        self.assertEqual(bot.restrict_chat_member.await_args.kwargs["until_date"].tzinfo, timezone.utc)

    async def test_rate_zero_preserved_existing_user_not_overwritten(self):
        for multiply in (1, -1):
            message = make_message("+рейтинг 10", chat_type="private")
            with patch.object(admin, "get_user_profile", AsyncMock(return_value={"nickname": "Existing"})), patch.object(admin, "add_user", AsyncMock()) as add_user, patch.object(admin, "get_user_rate", AsyncMock(return_value=0)), patch.object(admin, "update_user_rate", AsyncMock(return_value=False)) as update, patch.object(admin, "get_rate_display", AsyncMock(return_value="rate")):
                await admin._modify_rate(message, None, multiply)
                update.assert_awaited_once_with(42, multiply * 10)
                add_user.assert_not_awaited()

    async def test_missing_user_created(self):
        with patch.object(admin, "get_user_profile", AsyncMock(return_value=None)), patch.object(admin, "add_user", AsyncMock()) as add_user:
            await admin._ensure_user_exists(123456, "New")
            add_user.assert_awaited_once_with(123456, "New")


if __name__ == "__main__":
    unittest.main()
