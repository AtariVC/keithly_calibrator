from __future__ import annotations

import asyncio
import sys

import qasync
import qtmodern.styles
from qtmodern.windows import ModernWindow
from PyQt6 import QtWidgets

try:
    from .main_window import MainWindow
except ImportError:
    from main_window import MainWindow


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.aboutToQuit.connect(loop.stop)

    window = MainWindow()
    modern_window = ModernWindow(window)
    modern_window.show()

    with loop:
        loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
