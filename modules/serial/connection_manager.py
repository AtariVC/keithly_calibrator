import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Union

from PyQt6 import QtCore
from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import (
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
)

# Твои служебные классы
try:
    from device_registers import EnvironmentVar
    from src.log_config import log_s
    from src.modbus_worker import ModbusWorker
except Exception:
    class EnvironmentVar:
        CM_ID = 1
        DDII_SWITCH_MODE = 0x0001
        SILENT_MODE = 0x0000

    async def log_s(_): ...
    class ModbusWorker:
        def __init__(self): self.send_handler = type("X", (), {"mess": b""})()


class ConnectionMode(Enum):
    SERIAL = auto()
    TCP = auto()
    RELAY = auto()


@dataclass
class ConnectionStatus:
    connected: bool
    mode: Optional[ConnectionMode] = None
    cm_ok: Optional[bool] = None
    mpp_ok: Optional[bool] = None
    detail: str = ""


class DDIIConnectionManager(QtCore.QObject, EnvironmentVar):
    status_changed = QtCore.pyqtSignal(object)
    connection_established = QtCore.pyqtSignal(object)
    connection_lost = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, logger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.mw = ModbusWorker()

        self._mode: Optional[ConnectionMode] = None
        self._serial: Optional[AsyncModbusSerialClient] = None
        self._tcp: Optional[AsyncModbusTcpClient] = None
        self._relay_task: Optional[asyncio.Task] = None
        self._relay_running = False

        self._timeout_s = 1.0
        self._mpp_id = 14
        self.connected = False

    def set_mpp_id(self, mpp_id: int):
        self._mpp_id = int(mpp_id)

    def set_timeout(self, seconds: float):
        self._timeout_s = max(0.1, float(seconds))

    async def connect_serial(self, port: str, baudrate: int = 115200) -> bool:
        await self.disconnect()
        try:
            self._serial = AsyncModbusSerialClient(
                port=port,
                baudrate=baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=self._timeout_s,
                method="rtu",
            )
            ok = await self._serial.connect()
            if not ok:
                await self._fail("COM-порт занят или не найден")
                return False

            self._mode = ConnectionMode.SERIAL
            self.connected = True
            self.status_changed.emit(ConnectionStatus(True, self._mode, detail="Serial подключено"))
            self.connection_established.emit(self._serial)
            return True
        except Exception as e:
            await self._fail(f"Ошибка подключения Serial: {e}")
            return False

    async def connect_tcp(self, host: str, port: int) -> bool:
        await self.disconnect()
        try:
            self._tcp = AsyncModbusTcpClient(host=host, port=port, timeout=self._timeout_s)
            ok = await self._tcp.connect()
            if not ok:
                await self._fail("TCP-хост недоступен")
                return False
            self._mode = ConnectionMode.TCP
            self.connected = True
            self.status_changed.emit(ConnectionStatus(True, self._mode, detail=f"TCP {host}:{port}"))
            self.connection_established.emit(self._tcp)
            return True
        except Exception as e:
            await self._fail(f"Ошибка TCP-подключения: {e}")
            return False

    async def disconnect(self):
        if self._relay_running:
            await self.stop_relay()
        try:
            if self._serial:
                self._serial.close()
            if self._tcp:
                self._tcp.close()
        except Exception:
            pass
        self._serial = self._tcp = None
        self._mode = None
        was = self.connected
        self.connected = False
        if was:
            self.status_changed.emit(ConnectionStatus(False, detail="Отключено"))

    async def check_modules(self, check_cm=True, check_mpp=True):
        if not self.connected:
            return False, False

        client = self._get_client()
        if not client:
            return False, False

        cm_ok, mpp_ok = True, True
        try:
            if check_cm:
                rr = await client.write_registers(self.DDII_SWITCH_MODE, [self.SILENT_MODE], unit=self.CM_ID)
                await log_s(self.mw.send_handler.mess)
                if rr.isError():
                    raise ModbusException("Ошибка CM")
        except Exception as e:
            cm_ok = False
            self.logger.warning(f"CM недоступен: {e}")

        try:
            if check_mpp:
                rr = await client.read_holding_registers(0x0000, 4, unit=self._mpp_id)
                await log_s(self.mw.send_handler.mess)
                if rr.isError():
                    raise ModbusException("Ошибка MPP")
        except Exception as e:
            mpp_ok = False
            self.logger.warning(f"MPP недоступен: {e}")

        if not cm_ok and not mpp_ok:
            await self._connection_lost_and_close("CM и MPP недоступны")

        self.status_changed.emit(ConnectionStatus(self.connected, self._mode, cm_ok, mpp_ok))
        return cm_ok, mpp_ok

    async def start_relay(self, host="0.0.0.0", port=502) -> bool:
        if not self.connected:
            await self._fail("Нет активного подключения для relay")
            return False
        if self._relay_running:
            return True
        try:
            store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*200), zero_mode=True)
            context = ModbusServerContext(slaves=store, single=True)

            async def _run():
                self._relay_running = True
                try:
                    await StartAsyncTcpServer(context=context, address=(host, port))
                finally:
                    self._relay_running = False

            self._relay_task = asyncio.create_task(_run())
            self.status_changed.emit(ConnectionStatus(True, ConnectionMode.RELAY, detail=f"Relay {host}:{port}"))
            return True
        except Exception as e:
            await self._fail(f"Ошибка запуска relay: {e}")
            return False

    async def stop_relay(self):
        if self._relay_task and not self._relay_task.done():
            self._relay_task.cancel()
            try:
                await self._relay_task
            except Exception:
                pass
        self._relay_task = None
        self._relay_running = False
        self.status_changed.emit(ConnectionStatus(self.connected, self._mode, detail="Relay остановлен"))

    def _get_client(self) -> Optional[Union[AsyncModbusSerialClient, AsyncModbusTcpClient]]:
        return self._serial if self._mode == ConnectionMode.SERIAL else self._tcp

    async def _fail(self, msg: str):
        self.logger.error(msg)
        self.error.emit(msg)
        await self.disconnect()

    async def _connection_lost_and_close(self, msg: str):
        self.connection_lost.emit(msg)
        await self.disconnect()
