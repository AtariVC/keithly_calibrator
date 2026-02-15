import asyncio
import sys
from pathlib import Path

import qasync
import qtmodern.styles
from pymodbus.client import AsyncModbusSerialClient
from pymodbus.pdu import ModbusResponse
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QSizePolicy
from qtmodern.windows import ModernWindow
from qtpy.uic import loadUi

####### импорты из других директорий ######
# /src
src_path = Path(__file__).resolve().parent.parent.parent
modules_path = Path(__file__).resolve().parent.parent
# Добавляем папку src в sys.path
sys.path.append(str(src_path))
sys.path.append(str(modules_path))

from custom.widgets import widget_led_off, widget_led_on  # noqa: E402
from src.customComboBox_COMport import CustomComboBox_COMport  # noqa: E402
from device_registers import EnvironmentVar  # noqa: E402
from src.log_config import log_init, log_s  # noqa: E402
from src.modbus_worker import ModbusWorker  # noqa: E402


class SerialConnect(QtWidgets.QWidget, EnvironmentVar):
    pushButton_connect_w: QtWidgets.QPushButton
    lineEdit_Bauderate_w: QtWidgets.QLineEdit
    lineEdit_ID_w: QtWidgets.QLineEdit
    widget_led_w: QtWidgets.QWidget
    label_state_w: QtWidgets.QLabel
    horizontalLayout_comport: QtWidgets.QHBoxLayout

    coroutine_finished = QtCore.pyqtSignal()  # нужен чтобы нормально передать client, иначе передается None

    def __init__(self, logger, **kwargs) -> None:
        super().__init__(**kwargs)
        loadUi(Path(__file__).parents[0].joinpath("DialogSerial.ui"), self)
        self.mw = ModbusWorker()
        self.logger = logger
        self.comboBox_comm = CustomComboBox_COMport()
        self.horizontalLayout_comport.addWidget(self.comboBox_comm)
        self.size_policy: QSizePolicy = self.comboBox_comm.sizePolicy()
        self.pushButton_connect_flag = 0
        self.size_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        self.comboBox_comm.setSizePolicy(self.size_policy)
        self.mpp_id: int = 14
        self.state_serial: int = 0
        self.serial_task = None
        self.status_CM = 1
        self.status_MPP = 1
        self.client: AsyncModbusSerialClient = None  # type:ignore опасная строчка
        # Сейчас проброс client-а реализовано через сигнал, в будущем нужно добавить систему подписок на корутины
        self.pushButton_connect_w.clicked.connect(self.pushButton_connect_Handler)

    @qasync.asyncSlot()
    async def pushButton_connect_Handler(self) -> None:
        # self.serial_task = asyncio.create_task(self.serialConnect())
        # while not task.done():
        await self.serialConnect()
        if self.pushButton_connect_flag == 1:
            self.coroutine_finished.emit()
            # await asyncio.sleep(0.1)

    @qasync.asyncSlot()
    async def serialConnect(self) -> None:
        """Подключкние к ДДИИ
        Подключение происходит одновременно к ЦМ и МПП.
        Для подключение к МПП нужно задать ID.
        При успешном подключении ЦМ выдаст структуру ddii_mpp_data.

        Parameters:
        self (экземпляр Engine): текущий экземпляр класса Engine.
        id (int): ID MPP.
        baudrate (int): Скорость передачи данных для последовательной связи.
        f_comand (int): команда для записи в Modbus.
        data (int): Команда чтения из Modbus.

        Returns:
        None
        """

        baudrate = int(self.lineEdit_Bauderate_w.text())
        self.mpp_id = int(self.lineEdit_ID_w.text())
        if self.pushButton_connect_flag == 0:
            port = self.comboBox_comm.currentText()
            self.client = AsyncModbusSerialClient(
                port,
                timeout=1,
                baudrate=baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                handle_local_echo=True,
            )
            connected: bool = await self.client.connect()
            if connected:
                self.state_serial = 1
                self.logger.debug(
                    port
                    + " ,Baudrate = "
                    + str(baudrate)
                    + ", Parity = "
                    + "None"
                    + ", Stopbits = "
                    + "1"
                    + ", Bytesize = "
                    + str(self.client.comm_params.bytesize)
                )
            else:
                self.label_state_w.setText("State: COM-порт занят. Попробуйте переподключиться")
                self.state_serial = 0

            if self.state_serial == 1:
                self.pushButton_connect_w.setText("Отключить")
                self.pushButton_connect_flag = 1
                await self.check_connect()
                if self.status_CM and self.status_MPP == 0:
                    self.client.close()
                    await asyncio.sleep(1)
                    self.label_state_w.setText("State: Нет подключения к ДДИИ")
                    self.pushButton_connect_flag = 0
                    self.pushButton_connect_w.setText("Подключить")
        else:
            await log_s(self.mw.send_handler.mess)
            self.pushButton_connect_w.setText("Подключить")
            self.pushButton_connect_flag = 0
            self.widget_led_w.setStyleSheet(widget_led_off())
            self.label_state_w.setText("State:")
            self.client.close()
            # self.label_state_w.setText("State: ")
            # try:
            #     await self.client.write_registers(address = self.DDII_SWITCH_MODE,
            #                                                                 values = self.SILENT_MODE,
            #                                                                 slave = self.CM_ID)
            #     await log_s(self.mw.send_handler.mess)
            #     await asyncio.sleep(0.03)
            # except Exception as e:
            #     self.logger.error(str(e))
            # try:
            #     await self.client.write_registers(address = self.DDII_SWITCH_MODE,
            #                                             values = self.COMBAT_MODE,
            #                                             slave = self.CM_ID)
            #     await log_s(self.mw.send_handler.mess)
            # except Exception as e:
            #     self.logger.error(str(e))
            # await asyncio.sleep(0.3)

    @qasync.asyncSlot()
    async def check_connect(self) -> None:
        """
        Проверка подключения
        """

        self.status_CM = 1
        self.status_MPP = 1

        #### CM ####

        # self.tel_result: ModbusResponse  = self.get_telemetria()
        try:
            await self.client.write_registers(address=self.DDII_SWITCH_MODE, values=self.SILENT_MODE, slave=self.CM_ID)
            await log_s(self.mw.send_handler.mess)
        except Exception as e:
            self.logger.debug("Соединение c ЦМ не установлено")
            self.logger.error(str(e))
            self.status_CM = 0
            await asyncio.sleep(0.2)  # задержка нужна?

        ######## MPP #######
        try:
            response: ModbusResponse = await self.client.read_holding_registers(0x0000, 4, slave=self.mpp_id)
            await log_s(self.mw.send_handler.mess)
        except Exception as e:
            self.status_MPP = 0
            self.logger.debug("Соединение c МПП не установлено")
            self.logger.error(str(e))

        await self.update_label_connect()

    @qasync.asyncSlot()
    async def update_label_connect(self):
        cheak_st_connect = self.status_CM, self.status_MPP
        if cheak_st_connect == (1, 1):
            self.widget_led_w.setStyleSheet(widget_led_on())
            self.label_state_w.setText("State: CM - OK, MPP - OK")
            # self.pars_telemetria(self.tel_result)
        elif cheak_st_connect == (1, 0):
            self.label_state_w.setText("State: CM - OK, MPP - None")
            self.widget_led_w.setStyleSheet(widget_led_on())
            # self.pars_telemetria(self.tel_result)
        elif cheak_st_connect == (0, 1):
            self.label_state_w.setText("State: CM - None, MPP - OK")
        elif cheak_st_connect == (0, 0):
            self.label_state_w.setText("State: CM - None, MPP - None")
            self.widget_led_w.setStyleSheet(widget_led_off())


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    # light(app)
    logger = log_init()
    w: SerialConnect = SerialConnect(logger)
    # Интеграция asyncio с PyQt
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    # w.show()
    # mw: ModernWindow = ModernWindow(w)
    w.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)  # fix flickering on resize window
    w.show()

    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
        except asyncio.CancelledError:
            ...
    # with open("style\Light.css", "r") as f:#QSS not CSS for pyqt5
    #     stylesheet = f.read()
    #     w.setStyleSheet(stylesheet)
    #     f.close()
    # sys.exit(app.exec())
