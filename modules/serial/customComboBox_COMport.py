import sys
from PyQt6.QtWidgets import QComboBox
import serial.tools.list_ports
import serial

class CustomComboBox_COMport(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clickEvent = 1
        for n, (portname, desc, hwid) in enumerate(sorted(serial.tools.list_ports.comports())):
            super().addItem(portname)

    def mousePressEvent(self, event):
        # Обработка события первоначального нажатия мыши, когда выпадающий список отображается
        super().clear()
        for n, (portname, desc, hwid) in enumerate(sorted(serial.tools.list_ports.comports())):
            super().addItem(portname)
        # Вызов реализации базового класса
        super().mousePressEvent(event)

    
