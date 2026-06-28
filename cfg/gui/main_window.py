from __future__ import annotations

import asyncio
import json
import platform
import re
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
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keithley2600 import Keithley2600
from keithly_script import MeasureProcessing

from qcustomwidgets.widgets.button import Button
from qcustomwidgets.resources.compile_icons import svg_path

DEFAULT_KEITHLEY_ADDRESS = "10.6.1.222"
PLOT_BG = "#2b2b2b"
PLOT_AXES_BG = "#242424"
PLOT_TEXT = "#d7dce2"
PLOT_GRID = "#6c737d"

_SVG = svg_path()


class JsonHighlighter(QSyntaxHighlighter):
    _RE_KEY = re.compile(r'("(?:[^"\\]|\\.)*")\s*:')
    _RE_STR = re.compile(r'"(?:[^"\\]|\\.)*"')
    _RE_NUM = re.compile(r'(?<!["\w])-?\b\d+(?:\.\d*)?(?:[eE][+-]?\d+)?\b')
    _RE_KW = re.compile(r'\b(true|false|null)\b')
    _RE_PUNCT = re.compile(r'[{}\[\],:]')

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._key_fmt = self._fmt("#9cdcfe")
        self._str_fmt = self._fmt("#ce9178")
        self._num_fmt = self._fmt("#b5cea8")
        self._kw_fmt = self._fmt("#569cd6")
        self._punct_fmt = self._fmt("#808080")

    @staticmethod
    def _fmt(color: str) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        return f

    def highlightBlock(self, text: str) -> None:
        key_spans: list[tuple[int, int]] = []
        for m in self._RE_KEY.finditer(text):
            g = m.group(1)
            s = m.start()
            e = s + len(g)
            self.setFormat(s, e - s, self._key_fmt)
            key_spans.append((s, e))

        for m in self._RE_STR.finditer(text):
            s, e = m.start(), m.end()
            if not any(ks <= s < ke for ks, ke in key_spans):
                self.setFormat(s, e - s, self._str_fmt)

        for m in self._RE_NUM.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._num_fmt)

        for m in self._RE_KW.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._kw_fmt)

        for m in self._RE_PUNCT.finditer(text):
            self.setFormat(m.start(), 1, self._punct_fmt)


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
            0.02, 0.98, "",
            transform=self.ax.transAxes,
            va="top", color=PLOT_TEXT,
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
        self.rightPanelLayout.setStretch(1, 1)  # jsonEditorWidget expands
        self.rightPanelLayout.setStretch(3, 1)  # logTextEdit expands

        self._setup_plot()
        self._setup_json_panel()
        self._setup_signals()

    def _setup_plot(self) -> None:
        self.figure = Figure(figsize=(6, 4), tight_layout=True, facecolor=PLOT_BG)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.canvas.setStyleSheet(f"background-color: {PLOT_BG};")
        style_axes(self.axes)
        self.plotContainer.layout().addWidget(self.canvas)
        self.canvas.draw_idle()

    def _setup_json_panel(self) -> None:
        font = QFont("Menlo, Monaco, Courier New, monospace")
        font.setPointSize(11)
        self.jsonEditorWidget.setFont(font)
        self.jsonEditorWidget.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e;"
            "  color: #d4d4d4;"
            "  border: 1px solid #3c3c3c;"
            "  border-radius: 4px;"
            "}"
        )
        self._highlighter = JsonHighlighter(self.jsonEditorWidget.document())
        self.jsonEditorWidget.installEventFilter(self)

        layout: QtWidgets.QHBoxLayout = self.jsonFileRowLayout

        def _btn(icon: str, tip: str) -> Button:
            b = Button(icons=_SVG / icon, flat=True, tooltip=tip)
            b.setFixedSize(28, 28)
            layout.addWidget(b)
            return b

        self.selectJsonButton = _btn("folder-open.svg", "Выбрать JSON")
        self.saveJsonButton = _btn("save.svg", "Сохранить JSON")
        self.editJsonButton = _btn("editor.svg", "Открыть в редакторе")
        self.reloadJsonButton = _btn("repeat.svg", "Перезагрузить JSON")

    def _setup_signals(self) -> None:
        self.selectJsonButton.clicked.connect(self.select_json_file)
        self.saveJsonButton.clicked.connect(self.save_json_file)
        self.editJsonButton.clicked.connect(self.open_json_in_editor)
        self.reloadJsonButton.clicked.connect(self.reload_json)
        self.startStopButton.clicked.connect(self.on_start_stop_clicked)
        self.connectKeithleyButton.clicked.connect(self.connect_keithley_clicked)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.jsonEditorWidget:
            if event.type() == QtCore.QEvent.Type.DragEnter:
                if self._event_has_json_file(event):
                    event.acceptProposedAction()
                    return True
            if event.type() == QtCore.QEvent.Type.Drop:
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
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выбрать JSON", "", "JSON files (*.json)"
        )
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
        pretty = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        self.jsonEditorWidget.setPlainText(pretty)
        self.append_log(f"JSON загружен: {path}")

    def save_json_file(self) -> None:
        text = self.jsonEditorWidget.toPlainText()
        if not text.strip():
            self.append_log("Нечего сохранять — редактор пуст")
            return
        try:
            json.loads(text)
        except Exception as exc:
            self.append_log(f"Ошибка JSON: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка JSON", str(exc))
            return

        if self.json_path is None:
            file_name, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить JSON", "", "JSON files (*.json)"
            )
            if not file_name:
                return
            self.json_path = Path(file_name)
            self.jsonFileLineEdit.setText(self.json_path.name)

        try:
            self.json_path.write_text(text, encoding="utf-8")
            self.append_log(f"JSON сохранён: {self.json_path}")
        except Exception as exc:
            self.append_log(f"Ошибка сохранения: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка сохранения", str(exc))

    def reload_json(self) -> None:
        if self.json_path is None:
            self.append_log("JSON-файл не выбран")
            return
        self.load_json_file(self.json_path)

    def validate_current_json_file(self) -> bool:
        text = self.jsonEditorWidget.toPlainText()
        if not text.strip():
            QtWidgets.QMessageBox.warning(self, "JSON", "JSON-файл не выбран")
            self.append_log("JSON-файл не выбран")
            return False
        try:
            json.loads(text)
        except Exception as exc:
            self.append_log(f"Ошибка JSON: {exc}")
            QtWidgets.QMessageBox.critical(self, "Ошибка JSON", str(exc))
            return False
        if self.json_path:
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
                subprocess.Popen([code_cmd, path] if code_cmd else ["notepad.exe", path])
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
