import asyncio
import sys
from pathlib import Path

import qasync
import qtmodern.styles
from pymodbus.client import AsyncModbusSerialClient
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QDoubleValidator, QFont, QIntValidator
from PyQt6.QtWidgets import (
    QGroupBox,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qtmodern.windows import ModernWindow
from qtpy.uic import loadUi
from main.widgets.graph_widget import GraphWidget

# /src - add path before imports from those locations
src_path = Path(__file__).resolve().parents[3]
modules_path = Path(__file__).resolve().parents[3]

sys.path.append(str(src_path))
sys.path.append(str(modules_path))

from main.widgets.keithley_controll import KeithleyControl  # noqa: E402
from modules.serial.main_serial_dialog_tcp import SerialConnect  # noqa: E402
from src.log_config import log_init # noqa: E402
from src.main_window_maker import (  # noqa: E402
    create_split_widget,
    create_tab_widget_items,
)
from src.modbus_worker import ModbusWorker  # noqa: E402


class WindowConstructor(QtWidgets.QMainWindow):
    gridLayout_main_split: QtWidgets.QGridLayout

    def __init__(self) -> None:
        super().__init__()
        loadUi(Path(__file__).parent.joinpath("window_constructor.ui"), self)
        self.resize(1300, 800)
        self.mw: ModbusWorker = ModbusWorker()
        self.logger = log_init()
        self.init_widgets()

    def widget_model(self):
        spacer_v = QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        return {
            "Калибровка": {
                "Воздействие мпп": self.keithley_control,
                # "Измерение": self.measure_widget,
                # "Счетчик частиц": self.flux_widget,
                "spacer": spacer_v,
                "Подключение": self.w_ser_dialog,
            }
        }

    def on_tab_widget_handler(self, index: int):
        '''
        Функция-обработчик изменения вкладок в QTabWidget.
        Вызывается при переключении между вкладками и выполняет необходимые действия в зависимости от выбранной вкладки.
        '''
        # tab_text: str = self.tab_widget.tabText(index)
        # if tab_text == "Вьюер":
        #     clear_left_widget(self.w_graph_widget, self.graph_viewer_widget)

        # if tab_text == "Осциллограф":
        #     clear_left_widget(self.graph_viewer_widget, self.w_graph_widget)

        # if tab_text == "Вьюер":
        #     self.current_left_widget = self.graph_viewer_widget
        # elif tab_text == "Осциллограф":
        #     self.current_left_widget = self.w_graph_widget
        ...

    def init_widgets(self):
        self.w_graph_widget: GraphWidget = GraphWidget()
        self.w_ser_dialog: SerialConnect = SerialConnect(self.logger)
        # remove tab tcp connect
        for i in range(self.w_ser_dialog.tabWidget_serial.count()):
            if self.w_ser_dialog.tabWidget_serial.tabText(i).strip().lower() == "tcp":
                self.w_ser_dialog.tabWidget_serial.removeTab(i)
                break
        self.keithley_control: KeithleyControl = KeithleyControl(self)
        self.w_ser_dialog.checkBox_mpp_only.hide()
        self.client = self.w_ser_dialog.client
        model = self.widget_model()
        self.tab_widget = create_tab_widget_items(model, self.on_tab_widget_handler)
        create_split_widget(
            self.gridLayout_main_split, self.w_graph_widget, self.tab_widget
        )


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    w: WindowConstructor = WindowConstructor()
    mw: ModernWindow = ModernWindow(w)
    mw.setAttribute(
        QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False
    )  # fix flickering on resize window
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    mw.show()

    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
        except asyncio.CancelledError:
            ...
