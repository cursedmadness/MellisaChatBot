"""Проверки модуля помощи: разделы, кнопки, навигация. Без сети и базы."""
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiogram
from aiogram.exceptions import TelegramBadRequest


def load_help():
    package = ModuleType("routers")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "routers")]
    with patch.dict(sys.modules, {"routers": package, "database": MagicMock()}):
        sys.modules.pop("routers.help", None)
        return importlib.import_module("routers.help")


help_module = load_help()


def message():
    return SimpleNamespace(
        from_user=SimpleNamespace(id=1, first_name="Alice"),
        chat=SimpleNamespace(id=1, type="private"),
        answer=AsyncMock(),
        reply=AsyncMock(),
    )


class HelpContentTests(unittest.TestCase):
    def test_every_section_renders(self):
        for section in help_module.SECTION_ORDER:
            with self.subTest(section=section):
                text, keyboard = help_module.render(section)
                self.assertGreater(len(text), 100)
                self.assertTrue(keyboard.inline_keyboard)

    def test_main_screen_lists_all_sections(self):
        text, keyboard = help_module.render("main")
        buttons = [b for row in keyboard.inline_keyboard for b in row]
        callbacks = {b.callback_data for b in buttons}
        expected = {f"help:{key}" for key in help_module.SECTION_ORDER}
        self.assertEqual(callbacks, expected)
        self.assertIn("/start", text)
        start_text, _ = help_module.render("start")
        self.assertIn("500", start_text)

    def test_unknown_section_falls_back_to_main(self):
        text, _ = help_module.render("нет-такого")
        self.assertEqual(text, help_module.START_MESSAGE)

    def test_section_keyboard_has_back_and_neighbours(self):
        _, keyboard = help_module.render("cat")
        callbacks = {b.callback_data for row in keyboard.inline_keyboard for b in row}
        self.assertIn("help:main", callbacks)
        self.assertIn("help:profile", callbacks)  # сосед слева
        self.assertIn("help:shelter", callbacks)  # сосед справа

    def test_admin_commands_are_not_described(self):
        """Справка для граждан не должна раскрывать модерацию."""
        forbidden = ("/бан", "/мут", "/варн", "рассылка", "delete_user", "сбросить рис")
        for section in help_module.SECTION_ORDER:
            text, _ = help_module.render(section)
            for marker in forbidden:
                with self.subTest(section=section, marker=marker):
                    self.assertNotIn(marker, text)

    def test_commands_match_real_handlers(self):
        """В справке нет команд, которых нет в коде."""
        profile, _ = help_module.render("profile")
        self.assertIn("анкета", profile)
        self.assertNotIn("/profile", profile)  # такой команды нет
        self.assertIn(".ник", profile)
        self.assertIn("мой рейтинг", profile)


class HelpHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_handler_sends_keyboard(self):
        msg = message()
        await help_module.help_main(msg)
        msg.answer.assert_awaited_once()
        self.assertIn("Помощь", msg.answer.await_args.args[0])
        self.assertIsNotNone(msg.answer.await_args.kwargs["reply_markup"])

    async def test_section_handlers_work(self):
        for handler, marker in [
            (help_module.help_profile, "Профиль"),
            (help_module.help_cat, "Кошко-жена"),
            (help_module.help_shelter, "Приют"),
            (help_module.help_economy, "хэбао"),
            (help_module.help_activity, "Активность"),
            (help_module.help_rules, "Правила"),
        ]:
            with self.subTest(handler=handler.__name__):
                msg = message()
                await handler(msg)
                msg.answer.assert_awaited_once()
                self.assertIn(marker, msg.answer.await_args.args[0])

    async def test_navigation_edits_message(self):
        callback = SimpleNamespace(
            data="help:cat",
            from_user=SimpleNamespace(id=1),
            message=SimpleNamespace(
                edit_text=AsyncMock(), answer=AsyncMock()
            ),
            answer=AsyncMock(),
        )
        await help_module.help_navigation(callback)
        callback.message.edit_text.assert_awaited_once()
        self.assertIn("Кошко-жена", callback.message.edit_text.await_args.args[0])
        callback.answer.assert_awaited_once()

    async def test_navigation_ignores_unchanged_message(self):
        error = TelegramBadRequest(method=MagicMock(), message="message is not modified")
        callback = SimpleNamespace(
            data="help:main",
            from_user=SimpleNamespace(id=1),
            message=SimpleNamespace(
                edit_text=AsyncMock(side_effect=error), answer=AsyncMock()
            ),
            answer=AsyncMock(),
        )
        await help_module.help_navigation(callback)
        callback.message.answer.assert_not_awaited()
        callback.answer.assert_awaited_once()

    async def test_navigation_sends_new_message_when_edit_fails(self):
        error = TelegramBadRequest(method=MagicMock(), message="message to edit not found")
        callback = SimpleNamespace(
            data="help:profile",
            from_user=SimpleNamespace(id=1),
            message=SimpleNamespace(
                edit_text=AsyncMock(side_effect=error), answer=AsyncMock()
            ),
            answer=AsyncMock(),
        )
        await help_module.help_navigation(callback)
        callback.message.answer.assert_awaited_once()

    async def test_navigation_survives_broken_callback(self):
        callback = SimpleNamespace(
            data="help:cat",
            from_user=SimpleNamespace(id=1),
            message=None,
            answer=AsyncMock(),
        )
        await help_module.help_navigation(callback)
        callback.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
