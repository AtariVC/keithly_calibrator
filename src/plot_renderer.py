import asyncio
import datetime
import os
import sys
from pathlib import Path
from typing import Optional, Sequence, Callable, Union

import numpy as np
import pyqtgraph as pg
import qasync
import qtmodern
from PyQt6 import QtCore, QtWidgets

# from src.write_data_to_file import write_to_hdf5_file

####### импорты из других директорий ######
# /src
src_path = Path(__file__).resolve().parent.parent.parent.parent

# from src.signal_manager import SignalManager  # noqa: E402

sys.path.append(str(src_path))

class GraphPen():
    '''Отрисовщик графиков

    Добавляет в layout окно графика и отрисовывет график
    '''
    def __init__(self,
        layout: QtWidgets.QHBoxLayout | QtWidgets.QVBoxLayout | QtWidgets.QGridLayout,
        name: str = "default_graph",
        color: tuple = (255, 120, 10)) -> None:

        self.plt_widget = pg.PlotWidget()
        layout.addWidget(self.plt_widget)
        self.pen = pg.mkPen(color)
        self.name_frame: str = name
        self.plot_item = None # для PlotDataItem
        

    @qasync.asyncSlot()
    async def draw_graph(self, data: list, name_file_save_data: Optional[str] = None, name_data: Optional[str] = None, path_to_save: Optional[Path] = None, save_log=False, clear=False) -> tuple:
        if save_log and path_to_save:
            self.path_to_save: Path = path_to_save
        try:
            if any(isinstance(item, float) for item in data):
                data = list(map(int, data))
                # print(f"Данные преобразованы в int")
            x, y = await self._prepare_graph_data(data)
            if clear:
                self.plt_widget.clear()
                self.plot_item = None
            if save_log:
                # self._save_graph_data(x, y, name_file_save_data, name_data)
                pass
            if self.plot_item == None:
                self.plot_item = pg.PlotDataItem(x, y, pen = self.pen)
                self.plt_widget.addItem(self.plot_item)
            else:
                self.plot_item.setData(self.plot_item)
            # self.plt_widget.plot(x, y, pen=self.pen)
            return x, y
        except Exception as e:
            print(f"Ошибка отрисовки: {e}")
            return [],[]

    async def _prepare_graph_data(self, data):
        """Подготовка данных для графика"""
        x, y = [], []
        for index, value in enumerate(data):
            x.append(index)
            # y.append(0 if value&0xFFF > 4000 else value&0xFFF)
            y.append(value&0xFFF)
            # self.delete_big_bytes(value)
            # y.append(value)
        return x, y

    # def _save_graph_data(self, x: list, y: list, filename, name_data):
    #     """Сохранение данных графика"""
    #     write_to_hdf5_file([x, y], self.name_frame, self.path_to_save, name_file_hdf5=filename, name_data=name_data)

class HistPen():
    def __init__(self,
                layout: QtWidgets.QHBoxLayout|QtWidgets.QVBoxLayout|QtWidgets.QGridLayout,
                name: str,
                color: tuple = (0, 0, 255, 150)) -> None:
        self.hist_widget: pg.PlotWidget = pg.PlotWidget()
        layout.addWidget(self.hist_widget)
        self.color = color
        self.pen = pg.mkPen(color)
        # белый контур
        self.outline_pen = pg.mkPen((255, 255, 255), width=2)
        self.name_frame: str = name
        self.hist_item = None
        self.hist_outline_item = None  # для белого контура
        
        # Настройки гистограммы
        self.accumulate_data: list = []
        ###
        # self.bin_count = 100  # начальное количество бинов
        self.padding_factor = 0.1  # отступ по краям (10% от диапазона данных)
        ###
        self.bin_count = 4096
        self.x_range = (0, self.bin_count)
        self.bins = np.linspace(*self.x_range, self.bin_count)
        
        #### Path ####
        # self.parent_path: Path = Path("./log/graph_data").resolve()
        # current_datetime = datetime.datetime.now()
        # time: str = current_datetime.strftime("%d-%m-%Y_%H")[:23]
        # self.path_to_save: Path = self.parent_path / time

    def hist_clear(self):
        self.accumulate_data.clear()
        self.hist_widget.clear()
        self.hist_item = None
        self.hist_outline_item = None

    def _calculate_bins(self, data):
        """Вычисляет оптимальные бины и диапазон для данных"""
        if not data or len(data) < 2:
            return np.linspace(0, 1, 10), (0, 1)  # значения по умолчанию

        min_val = min(data)
        max_val = max(data)

        # Добавляем отступ по краям (10% от диапазона данных)
        padding = (max_val - min_val) * self.padding_factor
        if padding == 0:  # если все значения одинаковые
            padding = 1

        x_min = min_val - padding
        x_max = max_val + padding

        # Правило Фридмана-Диакониса для определения количества бинов
        q1 = np.percentile(data, 25)
        q3 = np.percentile(data, 75)
        iqr = q3 - q1
        if iqr > 0:  # защита от деления на ноль
            bin_width = 2 * iqr / (len(data) ** (1/3))
            self.bin_count = max(5, min(100, int((x_max - x_min) / bin_width)))
        else:
            # Если IQR = 0, используем правило Стёрджеса
            self.bin_count = min(50, max(5, int(1 + 3.322 * np.log10(len(data)))))

        bins = np.linspace(x_min, x_max, self.bin_count)
        return bins, (x_min, x_max)

    @qasync.asyncSlot()
    async def _draw_graph(self, data: list[int | float],
                    name_file_save_data: Optional[str] = None, name_data: Optional[str] = None,
                    save_log: Optional[bool] = False,
                    clear: Optional[bool] = False,
                    bins: Optional[list | np.ndarray] = None,
                    calculate_hist: Optional[bool] = True,
                    autoscale: Optional[bool] = True) -> None:
        if clear:
            self.hist_clear()
        if not data:
            return
        if bins is None:
            bins = self.bins
        
        if calculate_hist:
            y, x = np.histogram(data, bins)
        else:
            y, x = data, bins
        
        # Фильтрация выбросов и установка разумного диапазона X
        if autoscale:
            if len(y) > 0:
                non_zero_indices = np.where(np.array(y) > 0)[0]
                
                if len(non_zero_indices) > 0:
                    # Берем 1-й и 99-й перцентили для отсечения выбросов
                    lower_idx = max(0, int(np.percentile(non_zero_indices, 25))     - 1)
                    upper_idx = min(len(x)-1, int(np.percentile (non_zero_indices, 85)) + 1)
                    
                    # Устанавливаем диапазон с небольшим запасом
                    padding = 10
                    x_min = max(0, x[lower_idx] - padding)
                    x_max = x[upper_idx] + padding
                    
                    self.hist_widget.setXRange(x_min, x_max)
            
        # обновляем контур
        if self.hist_outline_item is None:
            self.hist_outline_item = pg.PlotDataItem(x, y, pen=self.outline_pen, stepMode=True,     fillLevel=0)
            self.hist_widget.addItem(self.hist_outline_item)
        else:
            self.hist_outline_item.setData(x, y)
        
        # обновляем основную гистограмму
        if self.hist_item is None:
            self.hist_item = pg.PlotDataItem(x, y, pen=self.pen, stepMode=True, brush=self.color,   fillLevel=0)
            self.hist_widget.addItem(self.hist_item)
        else:
            self.hist_item.setData(x, y)
        
        if save_log:
            self._save_graph_data(self.bins.tolist()[:-1], y.tolist(), name_file_save_data, name_data)

    # def _save_graph_data(self, x: list, y: list, filename, name_data):
    #     """Сохранение данных графика"""
    #     write_to_hdf5_file([x, y], self.name_frame, self.path_to_save, name_file_hdf5=filename, name_data=name_data)

    @qasync.asyncSlot()
    async def draw_hist(self, data: Sequence[Union[int, float]], 
                    name_file_save_data: Optional[str] = None, name_data: Optional[str] = None,
                    filter: Optional[Callable] = None,
                    save_log: Optional[bool] = False,
                    clear: Optional[bool] = False) -> None:
        """
        Отрисовывает гистограмму данных с возможностью фильтрации и сохранения
        Args:
            data: Список числовых значений для построения гистограммы
            filtr: Функция фильтрации данных (если None, используется максимум)
            save_log: Флаг сохранения данных
            name_file_save_data: Имя файла для сохранения
        """
        self.parent_path: Path = Path("./log/output_graph_data").resolve()
        current_datetime = datetime.datetime.now()
        time: str = current_datetime.strftime("%d-%m-%Y")[:23]
        self.path_to_save: Path = self.parent_path / time
        if filter is not None:
            filtered_value = filter(data)
            plot_data = [filtered_value] if filtered_value is not None else []
        else:
            plot_data = [max(data)]
        self.accumulate_data.extend(plot_data)
        await self._draw_graph(self.accumulate_data, name_file_save_data, name_data, save_log)


