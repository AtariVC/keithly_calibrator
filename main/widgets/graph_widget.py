import asyncio
import sys

# from save_config import ConfigSaver
from pathlib import Path

import qasync
import qtmodern.styles
from PyQt6 import QtWidgets
from qtpy.uic import loadUi

####### импорты из других директорий ######
# /src
src_path = Path(__file__).resolve().parents[3]
# Добавляем папку src в sys.path
sys.path.append(str(src_path))

from src.log_config import log_init # noqa: E402
from src.modbus_worker import ModbusWorker  # noqa: E402
from src.plot_renderer import GraphPen

class GraphWidget(QtWidgets.QWidget):
    vLayout_acq: QtWidgets.QVBoxLayout

    def __init__(self) -> None:
        super().__init__()
        loadUi(Path(__file__).parent.joinpath("graph_widget.ui"), self)
        self.mw = ModbusWorker()
        self.task = None  # type: ignore
        self.acq_pen = GraphPen(layout=self.vLayout_acq, name="acq_calibrate", color=(255, 255, 0))
        
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    # light(app)
    logger = log_init()
    w: GraphWidget = GraphWidget()
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)
    w.show()
    data: list = [1.4, 34.34, 324.4, 32.4, 89.4, 233.4, 234.4, 2344.4, 234.4]
    w.acq_pen.draw_graph(data, "test", clear=False)  # type: ignore

    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
        except asyncio.CancelledError:
            ...
