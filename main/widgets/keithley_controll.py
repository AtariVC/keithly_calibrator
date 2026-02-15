import asyncio
import sys
from pathlib import Path

import qasync
import qtmodern.styles
from PyQt6 import QtWidgets
from qtpy.uic import loadUi

####### импорты из других директорий ######
# /src
src_path = Path(__file__).resolve().parents[4]
modules_path = Path(__file__).resolve().parents[3]
# Добавляем папку src в sys.path
sys.path.append(str(src_path))
sys.path.append(str(modules_path))

from modules.serial.main_serial_dialog_tcp import SerialConnect  # noqa: E402
from src.async_task_manager import AsyncTaskManager  # noqa: E402
from src.log_config import log_init  # noqa: E402
from main.widgets.graph_widget import GraphWidget  # noqa: E402

try:
    import keithley2600  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    keithley2600 = None

try:
    import pyvisa  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    pyvisa = None


class Keithley2600Client:
    def __init__(self, timeout_ms: int = 3000) -> None:
        self.timeout_ms = timeout_ms
        self.rm = None
        self.smu = None
        self.resource = None
        self.idn = None

    def connect(self) -> str | None:
        if keithley2600 is None:
            raise RuntimeError("keithley2600 не установлен")
        if self.smu is not None:
            return self.idn
        self.idn = self._find_resource()
        if not self.idn:
            return None
        self.smu = keithley2600.Keithley2600(self.resource)
        return self.idn

    def _find_resource(self) -> str | None:
        if pyvisa is None:
            raise RuntimeError("pyvisa не установлен для авто-поиска")
        self.rm = pyvisa.ResourceManager()
        for res in self.rm.list_resources():
            try:
                inst = self.rm.open_resource(res)
                inst.timeout = self.timeout_ms
                idn = inst.query("*IDN?").strip()
                inst.close()
                if "KEITHLEY" in idn.upper() and "2611" in idn:
                    self.resource = res
                    return idn
            except Exception:
                continue
        return None

    def _ensure_connected(self) -> None:
        if self.smu is None:
            raise RuntimeError("Keithley 2611B не подключен")

    def prepare_source(self) -> None:
        self._ensure_connected()
        self.smu.smua.source.func = self.smu.smua.OUTPUT_DCVOLTS
        self.smu.smua.source.output = self.smu.smua.OUTPUT_ON

    def set_level(self, level: float) -> None:
        self._ensure_connected()
        self.smu.smua.source.levelv = level

    def output_off(self) -> None:
        if self.smu is None:
            return
        self.smu.smua.source.output = self.smu.smua.OUTPUT_OFF


class KeithleyControl(QtWidgets.QWidget):
    doubleSpinBox_U1: QtWidgets.QDoubleSpinBox
    doubleSpinBox_dur: QtWidgets.QDoubleSpinBox
    doubleSpinBox_T: QtWidgets.QDoubleSpinBox
    spinBox_N: QtWidgets.QSpinBox
    checkBox_cont_mode: QtWidgets.QCheckBox
    pushButton_start: QtWidgets.QPushButton
    comboBox_mpp_ch: QtWidgets.QComboBox

    def __init__(self, *args) -> None:
        super().__init__(*args)
        loadUi(Path(__file__).parent.joinpath("keithley_controll.ui"), self)
        self.logger = log_init()
        self.parent = args[0]
        self.task_manager = AsyncTaskManager(self.logger)
        self.device = Keithley2600Client()
        self._running = False
        self.graph_widget: GraphWidget = self.parent.w_graph_widget  # type: ignore
        
        self.mpp_lvl = 0
        
        if __name__ != "__main__":
            self.w_ser_dialog: SerialConnect = self.parent.w_ser_dialog  # type: ignore
            self.w_ser_dialog.coroutine_finished.connect(self.init_mb_cmd)
            self.mpp_cmd = self.w_ser_dialog.get_commands_interface(self.logger)

        self.checkBox_cont_mode.toggled.connect(self.on_cont_mode_toggled)
        self.on_cont_mode_toggled(self.checkBox_cont_mode.isChecked())
        self.pushButton_start.clicked.connect(self.pushButton_start_handler)
        self.w_ser_dialog.disconnected.connect(self.on_serial_disconnected)
        
    async def on_serial_disconnected(self):
        await self._stop_measuring("Serial отключен")
        # Обновляем команды через фабрику (вернутся null‑клиент команды)
        if self.w_ser_dialog:
            self.cm_cmd, self.mpp_cmd = self.w_ser_dialog.get_commands_interface(self.logger)
    
    async def init_mb_cmd(self) -> None:
        """Инициализация командного интерфейса МПП и ЦМ"""
        if not self.w_ser_dialog or not self.w_ser_dialog.is_modbus_ready():
            self.logger.warning("Modbus не готов: нет активного serial-соединения")
            self.cm_cmd, self.mpp_cmd = (
                self.w_ser_dialog.get_commands_interface(self.logger)
                if self.w_ser_dialog
                else (self.cm_cmd, self.mpp_cmd)
            )
            return
        try:
            ready = await self.w_ser_dialog.check_connection()
        except Exception as e:
            self.logger.warning(f"Не удалось обновить статус ЦМ/МПП при инициализации команд: {e}")
            self.cm_cmd, self.mpp_cmd = self.w_ser_dialog.get_commands_interface(self.logger)
            return
        # Всегда берём команды через фабрику, она сама подставит нужный клиент/mpp_id
        self.cm_cmd, self.mpp_cmd = self.w_ser_dialog.get_commands_interface(self.logger)
        if not ready:
            self.logger.warning("ЦМ/МПП недоступны — запуск измерений невозможен")

    def on_cont_mode_toggled(self, checked: bool) -> None:
        self.spinBox_N.setEnabled(not checked)

    def _set_running_state(self, running: bool) -> None:
        self._running = running
        self.pushButton_start.setText("Остановить" if running else "Запуск")

    def _set_search_state(self, searching: bool) -> None:
        if searching:
            self.pushButton_start.setText("Поиск...")
        else:
            self._set_running_state(self._running)
        self.pushButton_start.setEnabled(not searching)

    def _show_warning(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, "Keithley 2611B", message)
        self.logger.warning(message)

    async def _ensure_connected(self) -> bool:
        self.logger.info("Поиск Keithley 2611B...")
        try:
            idn = await asyncio.to_thread(self.device.connect)
        except Exception as exc:
            self._show_warning(f"Нет подключения к Keithley 2611B: {exc}")
            return False
        if not idn:
            self._show_warning("Keithley 2611B не обнаружен")
            return False
        self.logger.info(f"Keithley 2611B подключен: {idn}")
        return True

    async def _apply_level(self, level: float) -> None:
        await asyncio.to_thread(self.device.set_level, level)

    async def _output_off(self) -> None:
        if self.device.smu is None:
            return
        try:
            await asyncio.to_thread(self.device.output_off)
            self.logger.info("Keithley 2611B: выход отключен")
        except Exception as exc:
            self.logger.warning(f"Не удалось отключить выход Keithley 2611B: {exc}")

    async def _pulse_loop(self, u1: float, dur_s: float, period_s: float, count: int | None) -> None:
        low_s = max(period_s - dur_s, 0.0)
        done = 0
        while self._running and (count is None or done < count):
            await self._apply_level(u1)
            if dur_s > 0:
                await asyncio.sleep(dur_s)
            await self._apply_level(0.0)
            if low_s > 0:
                await asyncio.sleep(low_s)
            if dur_s == 0 and low_s == 0:
                await asyncio.sleep(0)
            done += 1
            await self._mpp_read_sequence()
            
    async def _mpp_get_lvl(self) -> int:
        try:
            mpp_ch = 0 if self.comboBox_mpp_ch.currentIndex() == 0 else 1
            output: bytes = self.mpp_cmd.start_measure_forced(mpp_ch)
            zero_lvl: int = max(self.parser.mpp_pars_16b(output))
            return zero_lvl + 20
        except Exception as e:
            self.logger.error(e)
            return 0   
    
    async def _mpp_start(self, mpp_lvl) -> None:
        await self.mpp_cmd.set_level(mpp_lvl)
        await self.mpp_cmd.start_measure(on=1)
    
    async def _mpp_stop(self) -> None:
        await self.mpp_cmd.start_measure(on=0)
    
    async def _mpp_read_sequence(self) -> None:
        await self.mpp_cmd.issue_waveform()
        mpp_ch = 0 if self.comboBox_mpp_ch.currentIndex() == 0 else 1
        result_ch: bytes = await self.mpp_cmd.read_oscill(ch=mpp_ch)
        result_ch_int: list[int] = await self.parser.mpp_pars_16b(result_ch)
        await self.graph_widget.acq_pen.draw_graph(
                        result_ch_int,
                        save_log=False,
                        clear=True,
                    )  # x, y

    async def _run_sequence(self) -> None:
        try:
            u1 = float(self.doubleSpinBox_U1.value())
            dur_us = float(self.doubleSpinBox_dur.value())
            period_us = float(self.doubleSpinBox_T.value())
            count = int(self.spinBox_N.value())
            continuous = self.checkBox_cont_mode.isChecked()

            await asyncio.to_thread(self.device.prepare_source)
            
            lvl = await self._mpp_get_lvl()
            await self._mpp_start(lvl)
            if continuous:
                self.logger.info(
                    f"Keithley 2611B: непрерывные импульсы U1={u1} В, "
                    f"dur={dur_us} мкс, T={period_us} мкс"
                )
                await self._pulse_loop(u1, dur_us * 1e-6, period_us * 1e-6, None)
            elif count == 0:
                self.logger.info(f"Keithley 2611B: постоянный уровень {u1} В")
                await self._apply_level(u1)
                while self._running:
                    await asyncio.sleep(0.2)
                await self._mpp_read_sequence()
            else:
                self.logger.info(
                    f"Keithley 2611B: импульсы U1={u1} В, dur={dur_us} мкс, "
                    f"T={period_us} мкс, N={count}"
                )
                await self._pulse_loop(u1, dur_us * 1e-6, period_us * 1e-6, count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.error(f"Ошибка выполнения Keithley 2611B: {exc}")
        finally:
            await self._output_off()
            self._set_running_state(False)

    @qasync.asyncSlot()
    async def pushButton_start_handler(self) -> None:
        if not self._running:
            self._set_search_state(True)
            try:
                if not await self._ensure_connected():
                    return
                self._set_running_state(True)
                self.mpp_lvl = self._mpp_get_lvl()
                self.task_manager.create_task(self._run_sequence(), "keithley_task")
            finally:
                self._set_search_state(False)
        else:
            self._set_running_state(False)
            self.task_manager.cancel_task("keithley_task")
            await self._output_off()
        
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    # light(app)
    logger = log_init()
    w: KeithleyControl = KeithleyControl()
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)
    w.show()
    
    
    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
        except asyncio.CancelledError:
            ...
