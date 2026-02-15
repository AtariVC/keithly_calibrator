"""
Лог конфиги.
"DEBUG" - для записи отладочной информации
"ERROR" - для записи ошибок в журнал ошибок
"INFO" - для записи команд serial port как в DockLight
"""
from loguru import logger
from datetime import datetime
import sys
import re
from PyQt6.QtCore import Qt, QTimer, QThread
from pathlib import Path

# from logger import logging

_initialized = False
# Global flags to enable/disable logging at runtime
LOG_ENABLED = True           # General loguru logging
SERIAL_LOG_ENABLED = True    # TX/RX serial hex stream logging (log_s)

def log_init():
    """Инициализировать loguru один раз и вернуть общий logger.

    Делает функцию идемпотентной: повторные вызовы не ломают обработчики
    и не вызывают ошибок вида "There is no existing handler with id 0".
    """
    global _initialized
    if _initialized:
        return logger

    # Удаляем все существующие обработчики безопасно, без указания id
    try:
        logger.remove()
    except Exception:
        pass

    rx_level= logger.level("RX", no=0, color="<red>", icon="")
    tx_level= logger.level("TX", no=0, color="<green>", icon="")
    emulator_level = logger.level("EMULATOR", no=0, color="<y>", icon="")

    time_now = datetime.now()
    form_time = time_now.strftime("%Y-%m-%d %H_%M_%S")
    home_dir = str(Path().resolve())
    log_path_debug =    home_dir + "/log/debug/" + str(form_time) + ".log"
    log_path_serial =   home_dir + "/log/serial/" + str(form_time) + ".log"
    log_path_emulator = home_dir + "/log/emulator/" + str(form_time) + ".log"
    log_format_debug = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <4}</level> | \
<yellow>{file}:{line}</yellow> | <w>{message}</w>"
    log_format_tx = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <1}</level> | \
<m>{message}</m>"
    log_format_rx = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <1}</level> | \
<c>{message}</c>"
    log_format_emulator = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <1}</level> | \
<w>{message}</w>"

    logger.add(sys.stderr, level="WARNING", format=log_format_debug,
            colorize=True, backtrace=True, diagnose=True, filter=warning_filter)
    logger.add(sys.stderr, level="INFO", format=log_format_debug,
            colorize=True, backtrace=True, diagnose=True, filter=info_filter)
    logger.add(sys.stderr, level="DEBUG", format=log_format_debug,
            colorize=True, backtrace=True, diagnose=True, filter=debug_filter)
    logger.add(sys.stderr, level="ERROR", format=log_format_debug,
            colorize=True, backtrace=True, diagnose=True, filter=error_filter)
    # логирование serial rx
    logger.add(sys.stdout,level=rx_level.name, format=log_format_rx,
            colorize=True, backtrace=True, diagnose=True, filter=rx_filter)
    # логирование serial tx
    logger.add(sys.stdout,level=tx_level.name, format=log_format_tx,
            colorize=True, backtrace=True, diagnose=True, filter=tx_filter)
    # эмулятор
    logger.add(sys.stdout,level=emulator_level.name, format=log_format_emulator,
            colorize=True, backtrace=True, diagnose=True, filter=emulator_filter)
    # логирование в файл
    logger.add(log_path_debug, level="DEBUG", format=log_format_debug, rotation="100 MB", enqueue=True, filter=debug_filter)
    logger.add(log_path_debug, level="ERROR", format=log_format_debug, rotation="100 MB", enqueue=True, filter=error_filter)
    logger.add(log_path_debug, level="INFO", format=log_format_debug, rotation="100 MB", enqueue=True, filter=error_filter)
    # logger.add(log_path_serial, level=rx_level.name, format=log_format_rx, enqueue=True, filter=rx_filter)
    # logger.add(log_path_serial, level=tx_level.name, format=log_format_tx, enqueue=True, filter=tx_filter)
    # logger.add(log_path_emulator, level=emulator_level.name, format=log_format_emulator, enqueue=True, filter=emulator_filter)
    # логирование в файл
    # logger.add(log_path_debug, level=log_level, format=log_format, colorize=False, backtrace=True, diagnose=True)
    _initialized = True
    return logger

def get_logger(name: str | None = None):
    """Получить общий логгер"""
    if not _initialized:
        log_init()
    # В loguru имя логгера не используется так же, как в logging,
    # возвращаем глобальный экземпляр
    return logger

def emulator_filter(record):
    return record["level"].name == "EMULATOR"

def tx_filter(record):
    return record["level"].name == "TX"

def rx_filter(record):
    return record["level"].name == "RX"

def debug_filter(record):
    return record["level"].name == "DEBUG"

def error_filter(record):
    return record["level"].name == "ERROR"

def warning_filter(record):
    return record["level"].name == "WARNING"

def info_filter(record):
    return record["level"].name == "INFO"

async def log_s(message: list):
    # Respect global switch for serial TX/RX logging
    if not SERIAL_LOG_ENABLED:
        message.clear()
        return 0
    mess: list[str]= [r'']
    for item in message:
        try:
            if item[:4] == "send":
                mess = item[6:].replace("0x", "")
                mode = "TX"
            if item[:4] == "recv":
                mode = "RX"
                mess = item[6:].replace("0x", "")
        except IndexError as e:
            logger.debug("Нет ответа от устройства")
            logger.debug("pymodus.send_handler.mass: IndexError")
            return 0
        mess: list[str] = re.findall(r'\b[a-f0-9]{1,2}\b', mess)  # type: ignore
        # ''.join(mess)
        new_mess = ""
        for i in range(0, len(mess)):
            if len(mess[i]) == 1:
                mess[i] = "0" + mess[i]
            new_mess = new_mess + mess[i] + " "
        if mode == "RX":
            logger.log("RX", new_mess.upper())
        elif mode == "TX":
            logger.log("TX", new_mess.upper())
    message.clear()

def set_log_enabled(flag: bool) -> None:
    """Enable/disable general logging (loguru handlers still exist, but callers may check this)."""
    global LOG_ENABLED
    LOG_ENABLED = bool(flag)

def set_serial_log_enabled(flag: bool) -> None:
    """Enable/disable serial TX/RX logging performed by log_s()."""
    global SERIAL_LOG_ENABLED
    SERIAL_LOG_ENABLED = bool(flag)
