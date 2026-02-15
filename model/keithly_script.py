import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator

from loguru import logger
from pydantic import BaseModel, model_validator

try:
    from keithley2600 import Keithley2600
    _KEITHLEY_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    Keithley2600 = Any  # type: ignore
    _KEITHLEY_IMPORT_ERROR = exc

src_path = Path(__file__).resolve().parent.parent.parent.parent
# Добавляем папку src в sys.path
sys.path.append(str(src_path))

from src.log_config import log_init

# k = Keithley2600(f'TCPIP0::{address}::INSTR')


class ConvinceMode(BaseModel):
    vg_lst: list
    step_delay_s: float


class LinspaceMode(BaseModel):
    vg_start: float
    vg_stop: float
    vg_step: int
    step_delay_s: float


class ConstMode(BaseModel):
    vg_cnst: float


class MeasureSettings(BaseModel):
    convince_mode: ConvinceMode | None = None
    linspace_mode: LinspaceMode | None = None
    const_mode: ConstMode | None = None

    @model_validator(mode="after")
    def validate_single_mode(self) -> "MeasureSettings":
        enabled_modes = [
            self.convince_mode is not None,
            self.linspace_mode is not None,
            self.const_mode is not None,
        ]
        if sum(enabled_modes) != 1:
            raise ValueError("Exactly one measure mode must be set")
        return self


class ModBusSettings(BaseModel):
    id: int
    bodrate: int


class MPModel(BaseModel):
    name: str
    calibrate_mode: bool  # Включить режим калибровки
    # (Нужно прописать настройки ModBus)
    modbus_settings: ModBusSettings | None = None
    measure_settings: MeasureSettings
    current_limit: float  # Задать ограничение по току
    loop: bool  # позволяет зациклить измерение
    save_table: bool
    save_plot: bool

    @classmethod
    def pydentic_model_init(cls, data: dict) -> Dict[str, "MPModel"]:
        return {
            name: cls.model_validate(conf)
            for name, conf in data.items()
        }

class MeasureProcessing:
    def __init__(self, k: Keithley2600 | None = None):
        self.k = k
        self.mp_model: Dict[str, MPModel] = {}

    def load_config(self, json_conf: str):
        try:
            with open(json_conf, "r", encoding="utf-8") as jsn:
                raw = json.load(jsn)
        except Exception:
            logger.error("Measure config not found")
            return
        try:
            self.mp_model = MPModel.pydentic_model_init(raw)
        except Exception as e:
            logger.error(e)
    
    async def run_process(self):
        for proess in self.mp_model.values():
            await self.apply_voltage_by_measure_settings(
                proess.measure_settings,
                current_limit=proess.current_limit,
            )
            
        
        # Здесь должна быть логика выполнения измерения в зависимости от настроек mp_conf
        # Например, если mp_conf.calibrate_mode == True, то выполняем калибровку
        # Если mp_conf.loop == True, то зацикливаем измерение и т.д.

    def _iter_setpoints(self, measure_settings: MeasureSettings) -> Iterator[tuple[float, float]]:
        if measure_settings.convince_mode is not None:
            delay = float(measure_settings.convince_mode.step_delay_s)
            for voltage in measure_settings.convince_mode.vg_lst:
                yield float(voltage), delay
            return

        if measure_settings.linspace_mode is not None:
            start = float(measure_settings.linspace_mode.vg_start)
            stop = float(measure_settings.linspace_mode.vg_stop)
            points = max(1, int(measure_settings.linspace_mode.vg_step))
            delay = float(measure_settings.linspace_mode.step_delay_s)
            if points == 1:
                yield start, delay
                return
            step = (stop - start) / (points - 1)
            for index in range(points):
                yield start + index * step, delay
            return

        if measure_settings.const_mode is not None:
            yield float(measure_settings.const_mode.vg_cnst), 0.0

    async def apply_voltage_by_measure_settings(
        self,
        measure_settings: MeasureSettings,
        current_limit: float | None = None,
    ) -> list[float]:
        if self.k is None:
            raise RuntimeError("Keithley is not connected")

        # Configure source as voltage output once before stepping.
        self.k.smua.source.func = self.k.smua.OUTPUT_DCVOLTS
        self.k.smua.source.output = self.k.smua.OUTPUT_ON
        if current_limit is not None:
            self.k.smua.source.limiti = float(current_limit)

        applied: list[float] = []
        for voltage, delay in self._iter_setpoints(measure_settings):
            self.k.smua.source.levelv = voltage
            applied.append(voltage)
            logger.debug(f"Keithley level set: {voltage:.6f} V")
            if delay > 0:
                await asyncio.sleep(delay)
        return applied

if __name__ == "__main__":
    address = "10.6.1.222"
    logger = log_init()
    json_conf = Path("modules/Calibrator/widgets/keithly_script.json")
    if _KEITHLEY_IMPORT_ERROR is not None:
        logger.error(f"keithley2600 import error: {_KEITHLEY_IMPORT_ERROR}")
        raise SystemExit(1)
    try:
        k: Keithley2600 | None = Keithley2600(f"TCPIP0::{address}::INSTR")  # type:ignore
        logger.debug(f"Connected: TCPIP0::{address}::INSTR")
    except Exception as e:
        k = None
        logger.error(f"Error connection keithley: {e}")
    try:
        # if k:
        mp: MeasureProcessing = MeasureProcessing(k)
        mp.load_config(json_conf)
    except Exception as e:
        logger.error(e)
