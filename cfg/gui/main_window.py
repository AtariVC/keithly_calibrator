from __future__ import annotations

import asyncio
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import qasync
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6 import QtCore, QtWidgets, uic

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keithley2600 import Keithley2600
from keithly_script import MeasureProcessing


DEFAULT_KEITHLEY_ADDRESS = "10.6.1.222"
PLOT_BG = "#2b2b2b"
PLOT_AXES_BG = "#242424"
PLOT_TEXT = "#d7dce2"
PLOT_GRID = "#6c737d"


def style_axes(ax: Any, title: str | None = None, x_name: str = "Voltage, V", y_name: str = "Measured value") -> None:
    ax.figure.set_facecolor(PLOT_BG)
    ax.set_facecolor(PLOT_AXES_BG)
    if title is not None:
        ax.set_title(title, color=PLOT_TEXT)
    ax.set_xlabel(x_name, color=PLOT_TEXT)
    ax.set_ylabel(y_name, color=PLOT_TEXT)
    ax.tick_params(colors=PLOT_TEXT)
    for spine in ax.spines.values():
        spine.set_color(PLOT_TEXT)
    ax.grid(True, color=PLOT_GRID, alpha=0.35)


class GuiRealtimePlotter:
    def __init__(self, window: "MainWindow", title: str, x_name: str, y_name: str) -> None:
        self.window = window
        self.ax = window.axes
        self.canvas = window.canvas
        self.ax.clear()
        self.line, = self.ax.plot([], [], marker="o", color="#4da3ff")
        self.fit_line, = self.ax.plot([], [], linestyle="--", color="#ff6b6b")
        self.fit_text = self.ax.text(
            0.02,
            0.98,
            "",
            transform=self.ax.transAxes,
            va="top",
            color=PLOT_TEXT,
            bbox={"boxstyle": "round", "facecolor": PLOT_AXES_BG, "edgecolor": PLOT_GRID, "alpha": 0.9},
        )
        style_axes(self.ax, title, x_name, y_name)
        self._x: list[float] = []
        self._y: list[float] = []
        self.canvas.draw_idle()

    async def update(self, voltage: float, value: float) -> None:
        self._x.append(float(voltage))
        self._y.append(float(value))
        self.line.set_data(self._x, self._y)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()
        await asyncio.sleep(0)

    async def update_calibration_fit(self, a: float | None, b: float | None) -> None:
        if a is None or b is None or len(self._x) < 2:
            self.fit_line.set_data([], [])
            self.fit_text.set_text("")
        else:
            x_min = min(self._x)
            x_max = max(self._x)
            self.fit_line.set_data([x_min, x_max], [a * x_min + b, a * x_max + b])
            self.fit_text.set_text(f"y = {a:.6f}x {b:+.6f}")
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()
        await asyncio.sleep(0)

    def save_png(self, file_path: Path) -> None:
        self.window.figure.savefig(file_path, dpi=150, bbox_inches="tight")

    def close(self) -> None:
        self.canvas.draw_idle()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ui_path = Path(__file__).with_name("main_window.ui")
        uic.loadUi(ui_path, self)

        self.json_path: Path | None = None
        self.keithley: Any | None = None
        self.measure_processing: MeasureProcessing | None = None
        self.measure_task: asyncio.Task[None] | None = None

        self.keithleyIpLineEdit.setText(DEFAULT_KEITHLEY_ADDRESS)
        self.horizontalLayout.setStretch(0, 3)
        self.horizontalLayout.setStretch(1, 2)
        self.rightPanelLayout.setStretch(2, 0)
        self.rightPanelLayout.setStretch(4, 1)
        self._setup_plot()
        self._setup_signals()
        self.jsonDropArea.installEventFilter(self)

    def _setup_plot(self) -> None:
        self.figure = Figure(figsize=(6, 4), tight_layout=True, facecolor=PLOT_BG)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.canvas.setStyleSheet(f"background-color: {PLOT_BG};")
        style_axes(self.axes)
        self.plotContainer.layout().addWidget(self.canvas)
        self.canvas.draw_idle()

    def _setup_signals(self) -> None:
        self.selectJsonButton.clicked.connect(self.select_json_file)
        self.editJsonButton.clicked.connect(self.open_json_in_editor)
        self.reloadJsonButton.clicked.connect(self.reload_json)
        self.startStopButton.clicked.connect(self.on_start_stop_clicked)
        self.connectKeithleyButton.clicked.connect(self.connect_keithley_clicked)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.jsonDropArea and event.type() == QtCore.QEvent.Type.DragEnter:
            if self._event_has_json_file(event):
                event.acceptProposedAction()
                return True
        if obj is self.jsonDropArea and event.type() == QtCore.QEvent.Type.Drop:
            path = self._json_path_from_drop_event(event)
            if path is not None:
                self.load_json_file(path)
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    def _event_has_json_file(self, event: QtCore.QEvent) -> bool:
        return self._json_path_from_drop_event(event) is not None

    def _json_path_from_drop_event(self, event: QtCore.QEvent) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".json" and path.is_file():
                return path
        return None

    def append_log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.logTextEdit.appendPlainText(f"[{ts}] {message}")

    def select_json_file(self) -> None:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_name = filedialog.askopenfilename(
            title="Выбрать JSON",
            filetypes=[("JSON files", "*.json")],
        )
        root.destroy()
        if file_name:
            self.load_json_file(Path(file_name))

    def load_json_file(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            json.loads(text)
        except Exception as exc:
            self.append_log(f"Ошибка JSON: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка JSON", str(exc))
            return
        self.json_path = path
        self.jsonFileLineEdit.setText(path.name)
        self.jsonDropAreaLabel.setText(f"Загружен JSON:\n{path.name}")
        self.append_log(f"JSON загружен: {path}")

    def reload_json(self) -> None:
        if self.json_path is None:
            self.append_log("JSON-файл не выбран")
            return
        self.load_json_file(self.json_path)

    def validate_current_json_file(self) -> bool:
        if self.json_path is None:
            QtWidgets.QMessageBox.warning(self, "JSON", "JSON-файл не выбран")
            self.append_log("JSON-файл не выбран")
            return False
        try:
            text = self.json_path.read_text(encoding="utf-8")
            json.loads(text)
        except Exception as exc:
            self.append_log(f"Ошибка JSON: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка JSON", str(exc))
            return False
        self.append_log(f"JSON проверен: {self.json_path}")
        return True

    def open_json_in_editor(self) -> None:
        if self.json_path is None:
            self.append_log("JSON-файл не выбран")
            return

        path = str(self.json_path)
        try:
            if platform.system() == "Windows":
                code_cmd = shutil.which("code")
                if code_cmd:
                    subprocess.Popen([code_cmd, path])
                else:
                    subprocess.Popen(["notepad.exe", path])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.append_log(f"JSON открыт в редакторе: {self.json_path}")
        except Exception as exc:
            self.append_log(f"Ошибка открытия редактора: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка редактора", str(exc))

    @qasync.asyncSlot()
    async def connect_keithley_clicked(self) -> None:
        await self.connect_keithley()

    async def connect_keithley(self) -> bool:
        ip_address = self.keithleyIpLineEdit.text().strip()
        if not ip_address:
            QtWidgets.QMessageBox.warning(self, "Keithley", "Введите IP-адрес Keithley")
            return False

        self.connectKeithleyButton.setEnabled(False)
        self.keithleyStatusLabel.setText("Подключение...")
        self.append_log(f"Подключение Keithley: {ip_address}")
        try:
            self.keithley = await asyncio.to_thread(
                Keithley2600,
                f"TCPIP0::{ip_address}::INSTR",
            )
        except Exception as exc:
            self.keithley = None
            self.keithleyStatusLabel.setText("Ошибка подключения")
            self.append_log(f"Ошибка подключения Keithley: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка подключения Keithley", str(exc))
            return False
        finally:
            self.connectKeithleyButton.setEnabled(True)

        self.keithleyStatusLabel.setText("Подключен")
        self.connectKeithleyButton.setText("Переподключить")
        self.append_log(f"Keithley подключен: {ip_address}")
        return True

    @qasync.asyncSlot()
    async def on_start_stop_clicked(self) -> None:
        if self.measure_task is not None and not self.measure_task.done():
            await self.stop_measurement()
        else:
            await self.start_measurement()

    async def start_measurement(self) -> None:
        if not self.validate_current_json_file():
            return
        if self.keithley is None and not await self.connect_keithley():
            self.startStopButton.setText("Запустить")
            return
        if self.json_path is None:
            return

        self.measure_processing = MeasureProcessing(
            self.keithley,
            plotter_factory=lambda title, x_name, y_name: GuiRealtimePlotter(self, title, x_name, y_name),
        )
        self.measure_processing.load_config(self.json_path)
        if not self.measure_processing.mp_model:
            self.append_log("Ошибка JSON: конфигурация измерения не загружена")
            QtWidgets.QMessageBox.critical(self, "Ошибка JSON", "Конфигурация измерения не загружена")
            return
        self.measure_task = asyncio.create_task(self._run_measurement_task())
        self.startStopButton.setText("Остановить")
        self.append_log("Измерение запущено")

    async def _run_measurement_task(self) -> None:
        try:
            if self.measure_processing is None:
                return
            await self.measure_processing.run_process()
            self.append_log("Измерение завершено")
        except asyncio.CancelledError:
            self.append_log("Измерение остановлено")
            raise
        except Exception as exc:
            self.append_log(f"Ошибка измерения: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка измерения", str(exc))
        finally:
            self.startStopButton.setText("Запустить")
            self.measure_task = None

    async def stop_measurement(self) -> None:
        task = self.measure_task
        self.startStopButton.setEnabled(False)
        try:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if self.measure_processing is not None:
                await self.measure_processing._safe_keithley_output_off()
                await self.measure_processing._close_modbus()
        finally:
            self.measure_task = None
            self.startStopButton.setText("Запустить")
            self.startStopButton.setEnabled(True)
            self.append_log("Измерение остановлено")

    def closeEvent(self, event: QtCore.QEvent) -> None:
        if self.measure_task is not None and not self.measure_task.done():
            self.measure_task.cancel()
        event.accept()
