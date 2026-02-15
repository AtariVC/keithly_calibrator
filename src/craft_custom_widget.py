from PyQt6.QtWidgets import QGroupBox, QGridLayout, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QFont
from PyQt6 import QtWidgets

def add_serial_widget(vlayout_ser_connect: QtWidgets.QVBoxLayout , w_ser_dialog) -> None:
    """Добавляет виджет подключения сериал в layout главного окна
    Args:
        vlayout_ser_connect ([QtWidgets.QVBoxLayout]): layout главного окна
        w_ser_dialog ([QtWidgets.QDialog]): виджет подключения сериал
    """
    spacer_g = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    spacer_v = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


    grBox: QGroupBox = QGroupBox("Подключение")
    # Настройка шрифта для QGroupBox
    font = QFont()
    font.setFamily("Arial")         # Шрифт
    font.setPointSize(12)           # Размер шрифта
    font.setBold(False)             # Жирный текст
    font.setItalic(False)           # Курсив
    grBox.setFont(font)
    gridL: QGridLayout = QGridLayout()
    vlayout_ser_connect.addWidget(grBox)
    grBox.setMinimumWidth(2)
    grBox.setLayout(gridL)

    # gridL.addItem(spacer_g, 0, 0)
    # gridL.addItem(spacer_g, 0, 0)
    gridL.addWidget(w_ser_dialog, 0, 0)

    grBox.setMaximumHeight(w_ser_dialog.minimumHeight())
    grBox.setMinimumWidth(w_ser_dialog.minimumWidth())

    # grBox.setMaximumHeight(w_ser_dialog.height() + 35)
    # grBox.setMinimumWidth(w_ser_dialog.width() + 20)



