import asyncio
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Literal

from loguru import logger
from pydantic import BaseModel, model_validator
from pymodbus.client import AsyncModbusSerialClient


import matplotlib.pyplot as plt

from keithley2600 import Keithley2600


src_path = Path(__file__).resolve().parent.parent
sys.path.append(str(src_path))

from src.async_task_manager import AsyncTaskManager
from src.cmd_interface import MPP_Commands
from src.log_config import log_init


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
    acq_channel: Literal[1, 2] = 1

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
    com: str
    timeout_s: float = 1.0


class MPModel(BaseModel):
    name: str
    calibrate_mode: bool
    modbus_settings: ModBusSettings | None = None
    measure_settings: MeasureSettings
    current_limit: float
    loop: bool
    save_table: bool
    save_plot: bool

    @classmethod
    def pydentic_model_init(cls, data: dict) -> Dict[str, "MPModel"]:
        return {name: cls.model_validate(conf) for name, conf in data.items()}


class MatplotlibRealtimePlot:
    def __init__(self, title: str) -> None:
        plt.ion()
        self.fig, self.ax = plt.subplots(num=title)
        self.line, = self.ax.plot([], [], marker="o")
        self.ax.set_title(title)
        self.ax.set_xlabel("Voltage, V")
        self.ax.set_ylabel("Measured value")
        self.ax.grid(True, alpha=0.3)
        self._x: list[float] = []
        self._y: list[float] = []
        self.fig.show()
        self.fig.canvas.draw_idle()

    async def update(self, voltage: float, value: float) -> None:
        self._x.append(float(voltage))
        self._y.append(float(value))
        self.line.set_data(self._x, self._y)
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        await asyncio.sleep(0)

    def save_png(self, file_path: Path) -> None:
        self.fig.savefig(file_path, dpi=150, bbox_inches="tight")

    def close(self) -> None:
        if plt is not None:
            plt.close(self.fig)


class MeasureProcessing:
    def __init__(
        self,
        k: Keithley2600 | None = None,
        mb_client: AsyncModbusSerialClient | None = None,
    ) -> None:
        self.k = k
        self.mb_client = mb_client
        self.mp_model: Dict[str, MPModel] = {}
        self.task_manager = AsyncTaskManager(logger)
        self._active_modbus_fp: tuple[str, int, float] | None = None
        self.output_dir: Path = Path("measure")

    def load_config(self, json_conf: str | Path) -> None:
        try:
            with open(json_conf, "r", encoding="utf-8") as jsn:
                raw = json.load(jsn)
        except Exception:
            logger.error("Measure config not found")
            return
        try:
            self.mp_model = MPModel.pydentic_model_init(raw)
        except Exception as exc:
            logger.error(exc)

    async def run_process(self) -> None:
        if not self.mp_model:
            raise RuntimeError("Measure process list is empty")
        if self.k is None:
            raise RuntimeError("Keithley is not connected")

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.output_dir = Path("measure") / ts
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Measure output dir: {self.output_dir}")

        try:
            for proc_key, process in self.mp_model.items():
                task_name = f"measure_{proc_key}"
                self.task_manager.create_task(self._run_single_process(proc_key, process), task_name)
                task = self.task_manager.tasks.get(task_name)
                if task is not None:
                    await task
        finally:
            await self._safe_keithley_output_off()
            await self._close_modbus()

    async def _run_single_process(self, proc_key: str, process: MPModel) -> None:
        await self._prepare_keithley_source(current_limit=process.current_limit)
        plotter = MatplotlibRealtimePlot(title=f"{proc_key}: {process.name}")
        safe_name = self._sanitize_filename(process.name)
        csv_path = self.output_dir / f"{safe_name}.csv"
        png_path = self.output_dir / f"{safe_name}.png"

        fieldnames = [
            "timestamp",
            "process_key",
            "process_name",
            "cycle",
            "step",
            "voltage_v",
            "value",
            "mode",
            "acq_channel",
        ]

        logger.info(f"Process started: {proc_key} ({process.name})")
        step_idx = 0
        cycle = 0

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                while True:
                    for voltage, delay_s in self._iter_setpoints(process.measure_settings):
                        if process.calibrate_mode:
                            value = await self._measure_calibration_point(
                                process=process,
                                voltage=voltage,
                                delay_s=delay_s,
                            )
                            mode = "modbus_peak"
                        else:
                            value = await self._measure_keithley_current_point(voltage, delay_s)
                            mode = "keithley_current_a"

                        row = {
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "process_key": proc_key,
                            "process_name": process.name,
                            "cycle": cycle,
                            "step": step_idx,
                            "voltage_v": f"{voltage:.6f}",
                            "value": f"{value:.12g}",
                            "mode": mode,
                            "acq_channel": process.measure_settings.acq_channel,
                        }
                        writer.writerow(row)
                        csv_file.flush()
                        await plotter.update(voltage, value)
                        step_idx += 1

                    cycle += 1
                    if not process.loop:
                        break
        finally:
            if process.save_plot:
                plotter.save_png(png_path)
                logger.info(f"Saved plot: {png_path}")
            if process.save_table:
                logger.info(f"Saved table: {csv_path}")
            plotter.close()
            await self._safe_keithley_output_off()
            logger.info(f"Process finished: {proc_key} ({process.name})")

    async def _measure_calibration_point(
        self,
        process: MPModel,
        voltage: float,
        delay_s: float,
    ) -> float:
        if process.modbus_settings is None:
            raise RuntimeError("modbus_settings is required in calibrate_mode")

        connected = await self.connect_modbus(process.modbus_settings)
        if not connected or self.mb_client is None:
            raise RuntimeError("Modbus client is not connected")

        mpp_cmd = MPP_Commands(self.mb_client, logger, process.modbus_settings.id)
        channel_index = int(process.measure_settings.acq_channel - 1)

        await mpp_cmd.start_measure_forced(channel_index)
        await self._keithley_set_voltage(voltage)
        if delay_s > 0:
            await asyncio.sleep(delay_s)

        raw = (
            await mpp_cmd.get_acq1_peak()
            if process.measure_settings.acq_channel == 1
            else await mpp_cmd.get_acq2_peak()
        )
        return float(self._extract_u16_value(raw))

    async def _measure_keithley_current_point(self, voltage: float, delay_s: float) -> float:
        await self._keithley_set_voltage(voltage)
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        return await asyncio.to_thread(self._read_keithley_current_sync)

    def _read_keithley_current_sync(self) -> float:
        if self.k is None:
            raise RuntimeError("Keithley is not connected")
        return float(self.k.smua.measure.i())

    async def _prepare_keithley_source(self, current_limit: float | None = None) -> None:
        if self.k is None:
            raise RuntimeError("Keithley is not connected")

        def _prepare() -> None:
            self.k.smua.source.func = self.k.smua.OUTPUT_DCVOLTS
            self.k.smua.source.output = self.k.smua.OUTPUT_ON
            if current_limit is not None:
                self.k.smua.source.limiti = float(current_limit)

        await asyncio.to_thread(_prepare)

    async def _safe_keithley_output_off(self) -> None:
        if self.k is None:
            return

        def _off() -> None:
            self.k.smua.source.output = self.k.smua.OUTPUT_OFF

        try:
            await asyncio.to_thread(_off)
        except Exception as exc:
            logger.warning(f"Keithley output off error: {exc}")

    async def _keithley_set_voltage(self, voltage: float) -> None:
        if self.k is None:
            raise RuntimeError("Keithley is not connected")

        def _set() -> None:
            self.k.smua.source.levelv = float(voltage)

        await asyncio.to_thread(_set)
        logger.debug(f"Keithley level set: {voltage:.6f} V")

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

    async def connect_modbus(self, modbus_settings: ModBusSettings) -> bool:
        new_fp = (modbus_settings.com, int(modbus_settings.bodrate), float(modbus_settings.timeout_s))
        if (
            self.mb_client is not None
            and getattr(self.mb_client, "connected", False)
            and self._active_modbus_fp == new_fp
        ):
            return True

        await self._close_modbus()

        self.mb_client = AsyncModbusSerialClient(
            port=modbus_settings.com,
            timeout=float(modbus_settings.timeout_s),
            baudrate=int(modbus_settings.bodrate),
            bytesize=8,
            parity="N",
            stopbits=1,
            handle_local_echo=True,
        )
        connected: bool = await self.mb_client.connect()
        if not connected:
            self.mb_client.close()
            self.mb_client = None
            self._active_modbus_fp = None
            return False
        self._active_modbus_fp = new_fp
        return True

    async def _close_modbus(self) -> None:
        if self.mb_client is not None:
            try:
                self.mb_client.close()
            except Exception as exc:
                logger.warning(f"Modbus close error: {exc}")
        self.mb_client = None
        self._active_modbus_fp = None

    @staticmethod
    def _extract_u16_value(raw: bytes) -> int:
        if not raw:
            raise RuntimeError("Empty Modbus response")
        payload = raw
        if len(payload) % 2 == 1:
            payload = payload[1:]
        if len(payload) < 2:
            raise RuntimeError(f"Unexpected Modbus payload: {raw.hex()}")
        regs = [int.from_bytes(payload[i : i + 2], byteorder="big") for i in range(0, len(payload), 2)]
        return int(regs[-1])

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        normalized = re.sub(r"\s+", "_", name.strip())
        normalized = re.sub(r"[^\w\-.()]+", "_", normalized)
        normalized = normalized.strip("._")
        return normalized or "measure"


if __name__ == "__main__":
    address = "10.6.1.222"
    logger = log_init()
    json_conf = Path(__file__).with_name("keithly_script.json")

    try:
        k: Keithley2600 | None = Keithley2600(f"TCPIP0::{address}::INSTR")  # type: ignore
        logger.debug(f"Connected: TCPIP0::{address}::INSTR")
    except Exception as exc:
        k = None
        logger.error(f"Error connection keithley: {exc}")
        raise SystemExit(1)

    try:
        mp = MeasureProcessing(k)
        mp.load_config(json_conf)
        asyncio.run(mp.run_process())
    except KeyboardInterrupt:
        logger.warning("Measure interrupted by user")
    except Exception as exc:
        logger.error(exc)
