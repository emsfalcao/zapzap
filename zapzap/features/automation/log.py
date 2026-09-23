"""Log rotativo da automação (uma linha por evento, sem conteúdo de mensagem).

Fork FalcaoNet: ``~/.local/share/ZapZap/automacao.log`` (no Flatpak, dentro
de ``~/.var/app/com.rtosta.zapzap/data/ZapZap``). Formato:

    2026-09-23 18:02:11 conta=<id> tipo=ausencia destino=<nome> resultado=ok tam=42
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "automacao.log"
_LOGGER_NAME = "zapzap.automacao"
_MAX_BYTES = 1024 * 1024
_BACKUP_COUNT = 3

_configured_path: Path | None = None


def log_directory() -> Path:
    """Directory of the automation log, resolved through QStandardPaths."""
    try:
        from PyQt6.QtCore import QStandardPaths

        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    except Exception:  # pragma: no cover - only without Qt
        location = ""
    if not location:
        location = str(Path.home() / ".local" / "share" / "ZapZap")
    return Path(location)


def log_path() -> Path:
    return log_directory() / LOG_FILE_NAME


def automation_logger() -> logging.Logger:
    """Return the file logger, configuring the rotating handler once."""
    global _configured_path
    logger = logging.getLogger(_LOGGER_NAME)
    path = log_path()
    if _configured_path != path:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
            )
            logger.addHandler(handler)
        except OSError:
            logging.getLogger(__name__).warning(
                "Automation log unavailable at %s", path, exc_info=True
            )
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _configured_path = path
    return logger


def log_event(
    account: str,
    kind: str,
    target: str,
    result: str,
    text_length: int | None = None,
) -> None:
    """Append one event line. The message body is never written, only its size."""
    parts = [
        f"conta={_clean(account)}",
        f"tipo={_clean(kind)}",
        f"destino={_clean(target)}",
        f"resultado={_clean(result)}",
    ]
    if text_length is not None:
        parts.append(f"tam={int(text_length)}")
    automation_logger().info(" ".join(parts))


def _clean(value) -> str:
    text = str(value if value is not None else "")
    return text.replace("\n", " ").replace("\r", " ").strip() or "-"
