from typing import Any

from loguru import logger
from pymodbus.client import ModbusSerialClient
from pymodbus.pdu import ModbusResponse

from log_config import log_s
from modbus_worker import ModbusWorker
from device_registers import MPP_REG, MPP_CMD_Payload, MPP_CMD_REG


def mb_decorator():
    def decorator(func):
        mw = ModbusWorker()

        def _wrapper(*args, **kwargs):
            try:
                res = func(*args, **kwargs)
                log_s(mw.send_handler.mess)
                return res
            except Exception as exc:
                logger.error(exc)
                return b"-1"

        return _wrapper

    return decorator


class MPP_Commands:
    """Команды Modbus для МПП"""

    def __init__(self, client: ModbusSerialClient, mpp_id: int|None = None):
        super().__init__()
        self.client = client
        self.payload = MPP_CMD_Payload()
        self.MPP_ID = mpp_id if mpp_id else self.MPP_ID_DEFAULT

    def _read(self, reg: MPP_REG, count: int) -> bytes:
        result: ModbusResponse = self.client.read_holding_registers(
            int(reg), count, self.MPP_ID
        )
        return result.encode()[1:]

    def _write(self, reg: MPP_REG, values: int | list[int]) -> Any:
        return self.client.write_registers(int(reg), values, self.MPP_ID)

    @mb_decorator()
    def get_hist32(self) -> bytes:
        return self._read(MPP_REG.HIST_32, 12)

    @mb_decorator()
    def get_hist16(self) -> bytes:
        return self._read(MPP_REG.HIST_16, 6)

    @mb_decorator()
    def get_bin_num(self) -> bytes:
        return self._read(MPP_REG.BIN_NUM, 1)

    @mb_decorator()
    def get_ddin(self) -> bytes:
        return self._read(MPP_REG.DDIIN_PEAK, 1)

    @mb_decorator()
    def get_tmp_cnt(self) -> bytes:
        return self._read(MPP_REG.CMD_REG, 1)

    @mb_decorator()
    def get_acq1_peak(self) -> bytes:
        return self._read(MPP_REG.ACQ1_PEAK, 1)

    @mb_decorator()
    def get_acq2_peak(self) -> bytes:
        return self._read(MPP_REG.ACQ2_PEAK, 1)

    @mb_decorator()
    def get_hh(self) -> bytes:
        return self._read(MPP_REG.HH, 32)

    @mb_decorator()
    def set_hh(self, CMD_REG: list[int]):
        self._write(MPP_REG.HH, CMD_REG)

    @mb_decorator()
    def set_clear_hist(self):
        self._write(MPP_REG.HIST_32, [0] * 18)

    @mb_decorator()
    def set_clear_reg_mes(self):
        self._write(MPP_REG.ACQ1_PEAK, [0] * 4)

    @mb_decorator()
    def CMD_REG_set_level(self, CMD_REG: int):
        self._write(MPP_REG.CMD_REG, [int(MPP_CMD_REG.SET_LEVEL), CMD_REG])

    @mb_decorator()
    def CMD_REG_start_meas(self):
        self._write(MPP_REG.CMD_REG, self.payload.START_MEASURE.copy())

    @mb_decorator()
    def CMD_REG_stop_meas(self):
        self._write(MPP_REG.CMD_REG, self.payload.STOP_MEASURE.copy())

    @mb_decorator()
    def CMD_REG_set_hh(self):
        self._write(MPP_REG.CMD_REG, int(MPP_CMD_REG.SET_HH))

    @mb_decorator()
    def CMD_REG_trig_cnt_clr(self):
        self._write(MPP_REG.CMD_REG, int(MPP_CMD_REG.TRIG_COUNT_CLEAR))
