"""Монитор соединения с Telegram: сообщает в DEV_CHAT_ID о долгом простое.

Подписка идёт на логгер aiogram.dispatcher, так как именно он пишет строки
«Failed to fetch updates» и «Connection established» при поллинге.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

# Через сколько после отказа сообщить о проблеме.
ALERT_AFTER = timedelta(minutes=5)
# Не чаще одной тревоги в этот интервал, чтобы не спамить при длинном сбое.
REPEAT_EVERY = timedelta(minutes=60)
# Сколько хранить последнюю сетевую ошибку в сообщении.
ERROR_MAX_LENGTH = 300


class ConnectionMonitor:
    """Следит за попытками получения updates и уведомляет о простоях."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int | None,
        *,
        alert_after: timedelta = ALERT_AFTER,
        repeat_every: timedelta = REPEAT_EVERY,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._alert_after = alert_after
        self._repeat_every = repeat_every
        self._failed_at: datetime | None = None
        self._last_alert_at: datetime | None = None
        self._checker: asyncio.Task | None = None
        self._last_error = "нет данных"

    # --- отслеживание -------------------------------------------------
    def start(self) -> None:
        if self._checker is not None and not self._checker.done():
            return
        self._checker = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        if self._checker is not None:
            self._checker.cancel()
            await asyncio.gather(self._checker, return_exceptions=True)
            self._checker = None

    def mark_error(self) -> None:
        if self._failed_at is None:
            self._failed_at = datetime.now(timezone.utc)
            logger.warning("Монитор: связь с Telegram потеряна, жду восстановления")

    async def mark_connected(self) -> None:
        """Вызывается, когда поллинг снова получил updates."""
        if self._failed_at is None:
            return
        failed_at, alerted = self._failed_at, self._last_alert_at is not None
        self._failed_at, self._last_alert_at = None, None
        downtime = datetime.now(timezone.utc) - failed_at
        if not alerted and downtime < self._alert_after:
            # Короткое мигание связи: в чат не пишем, только в лог.
            logger.info("Монитор: связь восстановилась после %s", _humanize(downtime))
            return
        await self._send(
            "<b>✅ Связь с Telegram восстановлена</b>\n\n"
            f"Простой: <b>{_humanize(downtime)}</b>\n"
            f"Начало сбоя: {failed_at.astimezone().strftime('%d.%m %H:%M:%S')}"
        )

    async def _watch_loop(self) -> None:
        """Поднимает тревогу, если сбой длится дольше порога."""
        while True:
            await asyncio.sleep(15)
            if self._failed_at is None:
                continue
            now = datetime.now(timezone.utc)
            downtime = now - self._failed_at
            if downtime < self._alert_after:
                continue
            if self._last_alert_at is not None and now - self._last_alert_at < self._repeat_every:
                continue
            self._last_alert_at = now
            await self._send(
                "<b>🔴 Бот не получает сообщения</b>\n\n"
                f"Telegram API не отвечает: <b>{_humanize(downtime)}</b>\n"
                f"Начало: {self._failed_at.astimezone().strftime('%d.%m %H:%M:%S')}\n"
                f"Последняя ошибка: <code>{escape(self._last_error)}</code>"
            )

    # --- отправка -----------------------------------------------------
    async def _send(self, text: str) -> None:
        if not self._chat_id:
            return
        try:
            await self._bot.send_message(self._chat_id, text)
            logger.info("Монитор: уведомление отправлено в чат %s", self._chat_id)
        except TelegramAPIError as error:
            logger.warning("Монитор: не удалось отправить уведомление: %s", error)
        except Exception as error:  # сеть тоже может быть недоступна
            logger.warning("Монитор: ошибка отправки уведомления: %s", error)


def _humanize(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} ч. {minutes} мин."
    if minutes:
        return f"{minutes} мин. {seconds} сек."
    return f"{seconds} сек."


class _MonitorLogHandler(logging.Handler):
    """Ловит строки aiogram о состоянии поллинга."""

    _FAILED_MARKER = "Failed to fetch updates"
    _OK_MARKER = "Connection established"

    def __init__(self, monitor: ConnectionMonitor) -> None:
        super().__init__(level=logging.INFO)
        self._monitor = monitor
        self._loop: asyncio.AbstractEventLoop | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            return
        if not (message.startswith(self._FAILED_MARKER) or message.startswith(self._OK_MARKER)):
            return
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        if message.startswith(self._FAILED_MARKER):
            self._monitor._last_error = message[:ERROR_MAX_LENGTH]
            self._monitor.mark_error()
        else:
            self._loop.create_task(self._monitor.mark_connected())


def attach_monitor(bot: Bot, chat_id: int | None) -> ConnectionMonitor:
    """Создаёт монитор и подписывает его на логгер aiogram.dispatcher."""
    monitor = ConnectionMonitor(bot, chat_id)
    handler = _MonitorLogHandler(monitor)
    handler.setLevel(logging.INFO)
    logging.getLogger("aiogram.dispatcher").addHandler(handler)
    monitor.start()
    return monitor
