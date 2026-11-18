"""Проверки монитора простоев Telegram без сети и без рабочей базы."""
import asyncio
import logging
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import telegram_monitor as monitor_module


def bot_double():
    return SimpleNamespace(send_message=AsyncMock())


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_failure_is_silent(self):
        bot = bot_double()
        monitor = monitor_module.ConnectionMonitor(bot, -100, alert_after=timedelta(minutes=5))
        monitor.mark_error()
        await monitor.mark_connected()
        # Короткое мигание: тревоги и отчёта нет, чтобы не спамить.
        bot.send_message.assert_not_awaited()
        self.assertIsNone(monitor._failed_at)

    async def test_recovery_after_alert_is_reported(self):
        bot = bot_double()
        monitor = monitor_module.ConnectionMonitor(bot, -100, alert_after=timedelta(minutes=5))
        monitor.mark_error()
        monitor._last_alert_at = datetime.now(timezone.utc)
        await monitor.mark_connected()
        self.assertEqual(bot.send_message.await_count, 1)
        self.assertIn("восстановлена", bot.send_message.await_args.args[1])

    async def test_long_failure_triggers_single_alert(self):
        bot = bot_double()
        monitor = monitor_module.ConnectionMonitor(
            bot, -100, alert_after=timedelta(0), repeat_every=timedelta(minutes=60)
        )
        monitor._last_error = "TelegramNetworkError: timeout"
        monitor.mark_error()
        monitor.start()
        try:
            for _ in range(60):
                if bot.send_message.await_count:
                    break
                await asyncio.sleep(0.5)
        finally:
            await monitor.stop()
        self.assertEqual(bot.send_message.await_count, 1)
        payload = bot.send_message.await_args.args[1]
        self.assertIn("не получает сообщения", payload)
        self.assertIn("timeout", payload)
        self.assertEqual(bot.send_message.await_args.args[0], -100)

    async def test_no_chat_id_sends_nothing(self):
        bot = bot_double()
        monitor = monitor_module.ConnectionMonitor(bot, None, alert_after=timedelta(0))
        monitor.mark_error()
        await monitor.mark_connected()
        bot.send_message.assert_not_awaited()

    async def test_send_failure_does_not_break_monitor(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("no network")))
        monitor = monitor_module.ConnectionMonitor(bot, -100)
        monitor.mark_error()
        monitor._last_alert_at = None
        await monitor._send("<b>x</b>")  # не должно бросить
        self.assertIsNotNone(monitor._failed_at)

    async def test_log_handler_reacts_to_polling_lines(self):
        bot = bot_double()
        monitor = monitor_module.ConnectionMonitor(bot, -100)
        handler = monitor_module._MonitorLogHandler(monitor)
        record = logging.LogRecord(
            "aiogram.dispatcher", logging.ERROR, __file__, 1,
            "Failed to fetch updates - %s: %s", ("TelegramNetworkError", "timeout"), None,
        )
        handler.emit(record)
        self.assertIsNotNone(monitor._failed_at)
        self.assertIn("timeout", monitor._last_error)


if __name__ == "__main__":
    unittest.main()
