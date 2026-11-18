"""Регрессии вывода: импорт не читает config, dotenv и рабочую базу."""
import importlib
import sys
import unittest
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def load_routers():
    db = MagicMock()
    package = ModuleType("routers")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / 'routers')]
    config = ModuleType("config")
    for name, value in {
        "STATS_ENABLED_CHATS": [123], "DAILY_TOP_LIMIT": 5,
        "MONTHLY_TOP_LIMIT": 30, "DAILY_REPORT_TIME_HOUR": 20,
        "DAILY_REPORT_TIME_MINUTE": 0, "MONTHLY_REPORT_TIME_HOUR": 20,
        "MONTHLY_REPORT_TIME_MINUTE": 0, "STATS_LEADERBOARD_LIMIT": 10,
    }.items():
        setattr(config, name, value)
    strings = ModuleType("routers.strings")
    strings.HELP_TEXT = "help"
    names = ["utils", "weather_service", "user_commands", "hebao", "waifu_rp", "activity_commands"]
    # Убираем ранее импортированные роутеры внутри подмены, затем возвращаем sys.modules.
    # Сторонние зависимости импортируем до снимка sys.modules (numpy нельзя перезагрузить).
    import aiogram  # noqa: F401
    with patch.dict(sys.modules, {"database": db, "config": config, "routers": package,
                                 "dotenv": MagicMock(), "routers.strings": strings}):
        for name in names:
            sys.modules.pop("routers." + name, None)
        modules = [importlib.import_module("routers." + name) for name in names]
    return modules


utils, weather, users, hebao, rp, activity = load_routers()


def message(text="", reply=None):
    return SimpleNamespace(
        text=text, caption=None, reply_to_message=reply,
        from_user=SimpleNamespace(id=12345, first_name="<Alice>&", full_name="<Alice>&", username="alice"),
        chat=SimpleNamespace(id=123, type="private"),
        answer=AsyncMock(), reply=AsyncMock(),
    )


class ParsingTests(unittest.IsolatedAsyncioTestCase):
    def test_command_bot_is_not_target(self):
        for text, expected in [
            ("/hebao@some_bot", None),
            ("/hebao@some_bot @alice", "@alice"),
            ("/hebao@bot12345 987654", 987654),
            ("/hebao@some_bot https://t.me/alice", "@alice"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(utils.extract_user_from_text(message(text)), expected)

    def test_reply_has_priority(self):
        reply = SimpleNamespace(from_user=SimpleNamespace(id=98765))
        self.assertEqual(utils.extract_user_from_text(message("/hebao@some_bot @alice", reply)), 98765)

    def test_extract_args_boundaries_and_bot_suffix(self):
        for text, expected in [
            ("/set_city@SomeBot New York", "New York"),
            ("/set_city@SomeBot", ""),
            (".город Москва", "Москва"),
            ("городской", "городской"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(utils.extract_args(text, ["/set_city", ".город", "город"]), expected)

    async def test_numeric_target_and_command_args(self):
        for text, command in [
            ("хэбао 98765", None),
            ("/hebao@some_bot 98765", SimpleNamespace(args="98765")),
        ]:
            self.assertEqual((await utils.extract_target_user(message(text), command))[0], 98765)
        with patch.object(utils, "resolve_user_id", AsyncMock(return_value=98765)) as resolve:
            await utils.extract_target_user(message("+рейтинг 100 @alice"))
            resolve.assert_awaited_once_with("@alice")
        self.assertIsNone((await utils.extract_target_user(message("/hebao@some_bot"), SimpleNamespace(args=None)))[0])


class PresentationTests(unittest.IsolatedAsyncioTestCase):
    def test_user_link_escapes_label(self):
        link = utils.get_user_link(12345, '<b>A&B</b>')
        self.assertIn('&lt;b&gt;A&amp;B&lt;/b&gt;', link)
        self.assertEqual(link.count('<a '), 1)

    async def test_profile_escapes_database_values(self):
        raw = '<b>A&B</b>'
        with patch.object(utils, 'get_user_profile', AsyncMock(return_value=dict.fromkeys(
            ['nickname', 'description', 'city', 'activity'], raw))), patch.object(
                utils, 'get_user_rate', AsyncMock(return_value=10)):
            text = await utils.get_profile_text(12345)
        self.assertEqual(text.count(escape(raw)), 4)
        self.assertNotIn(raw, text)

    async def test_registration_stores_raw_nickname_and_city(self):
        raw = '<b>A&B</b>'
        for handler, setter_name in [(users.process_nickname, 'set_user_nickname'),
                                     (users.process_city, 'set_user_city')]:
            msg = message(raw)
            state = SimpleNamespace(set_state=AsyncMock())
            with patch.object(users, setter_name, AsyncMock()) as setter:
                await handler(msg, state)
                setter.assert_awaited_once_with(12345, raw)
            self.assertIn(escape(raw), msg.answer.await_args.args[0])
            self.assertNotIn(raw, msg.answer.await_args.args[0])

    async def test_setters_store_raw_arguments(self):
        raw = '<b>A&B</b>'
        for handler, setter, command in [
            (users.set_nickname_handler, 'set_user_nickname', '/set_nickname'),
            (users.set_city_command_handler, 'set_user_city', '/set_city'),
            (users.set_description_handler, 'set_user_description', '/set_description'),
        ]:
            msg = message(command + '@SomeBot ' + raw)
            with patch.object(users, setter, AsyncMock()) as save:
                if handler is users.set_city_command_handler:
                    await handler(msg, SimpleNamespace(clear=AsyncMock()))
                else:
                    await handler(msg)
                save.assert_awaited_once_with(12345, raw)
            self.assertNotIn(raw, msg.answer.await_args.args[0])

    async def test_user_supplied_names_in_other_responses(self):
        raw = '<Alice>&'
        for handler, getter in [(users.show_my_nickname, 'get_user_nickname'),
                                (users.show_my_description, 'get_user_description')]:
            msg = message()
            with patch.object(users, getter, AsyncMock(return_value=raw)):
                await handler(msg)
            self.assertIn(escape(raw), msg.answer.await_args.args[0])
        msg = message('мой ид')
        await users.show_user_id(msg)
        self.assertIn(escape(raw), msg.reply.await_args.args[0])

    async def test_hebao_does_not_nest_links(self):
        msg = message('хэбао 98765')
        link = utils.get_user_link(98765, '<Bob>&')
        with patch.object(hebao, 'get_user_display_name', AsyncMock(return_value=link)), patch.object(
            hebao, 'get_hebao_overview', AsyncMock(return_value=[
                {'item_key': 'unknown', 'item_name': '<Bowl>&', 'quantity': 1}])):
            await hebao.show_hebao_command(msg)
        text = msg.answer.await_args.args[0]
        self.assertEqual(text.count('<a '), 1)
        self.assertIn(link, text)
        self.assertIn('&lt;bowl&gt;&amp;', text)

    def test_weather_escapes_city_and_fallback_description(self):
        data = {'main': {'temp': 10, 'feels_like': 9, 'humidity': 50},
                'wind': {'speed': 1}, 'weather': [{'id': 999, 'description': '<Rain>&'}]}
        text = weather.format_weather_message(data, '<City>&')
        self.assertIn('&lt;city&gt;&amp;', text)
        self.assertIn('&lt;rain&gt;&amp;', text)

    async def test_zero_coordinates_valid_and_missing_longitude_invalid(self):
        for coords, called in [((0, 0), True), ((0, 10), True), ((10, 0), True),
                               ((None, 0), False), ((0, None), False)]:
            with self.subTest(coords=coords), patch.object(weather, 'get_coordinates', AsyncMock(return_value=coords)), patch.object(
                weather, 'get_weather', AsyncMock(return_value=None)) as fetch:
                await weather.get_weather_string('city')
                self.assertEqual(fetch.await_count, int(called))

    async def test_rp_zero_coordinates_and_escaped_values(self):
        with patch.object(rp, 'get_user_nickname', AsyncMock(return_value='<Nick>&')), patch.object(
            rp, 'get_user_city', AsyncMock(return_value='<City>&')), patch.object(
            rp, 'get_coordinates', AsyncMock(return_value=(0, 0))), patch.object(
            rp, 'get_weather', AsyncMock(return_value={'main': {'temp': 30}, 'weather': [{'id': 800}]})) as fetch, patch.object(
            rp.random, 'choice', return_value='{cat_name} {nickname} {city}'):
            text = await rp.generate_waifu_rp_message(12345, '<Cat>&')
        fetch.assert_awaited_once_with(0, 0)
        self.assertEqual(text, '<b>&lt;Cat&gt;&amp;</b> &lt;Nick&gt;&amp; &lt;city&gt;&amp;')

    async def test_reports_escape_nicknames(self):
        raw = '<Nick>&'
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(activity, 'get_daily_top', AsyncMock(return_value=[(raw, 1)])), patch.object(
            activity, 'get_highly_active_users', AsyncMock(return_value=[])), patch.object(
            activity, 'reset_daily_activity', AsyncMock()):
            await activity.publish_daily_report(bot)
        with patch.object(activity, 'get_monthly_top', AsyncMock(return_value=[(raw, 1)])):
            await activity.publish_monthly_report(bot)
        msg = message()
        with patch.object(activity, 'get_chat_leaderboard', AsyncMock(return_value=[(raw, 1)])):
            await activity.show_stats_handler(msg)
        texts = [call.kwargs['text'] for call in bot.send_message.await_args_list]
        texts.append(msg.answer.await_args.args[0])
        self.assertEqual(len(texts), 4)
        for text in texts:
            self.assertIn(escape(raw), text)
            self.assertNotIn(raw, text)


class MonthlyScheduleTests(unittest.TestCase):
    def test_month_end_before_at_and_after_target(self):
        for now, expected in [
            ((2024, 1, 15, 0, 0), (2024, 1, 31)),
            ((2024, 1, 31, 19, 59), (2024, 1, 31)),
            ((2024, 1, 31, 20, 0), (2024, 2, 29)),
            ((2024, 2, 29, 21, 0), (2024, 3, 31)),
            ((2025, 1, 31, 21, 0), (2025, 2, 28)),
            ((2024, 4, 30, 21, 0), (2024, 5, 31)),
            ((2024, 12, 31, 21, 0), (2025, 1, 31)),
        ]:
            with self.subTest(now=now):
                current = datetime(*now, tzinfo=timezone.utc)
                target = activity.next_monthly_report_time(current)
                self.assertEqual(target, datetime(*expected, 20, tzinfo=timezone.utc))
                self.assertGreater(target, current)


if __name__ == '__main__':
    unittest.main()
