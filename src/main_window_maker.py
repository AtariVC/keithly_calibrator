
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QSpacerItem, QSizePolicy, QSplitter, QTabWidget, QScrollArea, QGridLayout
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from typing import Optional, Sequence, Callable, Union, Dict

def create_split_widget(gridLayout_main_split: QGridLayout, 
                        left_widget: QWidget,
                        right_widget: QTabWidget) -> None:
    """Создает и добавляет в layout разделитель (QSplitter) с двумя виджетами.
    
    Функция принимает основной QGridLayout и два виджета (обычно QTabWidget), 
    создает горизонтальный QSplitter, размещает в нем оба виджета 
    и добавляет разделитель в указанный layout.

    Args:
        gridLayout_main_split (QGridLayout): Основной layout, в который будет добавлен QSplitter.
        left_widget (QTabWidget): Виджет, который будет размещен слева в QSplitter.
        right_widget (QTabWidget): Виджет, который будет размещен справа в QSplitter.
    """
    # Виджеты
    # w_graph_widget: GraphWidget = GraphWidget()
    # tab_widget: QTabWidget = create_tab_widget_items(widget_model)
    splitter = QSplitter()
    gridLayout_main_split.addWidget(splitter)
    splitter.addWidget(left_widget)
    splitter.addWidget(right_widget)

def replace_left_widget_splitter(old_left_widget: QWidget, new_left_widget: QWidget):
        """Заменяет левый виджет в сплиттере"""
    # 1. Находим сплиттер (родительский виджет)
        splitter = old_left_widget.parentWidget()
        if not isinstance(splitter, QSplitter):
            return

        # 2. Находим индекс нашего виджета в сплитере
        index = splitter.indexOf(old_left_widget)
        if index == -1:
            return

        # 3. Заменяем виджет
        splitter.replaceWidget(index, new_left_widget)
        new_left_widget.show()
        old_left_widget.hide()

def create_tab_widget_items(widget_model: Dict[str, Dict[str, QWidget]],
                            tab_widget_handler: Optional[Callable] = None) -> QTabWidget:
    """Создает и возвращает QTabWidget с организованными вкладками виджетов.
    Функция создает многоуровневый интерфейс с:
    - Вкладками (QTabWidget)
    - Прокручиваемыми областями (QScrollArea) 
    - Групповыми блоками (QGroupBox) для каждого виджета

    :Args:
        widget_model (Dict[str, Dict[str, QWidget]]): 
            Иерархическая структура виджетов:
                - Ключ 1 уровня: Название вкладки (str)
                - Значение: Словарь {
                    "название виджета": QWidget-объект
                }
        tab_widget_handler (Optional[Callable] = None): 
        Обработчик событий изменения вкладок tabwidget.

    :Return:

        QTabWidget: Готовый виджет с вкладками, содержащий:
            - Каждая вкладка содержит ScrollArea
            - Каждый виджет оформлен в GroupBox
            - Автоматические отступы и размеры
            - Стандартизированное форматирование шрифтов

    :Example:
        widget_structure = {

            "Графики": {
                "График 1": GraphWidget(),
                "График 2": GraphWidget()},

            "Настройки": {
                "Параметры": SettingsWidget()}
        }
        tab_widget = create_tab_widget_items(widget_structure)
        
    """
    
    def _grBox_wrapper(widget: QWidget, name: str) -> QGroupBox:
        """Создает GroupBox с заданным виджетом внутри."""
        grBox_widget: QGroupBox = QGroupBox(name)
        vLayout_grBox_widget: QVBoxLayout = QVBoxLayout(grBox_widget)
        grBox_widget.setMaximumHeight(widget.minimumHeight() + 40)
        grBox_widget.setMinimumWidth(widget.minimumWidth() + 20)
        vLayout_grBox_widget.addWidget(widget)
        font = QFont()
        font.setFamily("Arial")
        font.setPointSize(12)
        grBox_widget.setFont(font)
        return grBox_widget
    
    def _tab_factories(widget_model: Dict[str, Dict[str, QWidget]]):
        """Создает словарь фабричных функций для генерации содержимого вкладок.

        Args:
            widget_model (Dict[str, Dict[str, QWidget]]): 
                Словарь конфигурации вкладок, где:
                    - Ключ (str): название вкладки
                    - Значение (Dict[str, QWidget]): словарь виджетов в формате:
                        {"название виджета": QWidget-объект}

        Returns:
            Dict[str, Callable]: 
                Словарь фабричных функций в формате:
                    {"название вкладки": функция-widget_maker}
                Где widget_maker принимает (widgets: Dict[str, QWidget], tab_widget: QTabWidget)
                и возвращает QWidget с оформленными элементами.
        """
        dict_tab_factry = {}
        for tab_name in widget_model.keys():
            dict_tab_factry[tab_name]= _widget_maker
        return dict_tab_factry

    def _widget_maker(widgets: Dict[str, Optional[QWidget| QSpacerItem]]):
        """Фабрика для создания содержимого вкладки."""
        ######################
        spacer_v = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        spacer_v_scroll = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Создаем QScrollArea для прокручиваемого содержимого
        scroll_area_menu = QScrollArea()
        scroll_area_menu.setWidgetResizable(True)
        scroll_content_widget = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content_widget)
        edge_spacer_flag = True
        # Создание виджетов в grBox. Добавляем виджеты в scroll_content_layout
        for name, widget in widgets.items():
            if isinstance(widget, QSpacerItem):
                spacer: QSpacerItem = widget # type: ignore
                scroll_content_layout.addItem(spacer)
                edge_spacer_flag = False
            elif widget is not None:
                scroll_content_layout.addWidget(_grBox_wrapper(widget, name=name)) # type: ignore
                
        if edge_spacer_flag:
            scroll_content_layout.addItem(spacer_v_scroll)
        return scroll_content_widget

    tab_widget: QTabWidget = QTabWidget()
    tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    # Настройка шрифта для вкладок
    tab_font = QFont()
    tab_font.setFamily("Arial")
    tab_font.setPointSize(12)
    tab_widget.setFont(tab_font)
    # Используем фабрику для добавления вкладок
    factories = _tab_factories(widget_model)
    for tab_name, factory in factories.items():
        tab_widget.addTab(factory(widget_model[tab_name]), tab_name)
        if tab_widget_handler:
            # добавляем обработчик нажатия вкладок
            if tab_widget_handler:
                tab_widget.currentChanged.connect(tab_widget_handler)
    return tab_widget