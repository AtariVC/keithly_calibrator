from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt

class AutoSizeLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.adjust_size)
        
    def adjust_size(self):
        fm = self.fontMetrics()
        text = self.text() or self.placeholderText()
        if text:
            text_width = fm.horizontalAdvance(text)
            new_width = text_width + 30  # + отступы
            new_width = max(60, min(new_width, 400))
            self.setMinimumWidth(new_width)