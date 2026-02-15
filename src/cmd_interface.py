from functools import wraps
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from loguru import logger
from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.pdu import ModbusResponse

try:
    from .device_registers import DeviceProtocol, MPP_CMD_Payload, MPP_CMD_REG, MPP_REG
    from .log_config import log_s
    from .modbus_worker import ModbusWorker
except Exception:
    from src.device_registers import DeviceProtocol, MPP_CMD_Payload, MPP_CMD_REG, MPP_REG
    from src.log_config import log_s
    from src.modbus_worker import ModbusWorker


P = ParamSpec("P")
T = TypeVar("T")
AsyncModbusClient = AsyncModbusSerialClient | AsyncModbusTcpClient


async def _flush_modbus_log(mw: ModbusWorker | None) -> None:
    if mw is None:
        return
    try:
        await log_s(mw.send_handler.mess)
    except Exception as exc:
        logger.debug(f"Не удалось записать Modbus лог: {exc}")


def mb_decorator(default: Any = b"-1") -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T | Any]]]:
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T | Any]]:
        @wraps(func)
        async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> T | Any:
            mw = getattr(args[0], "mw", None) if args else None
            try:
                result = await func(*args, **kwargs)
                await _flush_modbus_log(mw)
                return result
            except Exception as exc:
                logger.error(exc)
                await _flush_modbus_log(mw)
                return default

        return _wrapper

    return decorator


class MPP_Commands:
    """Асинхронные команды Modbus для МПП."""

    def __init__(
        self,
        client: AsyncModbusClient,
        logger_instance: Any | None = None,
        mpp_id: int | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.logger = logger_instance or logger
        self.mw = ModbusWorker()
        self.payload = MPP_CMD_Payload()
        self.MPP_ID = int(mpp_id) if mpp_id is not None else int(DeviceProtocol.MPP_ID_DEFAULT)

    async def _read(self, reg: MPP_REG, count: int) -> bytes:
        result: ModbusResponse = await self.client.read_holding_registers(
            int(reg),
            int(count),
            slave=self.MPP_ID,
        )
        if result.isError():
            raise RuntimeError(f"Ошибка чтения Modbus: reg={int(reg):#06x}, count={count}")
        payload = result.encode()
        return payload[1:] if len(payload) > 1 else b""

    async def _write(self, reg: MPP_REG, values: int | list[int]) -> ModbusResponse:
        payload: list[int]
        if isinstance(values, int):
            payload = [int(values)]
        else:
            payload = [int(v) for v in values]

        result: ModbusResponse = await self.client.write_registers(
            int(reg),
            payload,
            slave=self.MPP_ID,
        )
        if result.isError():
            raise RuntimeError(f"Ошибка записи Modbus: reg={int(reg):#06x}, values={payload}")
        return result

    @mb_decorator()
    async def get_hist32(self) -> bytes:
        return await self._read(MPP_REG.HIST_32, 12)

    @mb_decorator()
    async def get_hist16(self) -> bytes:
        return await self._read(MPP_REG.HIST_16, 6)

    @mb_decorator()
    async def get_bin_num(self) -> bytes:
        return await self._read(MPP_REG.BIN_NUM, 1)

    @mb_decorator()
    async def get_ddin(self) -> bytes:
        return await self._read(MPP_REG.DDIIN_PEAK, 1)

    @mb_decorator()
    async def get_tmp_cnt(self) -> bytes:
        return await self._read(MPP_REG.CMD_REG, 1)

    @mb_decorator()
    async def get_acq1_peak(self) -> bytes:
        return await self._read(MPP_REG.ACQ1_PEAK, 1)

    @mb_decorator()
    async def get_acq2_peak(self) -> bytes:
        return await self._read(MPP_REG.ACQ2_PEAK, 1)

    @mb_decorator()
    async def get_hh(self) -> bytes:
        return await self._read(MPP_REG.HH, 32)

    @mb_decorator(default=None)
    async def set_hh(self, cmd_reg: list[int]) -> None:
        await self._write(MPP_REG.HH, cmd_reg)

    @mb_decorator(default=None)
    async def set_clear_hist(self) -> None:
        await self._write(MPP_REG.HIST_32, [0] * 18)

    @mb_decorator(default=None)
    async def set_clear_reg_mes(self) -> None:
        await self._write(MPP_REG.ACQ1_PEAK, [0] * 4)

    @mb_decorator(default=None)
    async def CMD_REG_set_level(self, cmd_reg: int) -> None:
        await self._write(MPP_REG.CMD_REG, [int(MPP_CMD_REG.SET_LEVEL), int(cmd_reg)])

    @mb_decorator(default=None)
    async def CMD_REG_start_meas(self) -> None:
        await self._write(MPP_REG.CMD_REG, self.payload.START_MEASURE.copy())

    @mb_decorator(default=None)
    async def CMD_REG_stop_meas(self) -> None:
        await self._write(MPP_REG.CMD_REG, self.payload.STOP_MEASURE.copy())

    @mb_decorator(default=None)
    async def CMD_REG_set_hh(self) -> None:
        await self._write(MPP_REG.CMD_REG, int(MPP_CMD_REG.SET_HH))

    @mb_decorator(default=None)
    async def CMD_REG_trig_cnt_clr(self) -> None:
        await self._write(MPP_REG.CMD_REG, int(MPP_CMD_REG.TRIG_COUNT_CLEAR))

    @mb_decorator(default=None)
    async def set_level(self, level: int) -> None:
        await self._write(MPP_REG.CMD_REG, [int(MPP_CMD_REG.SET_LEVEL), int(level)])

    @mb_decorator(default=None)
    async def start_measure(self, on: int = 1) -> None:
        if int(on):
            await self._write(MPP_REG.CMD_REG, self.payload.START_MEASURE.copy())
        else:
            await self._write(MPP_REG.CMD_REG, self.payload.STOP_MEASURE.copy())

    @mb_decorator(default=None)
    async def issue_waveform(self) -> None:
        await self._write(MPP_REG.CMD_REG, int(MPP_CMD_REG.WAVEFORM_RELEASE))

    @mb_decorator()
    async def read_oscill(self, ch: int = 0, count: int = 256) -> bytes:
        reg = MPP_REG.OSCILL_CH0 if int(ch) == 0 else MPP_REG.OSCILL_CH1
        return await self._read(reg, int(count))

    @mb_decorator(default=None)
    async def start_measure_forced(self, ch: int = 0) -> None:
        await self._write(
            MPP_REG.CMD_REG,
            [int(MPP_CMD_REG.START_MEASURE_FORCED), int(ch)],
        )
