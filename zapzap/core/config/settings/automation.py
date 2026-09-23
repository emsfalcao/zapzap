"""Automation (away replies and scheduled messages) settings domain.

Fork FalcaoNet: automação por cima do WhatsApp Web (DOM/JS injetado). Não é
oficial e pode gerar restrição ou banimento do número; por isso tudo vem
desligado por padrão, com freios (limite por hora, atrasos "humanos",
cooldown por conversa) e registro em arquivo de log.

Este módulo é puro (sem Qt além do SettingsManager) para que as regras —
janela diária cruzando a meia-noite, cooldown, limite por hora, validação de
data/hora e do número E.164 — sejam testáveis sem WebEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
import re
import uuid

from zapzap.core.config.settings.base import BaseSettings
from zapzap.features.browser.web.open_chat import (
    VALID_CALLING_CODES,
    ChatTarget,
    ChatTargetValidationError,
    normalize_phone_digits,
    validate_chat_target,
)

MAX_AWAY_TEXT_LENGTH = 1000
MAX_SCHEDULED_TEXT_LENGTH = 4096

DELAY_MIN_OPTIONS_S = (5, 10, 20, 30, 60)
DELAY_MAX_OPTIONS_S = (30, 60, 120, 300)
MAX_PER_HOUR_OPTIONS = (5, 10, 20, 30)
COOLDOWN_OPTIONS_H = (1, 4, 8, 24)
UNFOCUSED_OPTIONS_MIN = (0, 5, 15, 30)
LATE_GRACE_OPTIONS_MIN = (15, 60, 240, 1440)

# Status persistidos de uma mensagem agendada (IDs estáveis, não traduzidos).
STATUS_PENDING = "pendente"
STATUS_SENT = "enviada"
STATUS_FAILED = "falhou"
STATUS_EXPIRED = "expirada"
SCHEDULED_STATUSES = (STATUS_PENDING, STATUS_SENT, STATUS_FAILED, STATUS_EXPIRED)

MAX_SCHEDULED_ATTEMPTS = 3
RETRY_WAIT_S = 5 * 60

_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")
_DATETIME_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})$")


class AutomationValidationError(ValueError):
    """Raised when an automation field does not satisfy the storage rules."""

    INVALID_TIME = "invalid_time"
    INVALID_DATETIME = "invalid_datetime"
    DATETIME_IN_PAST = "datetime_in_past"
    EMPTY_TEXT = "empty_text"
    TOO_LONG = "too_long"
    INVALID_NUMBER = "invalid_number"

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Horários
# ---------------------------------------------------------------------------

def parse_time_hhmm(value: str) -> tuple[int, int]:
    """Parse ``HH:MM`` into ``(hour, minute)``; raises INVALID_TIME."""
    match = _TIME_PATTERN.match((value or "").strip())
    if not match:
        raise AutomationValidationError(AutomationValidationError.INVALID_TIME)
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise AutomationValidationError(AutomationValidationError.INVALID_TIME)
    return hour, minute


def format_time_hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def is_within_daily_window(
    now: datetime,
    start: str,
    end: str,
    include_weekend: bool = False,
) -> bool:
    """Return whether ``now`` falls inside the daily window ``start``–``end``.

    The window may cross midnight (e.g. 18:00 → 08:00). ``start == end``
    means the whole day. With ``include_weekend`` Saturday and Sunday count
    entirely, regardless of the hours.
    """
    if include_weekend and now.weekday() >= 5:
        return True
    start_h, start_m = parse_time_hhmm(start)
    end_h, end_m = parse_time_hhmm(end)
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    current = now.hour * 60 + now.minute
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current < end_minutes
    # Cruza a meia-noite: [start, 24h) ∪ [0, end)
    return current >= start_minutes or current < end_minutes


def parse_schedule_datetime(value: str) -> datetime:
    """Parse ``AAAA-MM-DD HH:MM`` (local, naive); raises INVALID_DATETIME."""
    match = _DATETIME_PATTERN.match((value or "").strip())
    if not match:
        raise AutomationValidationError(
            AutomationValidationError.INVALID_DATETIME
        )
    try:
        return datetime(*(int(group) for group in match.groups()))
    except ValueError as error:
        raise AutomationValidationError(
            AutomationValidationError.INVALID_DATETIME
        ) from error


def format_schedule_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Número E.164
# ---------------------------------------------------------------------------

def split_e164(number: str) -> tuple[str, str]:
    """Split ``+5581999999999`` into ``("55", "81999999999")``.

    Uses the same calling-code table as the "By phone number" dialog; the
    longest matching prefix (1–3 digits) wins. Raises INVALID_NUMBER.
    """
    digits = normalize_phone_digits(number)
    if not digits:
        raise AutomationValidationError(AutomationValidationError.INVALID_NUMBER)
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix in VALID_CALLING_CODES and len(digits) > length:
            return prefix, digits[length:]
    raise AutomationValidationError(AutomationValidationError.INVALID_NUMBER)


def validate_e164_number(number: str) -> ChatTarget:
    """Validate a full international number with the shared E.164 rules."""
    calling_code, national = split_e164(number)
    try:
        return validate_chat_target(calling_code, national)
    except ChatTargetValidationError as error:
        raise AutomationValidationError(
            AutomationValidationError.INVALID_NUMBER
        ) from error


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def validate_text(text: str, max_length: int) -> str:
    text = text or ""
    if not text.strip():
        raise AutomationValidationError(AutomationValidationError.EMPTY_TEXT)
    if len(text) > max_length:
        raise AutomationValidationError(AutomationValidationError.TOO_LONG)
    return text


def validate_away_text(text: str) -> str:
    return validate_text(text, MAX_AWAY_TEXT_LENGTH)


# ---------------------------------------------------------------------------
# Mensagem agendada
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduledMessage:
    """One message to be sent at ``when`` from account ``user_id``."""

    id: str
    user_id: str
    number: str
    text: str
    when: datetime
    status: str = STATUS_PENDING
    attempts: int = 0
    last_error: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_attempt: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conta": self.user_id,
            "numero": self.number,
            "texto": self.text,
            "quando": self.when.isoformat(timespec="minutes"),
            "status": self.status,
            "tentativas": self.attempts,
            "ultimo_erro": self.last_error,
            "criado_em": self.created_at.isoformat(timespec="seconds"),
            "ultima_tentativa": (
                self.last_attempt.isoformat(timespec="seconds")
                if self.last_attempt else ""
            ),
        }

    @classmethod
    def from_dict(cls, data) -> ScheduledMessage | None:
        if not isinstance(data, dict):
            return None
        try:
            when = datetime.fromisoformat(str(data.get("quando", "")))
        except ValueError:
            return None
        item_id = str(data.get("id", "")).strip()
        number = normalize_phone_digits(str(data.get("numero", "")))
        text = str(data.get("texto", ""))
        if not item_id or not number or not text.strip():
            return None
        status = str(data.get("status", STATUS_PENDING))
        if status not in SCHEDULED_STATUSES:
            status = STATUS_PENDING
        created_at = _parse_optional_datetime(data.get("criado_em"))
        last_attempt = _parse_optional_datetime(data.get("ultima_tentativa"))
        try:
            attempts = int(data.get("tentativas", 0))
        except (TypeError, ValueError):
            attempts = 0
        return cls(
            id=item_id,
            user_id=str(data.get("conta", "")),
            number=number,
            text=text[:MAX_SCHEDULED_TEXT_LENGTH],
            when=when,
            status=status,
            attempts=max(0, attempts),
            last_error=str(data.get("ultimo_erro", "")),
            created_at=created_at or when,
            last_attempt=last_attempt,
        )


def _parse_optional_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def validate_scheduled_message(
    user_id: str,
    number: str,
    text: str,
    when: str,
    now: datetime | None = None,
) -> ScheduledMessage:
    """Validate the dialog fields and return a pending ScheduledMessage."""
    now = now or datetime.now()
    target = validate_e164_number(number)
    text = validate_text(text, MAX_SCHEDULED_TEXT_LENGTH)
    when_dt = parse_schedule_datetime(when)
    if when_dt <= now:
        raise AutomationValidationError(
            AutomationValidationError.DATETIME_IN_PAST
        )
    return ScheduledMessage(
        id=uuid.uuid4().hex,
        user_id=str(user_id),
        number=target.normalized_phone,
        text=text,
        when=when_dt,
        created_at=now,
    )


def due_scheduled_items(
    items: list[ScheduledMessage],
    now: datetime,
    late_grace_min: int,
    retry_wait_s: int = RETRY_WAIT_S,
) -> tuple[list[ScheduledMessage], list[ScheduledMessage]]:
    """Split pending items into ``(to_send, to_expire)`` for this tick.

    An item whose time passed by more than ``late_grace_min`` (the app was
    closed, for instance) expires instead of being sent late. A retry waits
    ``retry_wait_s`` after the previous attempt.
    """
    to_send: list[ScheduledMessage] = []
    to_expire: list[ScheduledMessage] = []
    grace = timedelta(minutes=late_grace_min)
    retry_wait = timedelta(seconds=retry_wait_s)
    for item in sorted(items, key=lambda entry: entry.when):
        if item.status != STATUS_PENDING or item.when > now:
            continue
        if now - item.when > grace:
            to_expire.append(item)
            continue
        if item.last_attempt is not None and now - item.last_attempt < retry_wait:
            continue
        to_send.append(item)
    return to_send, to_expire


# ---------------------------------------------------------------------------
# Freios: limite por hora e cooldown por conversa (puros, sem Qt)
# ---------------------------------------------------------------------------

class HourlyLimit:
    """Sliding one-hour window over send timestamps (epoch seconds)."""

    WINDOW_S = 3600

    def __init__(self, timestamps: list[float] | None = None):
        self._timestamps = [float(value) for value in (timestamps or [])]

    def prune(self, now: float) -> None:
        threshold = now - self.WINDOW_S
        self._timestamps = [
            value for value in self._timestamps if value > threshold
        ]

    def count(self, now: float) -> int:
        self.prune(now)
        return len(self._timestamps)

    def allows(self, limit: int, now: float) -> bool:
        return self.count(now) < int(limit)

    def record(self, now: float) -> None:
        self.prune(now)
        self._timestamps.append(float(now))

    @property
    def timestamps(self) -> list[float]:
        return list(self._timestamps)


class ReplyCooldown:
    """Remember the last automatic reply per conversation key."""

    def __init__(self, replied: dict[str, float] | None = None):
        self._replied = {
            str(key): float(value) for key, value in (replied or {}).items()
        }

    def prune(self, cooldown_s: float, now: float) -> None:
        threshold = now - cooldown_s
        self._replied = {
            key: value for key, value in self._replied.items()
            if value > threshold
        }

    def is_cooling(self, key: str, cooldown_s: float, now: float) -> bool:
        self.prune(cooldown_s, now)
        return key in self._replied

    def mark(self, key: str, now: float) -> None:
        self._replied[key] = float(now)

    @property
    def replied(self) -> dict[str, float]:
        return dict(self._replied)


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

class AutomationSettings(BaseSettings):
    """Semantic access to every automation key. Everything defaults to off."""

    _ENABLED = ("automation/enabled", False)
    _DELAY_MIN_S = ("automation/delay_min_s", 20)
    _DELAY_MAX_S = ("automation/delay_max_s", 60)
    _MAX_PER_HOUR = ("automation/max_per_hour", 10)
    _SENT_TIMESTAMPS = ("automation/sent_timestamps", "[]")

    _AWAY_ENABLED = ("automation/away/enabled", False)
    _AWAY_TEXT = ("automation/away/text", "")
    _AWAY_COOLDOWN_H = ("automation/away/cooldown_h", 8)
    _AWAY_SKIP_GROUPS = ("automation/away/skip_groups", True)
    _AWAY_ONLY_WHEN_UNFOCUSED_MIN = ("automation/away/only_when_unfocused_min", 5)
    _AWAY_SCHEDULE_ENABLED = ("automation/away/schedule_enabled", False)
    _AWAY_SCHEDULE_START = ("automation/away/schedule_start", "18:00")
    _AWAY_SCHEDULE_END = ("automation/away/schedule_end", "08:00")
    _AWAY_SCHEDULE_WEEKEND = ("automation/away/schedule_weekend", True)
    _AWAY_REPLIED = ("automation/away/replied", "{}")

    _SCHEDULED_ENABLED = ("automation/scheduled/enabled", False)
    _SCHEDULED_LATE_GRACE_MIN = ("automation/scheduled/late_grace_min", 60)
    _SCHEDULED_ITEMS = ("automation/scheduled/items", "[]")

    ALL_KEYS = (
        _ENABLED[0], _DELAY_MIN_S[0], _DELAY_MAX_S[0], _MAX_PER_HOUR[0],
        _SENT_TIMESTAMPS[0], _AWAY_ENABLED[0], _AWAY_TEXT[0],
        _AWAY_COOLDOWN_H[0], _AWAY_SKIP_GROUPS[0],
        _AWAY_ONLY_WHEN_UNFOCUSED_MIN[0], _AWAY_SCHEDULE_ENABLED[0],
        _AWAY_SCHEDULE_START[0], _AWAY_SCHEDULE_END[0],
        _AWAY_SCHEDULE_WEEKEND[0], _AWAY_REPLIED[0], _SCHEDULED_ENABLED[0],
        _SCHEDULED_LATE_GRACE_MIN[0], _SCHEDULED_ITEMS[0],
    )

    # --- geral ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._get_bool(self._ENABLED)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._set_bool(self._ENABLED, value)

    @property
    def delay_min_s(self) -> int:
        return max(0, self._get_int(self._DELAY_MIN_S))

    @delay_min_s.setter
    def delay_min_s(self, value: int) -> None:
        self._set_int(self._DELAY_MIN_S, max(0, int(value)))

    @property
    def delay_max_s(self) -> int:
        return max(self.delay_min_s, self._get_int(self._DELAY_MAX_S))

    @delay_max_s.setter
    def delay_max_s(self, value: int) -> None:
        self._set_int(self._DELAY_MAX_S, max(0, int(value)))

    @property
    def max_per_hour(self) -> int:
        return max(1, self._get_int(self._MAX_PER_HOUR))

    @max_per_hour.setter
    def max_per_hour(self, value: int) -> None:
        self._set_int(self._MAX_PER_HOUR, max(1, int(value)))

    def load_hourly_limit(self) -> HourlyLimit:
        return HourlyLimit(self._load_json(self._SENT_TIMESTAMPS, list))

    def save_hourly_limit(self, limit: HourlyLimit) -> None:
        self._set_str(self._SENT_TIMESTAMPS, json.dumps(limit.timestamps))

    # --- ausência ------------------------------------------------------
    @property
    def away_enabled(self) -> bool:
        return self._get_bool(self._AWAY_ENABLED)

    @away_enabled.setter
    def away_enabled(self, value: bool) -> None:
        self._set_bool(self._AWAY_ENABLED, value)

    @property
    def away_text(self) -> str:
        return self._get_str(self._AWAY_TEXT)[:MAX_AWAY_TEXT_LENGTH]

    @away_text.setter
    def away_text(self, value: str) -> None:
        self._set_str(self._AWAY_TEXT, (value or "")[:MAX_AWAY_TEXT_LENGTH])

    @property
    def away_cooldown_h(self) -> int:
        return max(1, self._get_int(self._AWAY_COOLDOWN_H))

    @away_cooldown_h.setter
    def away_cooldown_h(self, value: int) -> None:
        self._set_int(self._AWAY_COOLDOWN_H, max(1, int(value)))

    @property
    def away_skip_groups(self) -> bool:
        return self._get_bool(self._AWAY_SKIP_GROUPS)

    @away_skip_groups.setter
    def away_skip_groups(self, value: bool) -> None:
        self._set_bool(self._AWAY_SKIP_GROUPS, value)

    @property
    def away_only_when_unfocused_min(self) -> int:
        return max(0, self._get_int(self._AWAY_ONLY_WHEN_UNFOCUSED_MIN))

    @away_only_when_unfocused_min.setter
    def away_only_when_unfocused_min(self, value: int) -> None:
        self._set_int(self._AWAY_ONLY_WHEN_UNFOCUSED_MIN, max(0, int(value)))

    @property
    def away_schedule_enabled(self) -> bool:
        return self._get_bool(self._AWAY_SCHEDULE_ENABLED)

    @away_schedule_enabled.setter
    def away_schedule_enabled(self, value: bool) -> None:
        self._set_bool(self._AWAY_SCHEDULE_ENABLED, value)

    @property
    def away_schedule_start(self) -> str:
        return self._valid_time_or_default(self._AWAY_SCHEDULE_START)

    @away_schedule_start.setter
    def away_schedule_start(self, value: str) -> None:
        self._set_str(
            self._AWAY_SCHEDULE_START, format_time_hhmm(*parse_time_hhmm(value))
        )

    @property
    def away_schedule_end(self) -> str:
        return self._valid_time_or_default(self._AWAY_SCHEDULE_END)

    @away_schedule_end.setter
    def away_schedule_end(self, value: str) -> None:
        self._set_str(
            self._AWAY_SCHEDULE_END, format_time_hhmm(*parse_time_hhmm(value))
        )

    @property
    def away_schedule_weekend(self) -> bool:
        return self._get_bool(self._AWAY_SCHEDULE_WEEKEND)

    @away_schedule_weekend.setter
    def away_schedule_weekend(self, value: bool) -> None:
        self._set_bool(self._AWAY_SCHEDULE_WEEKEND, value)

    def load_reply_cooldown(self) -> ReplyCooldown:
        return ReplyCooldown(self._load_json(self._AWAY_REPLIED, dict))

    def save_reply_cooldown(self, cooldown: ReplyCooldown) -> None:
        self._set_str(self._AWAY_REPLIED, json.dumps(cooldown.replied))

    # --- agendadas -----------------------------------------------------
    @property
    def scheduled_enabled(self) -> bool:
        return self._get_bool(self._SCHEDULED_ENABLED)

    @scheduled_enabled.setter
    def scheduled_enabled(self, value: bool) -> None:
        self._set_bool(self._SCHEDULED_ENABLED, value)

    @property
    def scheduled_late_grace_min(self) -> int:
        return max(0, self._get_int(self._SCHEDULED_LATE_GRACE_MIN))

    @scheduled_late_grace_min.setter
    def scheduled_late_grace_min(self, value: int) -> None:
        self._set_int(self._SCHEDULED_LATE_GRACE_MIN, max(0, int(value)))

    @property
    def scheduled_items(self) -> list[ScheduledMessage]:
        items = []
        seen = set()
        for entry in self._load_json(self._SCHEDULED_ITEMS, list):
            item = ScheduledMessage.from_dict(entry)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            items.append(item)
        items.sort(key=lambda item: item.when)
        return items

    @scheduled_items.setter
    def scheduled_items(self, items: list[ScheduledMessage]) -> None:
        payload = [item.to_dict() for item in items]
        self._set_str(
            self._SCHEDULED_ITEMS, json.dumps(payload, ensure_ascii=False)
        )

    def add_scheduled(self, item: ScheduledMessage) -> None:
        self.scheduled_items = [
            existing for existing in self.scheduled_items
            if existing.id != item.id
        ] + [item]

    def update_scheduled(self, item_id: str, **changes) -> ScheduledMessage | None:
        """Apply field changes to one item and persist; returns the new item."""
        updated = None
        items = []
        for item in self.scheduled_items:
            if item.id == item_id:
                item = replace(item, **changes)
                updated = item
            items.append(item)
        if updated is not None:
            self.scheduled_items = items
        return updated

    def remove_scheduled(self, item_id: str) -> None:
        self.scheduled_items = [
            item for item in self.scheduled_items if item.id != item_id
        ]

    def find_scheduled(self, item_id: str) -> ScheduledMessage | None:
        for item in self.scheduled_items:
            if item.id == item_id:
                return item
        return None

    # --- util ----------------------------------------------------------
    def _valid_time_or_default(self, setting: tuple[str, str]) -> str:
        value = self._get_str(setting)
        try:
            return format_time_hhmm(*parse_time_hhmm(value))
        except AutomationValidationError:
            return setting[1]

    def _load_json(self, setting: tuple[str, str], expected_type):
        raw = self._get_str(setting)
        try:
            data = json.loads(raw) if raw else expected_type()
        except (TypeError, ValueError):
            return expected_type()
        if not isinstance(data, expected_type):
            return expected_type()
        return data
