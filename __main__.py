import asyncio
import sys

import qasync
import qtmodern.styles
from PyQt6 import QtCore, QtGui, QtWidgets
from qtmodern.windows import ModernWindow

from main.window_constructor import WindowConstructor


def _set_existing_app_font(app: QtWidgets.QApplication) -> None:
    for family in ("Arial", "Helvetica", "Noto Sans", "Sans Serif"):
        if family in QtGui.QFontDatabase.families():
            app.setFont(QtGui.QFont(family, 11))
            return


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    _set_existing_app_font(app)
    qtmodern.styles.dark(app)
    w: WindowConstructor = WindowConstructor()
    mw: ModernWindow = ModernWindow(w)
    mw.setAttribute(
        QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False
    )  # fix flickering on resize window

    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app.aboutToQuit.connect(event_loop.stop)
    mw.show()

    with event_loop:
        event_loop.run_forever()
