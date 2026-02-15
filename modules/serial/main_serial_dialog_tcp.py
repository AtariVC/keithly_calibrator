import asyncio
import sys
from pathlib import Path

import qasync
import qtmodern.styles
from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.pdu import ModbusResponse
from pymodbus.server import StartAsyncTcpServer
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

from .customComboBox_COMport import CustomComboBox_COMport  # noqa: E402

from custom.widgets import widget_led_off, widget_led_on  # noqa: E402
from device_registers import MPP_CMD_REG, MPP_REG, MPP_CMD_Payload  # noqa: E402
from src.cmd_interface import MPP_Commands  # noqa: E402
from src.log_config import log_init, log_s  # noqa: E402
from src.modbus_worker import ModbusWorker  # noqa: E402

BAUDRATE = 125000


class ModbusRelayServer:
    """Сервер для ретрансляции Modbus данных"""

    def __init__(self, serial_client, host="0.0.0.0", port=5012):
        self.serial_client = serial_client
        self.host = host
        self.port = port
        self.server = None
        self.context = None
        self._setup_datastore()

    def _setup_datastore(self):
        """Настройка хранилища данных Modbus"""
        store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            hr=ModbusSequentialDataBlock(0, [0] * 100),
            ir=ModbusSequentialDataBlock(0, [0] * 100),
        )
        self.context = ModbusServerContext(slaves=store, single=True)

    async def start_server(self):
        """Запуск TCP сервера"""
        try:
            self.server = await StartAsyncTcpServer(
                context=self.context, address=(self.host, self.port), defer_start=False
            )
            print(f"Modbus TCP сервер запущен на {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Ошибка запуска сервера: {e}")
            return False

    def stop_server(self):
        """Остановка TCP сервера"""
        if self.server:
            self.server.server_close()
            print("Modbus TCP сервер остановлен")


class SerialConnect(QtWidgets.QWidget):
    tabWidget_serial: QtWidgets.QTabWidget
    # serial
    pushButton_connect_w: QtWidgets.QPushButton
    checkBox_mpp_only: QtWidgets.QCheckBox
    lineEdit_ID_w: QtWidgets.QLineEdit
    widget_led_w: QtWidgets.QWidget
    label_state_w: QtWidgets.QLabel
    horizontalLayout_comport: QtWidgets.QHBoxLayout
    # tcp
    lineEdit_ip: QtWidgets.QLineEdit
    lineEdit_tcp_port: QtWidgets.QLineEdit
    pushButton_connect_tcp: QtWidgets.QPushButton
    widget_led_tcp: QtWidgets.QWidget
    label_tcp: QtWidgets.QLabel

    coroutine_finished = QtCore.pyqtSignal()
    tcp_status_changed = QtCore.pyqtSignal(str, bool)
    disconnected = QtCore.pyqtSignal()

    def __init__(self, logger, **kwargs) -> None:
        super().__init__(**kwargs)
        loadUi(Path(__file__).parents[0].joinpath("DialogSerialTCP.ui"), self)
        self.mw = ModbusWorker()
        self.logger = logger
        self.comboBox_comm = CustomComboBox_COMport()
        self.horizontalLayout_comport.addWidget(self.comboBox_comm)
        self.size_policy: QSizePolicy = self.comboBox_comm.sizePolicy()
        # Признак подключения Serial определяется по self.client
        self.size_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        self.comboBox_comm.setSizePolicy(self.size_policy)
        self.mpp_id: int = 14
        self.status_CM = 1
        self.status_MPP = 1
        self.client: AsyncModbusSerialClient | None = None
        self.tcp_client: AsyncModbusTcpClient | None = None
        self.relay_server: ModbusRelayServer | None = None
        # Признаки TCP клиента/сервера определяются по self.tcp_client/self.relay_server

        # Подключаем обработчики
        self.pushButton_connect_w.clicked.connect(self.pushButton_connect_Handler)
        self.pushButton_connect_tcp.clicked.connect(self.tcp_button_handler)
        self.tcp_status_changed.connect(self.update_tcp_status)

        # Обновляем интерфейс при смене вкладок
        self.tabWidget_serial.currentChanged.connect(self.update_tcp_interface)

        # Нулевой клиент для безопасных команд при отсутствии связи
        class _NullModbusClient(AsyncModbusSerialClient):
            def __init__(self):
                pass

            async def read_holding_registers(self, *args, **kwargs):
                raise RuntimeError("No Modbus client connected")

            async def write_registers(self, *args, **kwargs):
                raise RuntimeError("No Modbus client connected")

            async def connect(self, *args, **kwargs):
                return False

            def close(self):
                return None

        self._null_client = _NullModbusClient()

    def update_tcp_interface(self, index):
        """Обновление интерфейса TCP в зависимости от состояния serial"""
        if index == 1:  # Вкладка TCP
            if self.client is not None:  # Есть serial подключение
                self.pushButton_connect_tcp.setText(
                    "Запустить" if self.relay_server is None else "Остановить"
                )
                self.label_tcp.setText("Состояние сервера:")
            else:  # Нет serial подключения
                self.pushButton_connect_tcp.setText(
                    "Подключить" if self.tcp_client is None else "Отключить"
                )
                self.label_tcp.setText("Состояние подключения:")

    @qasync.asyncSlot()
    async def tcp_button_handler(self):
        """Обработчик кнопки TCP"""
        if self.client is not None:  # Есть serial подключение - управляем сервером
            await self.tcp_server_handler()
        else:  # Нет serial подключения - подключаемся как клиент
            await self.tcp_client_handler()

    async def tcp_server_handler(self):
        """Обработчик для режима сервера"""
        if self.relay_server is not None:
            self.stop_tcp_server()
        else:
            await self.start_tcp_server()

    async def tcp_client_handler(self):
        """Обработчик для режима клиента"""
        if self.tcp_client is not None:
            self.disconnect_tcp_client()
        else:
            await self.connect_tcp_client()

    async def start_tcp_server(self):
        """Запуск TCP сервера"""
        host = self.lineEdit_ip.text()
        port = int(self.lineEdit_tcp_port.text())

        # Создаем сервер и сохраняем только при успешном запуске
        relay_server = ModbusRelayServer(self.client, host, port)

        if await relay_server.start_server():
            self.relay_server = relay_server
            self.tcp_status_changed.emit(f"Сервер запущен на {host}:{port}", True)
            self.logger.info(f"TCP сервер запущен на {host}:{port}")
        else:
            self.tcp_status_changed.emit("Ошибка запуска сервера", False)

    def stop_tcp_server(self):
        """Остановка TCP сервера"""
        if self.relay_server:
            self.relay_server.stop_server()
            self.relay_server = None
            self.tcp_status_changed.emit("Сервер остановлен", False)
            self.logger.info("TCP сервер остановлен")

    async def connect_tcp_client(self):
        """Подключение как TCP клиент"""
        host = self.lineEdit_ip.text()
        port = int(self.lineEdit_tcp_port.text())

        try:
            tcp_client = AsyncModbusTcpClient(host=host, port=port, timeout=2)
            connected = await tcp_client.connect()
            if connected:
                self.tcp_client = tcp_client
                self.tcp_status_changed.emit(f"Подключено к {host}:{port}", True)
                self.logger.info(f"Подключено к TCP серверу {host}:{port}")
            else:
                # Закрываем созданный клиент, если не удалось подключиться
                try:
                    tcp_client.close()
                except Exception:
                    pass
                self.tcp_status_changed.emit("Не удалось подключиться", False)

        except Exception as e:
            self.tcp_status_changed.emit(f"Ошибка подключения: {e}", False)
            self.logger.error(f"Ошибка TCP подключения: {e}")

    def disconnect_tcp_client(self):
        """Отключение TCP клиента"""
        if self.tcp_client:
            self.tcp_client.close()
            self.tcp_client = None
            self.tcp_status_changed.emit("Отключено", False)
            self.logger.info("TCP подключение закрыто")

    def disconnect_serial_client(self):
        """Отключение Serial клиента"""
        # Останавливаем TCP сервер при отключении
        if self.relay_server is not None:
            self.stop_tcp_server()

        # Закрываем TCP клиент если был подключен
        if self.tcp_client is not None:
            self.disconnect_tcp_client()
            self.logger.info("TCP подключение закрыто")
            self.tcp_status_changed.emit("Отключено", False)
            self.disconnected.emit()

        if self.client:
            self.client.close()
            self.client = None
            self.label_state_w.setText("State: Отключено")
            self.pushButton_connect_w.setText("Подключить")

    def update_tcp_status(self, message, is_connected):
        """Обновление статуса TCP"""
        if self.client is not None:  # Режим сервера
            self.label_tcp.setText(f"Состояние сервера: {message}")
        else:  # Режим клиента
            self.label_tcp.setText(f"Состояние подключения: {message}")

        self.widget_led_tcp.setStyleSheet(
            widget_led_on() if is_connected else widget_led_off()
        )

        # Обновляем текст кнопки
        if self.client is not None:
            self.pushButton_connect_tcp.setText(
                "Остановить" if is_connected else "Запустить"
            )
        else:
            self.pushButton_connect_tcp.setText(
                "Отключить" if is_connected else "Подключить"
            )

    @qasync.asyncSlot()
    async def pushButton_connect_Handler(self) -> None:
        await self.serialConnect()
        if self.client is not None:
            # Обновляем интерфейс TCP при изменении состояния serial
            self.update_tcp_interface(self.tabWidget_serial.currentIndex())
            self.coroutine_finished.emit()

    @qasync.asyncSlot()
    async def serialConnect(self) -> None:
        self.mpp_id = int(self.lineEdit_ID_w.text())

        if self.client is None:
            port = self.comboBox_comm.currentText()
            self.client = AsyncModbusSerialClient(
                port,
                timeout=1,
                baudrate=BAUDRATE,
                bytesize=8,
                parity="N",
                stopbits=1,
                handle_local_echo=True,
            )

            connected: bool = await self.client.connect()
            if connected:
                self.logger.debug(
                    f"{port}, Baudrate={BAUDRATE}, Parity=None, Stopbits=1, Bytesize=8"
                )
                self.pushButton_connect_w.setText("Отключить")
                await self._check_connect()
            else:
                self.label_state_w.setText(
                    "State: COM-порт занят. Попробуйте переподключиться"
                )
        else:
            self.pushButton_connect_w.setText("Подключить")
            self.widget_led_w.setStyleSheet(widget_led_off())
            self.label_state_w.setText("State:")
            if self.client:
                self.client.close()
                self.client = None
            else:
                ...
            self.disconnected.emit()

    @qasync.asyncSlot()
    async def _check_connect(self) -> None:
        self.status_MPP = 1

        ######## MPP #######
        try:
            if self.client:
                response: ModbusResponse = await self.client.read_holding_registers(
                    0x0000, 4, slave=self.mpp_id
                )
                await log_s(self.mw.send_handler.mess)
                if response:
                    self.status_MPP = 1
                    self.widget_led_w.setStyleSheet(widget_led_on())
                else:
                    self.status_MPP = 0
                    self.widget_led_w.setStyleSheet(widget_led_off())
        except Exception as e:
            self.pushButton_connect_w.setText("Подключить")
            self.label_state_w.setText(f"State: Нет подключения к ID{self.mpp_id}")
            self.status_MPP = 0
            self.logger.debug(f"Соединение c ID{self.mpp_id} не установлено")
            self.logger.error(str(e))
            self.client.close()
            await asyncio.sleep(0.1)
            self.client = None
            self.disconnected.emit()

        #### CM ####
        if self.checkBox_mpp_only.isChecked() is False:
            try:
                if self.client:
                    await self.client.write_registers(
                        address=self.DDII_SWITCH_MODE,
                        values=self.SILENT_MODE,
                        slave=self.CM_ID,
                    )
                    await log_s(self.mw.send_handler.mess)
            except Exception as e:
                self.logger.debug("Соединение c ЦМ не установлено")
                self.logger.error(str(e))

    # ===== Проверки состояния подключения по Serial =====
    def is_modbus_ready(self) -> bool:
        return self.client is not None

    def get_commands_interface(self, logger) -> tuple[MPP_Commands]:
        """Возвращает новые объекты команд с актуальным клиентом и MPP_ID.
        Если соединения нет, возвращает команды с null‑клиентом.
        """
        cli = self.client if self.client is not None else self._null_client
        try:
            mpp = MPP_Commands(cli, logger, self.mpp_id)
        except Exception:
            mpp = MPP_Commands(cli, logger)
        return mpp

    async def check_connection(self, only_cm=True, only_mpp=True) -> bool:
        """
        Проверка подключения CM и MPP по Serial. Для внешнего использования.

        - Проверяет наличие клиента; при его отсутствии возвращает False.
        - Обновляет статусы устройств через `check_connect()`.
        - Если активен `checkBox_mpp_only`, то для готовности устройств достаточно
        доступности МПП; ЦМ игнорируется. Иначе требуются ЦМ и МПП.

        Returns:
            bool: True, если условия подключения выполнены, иначе False.
        """
        if not self.is_modbus_ready():
            self.logger.debug("Modbus клиент не подключен")
            return False
        await self._check_connect()
        if self.status_CM and self.status_MPP:
            return True  # Оба устройства подключены
        elif self.status_MPP and self.checkBox_mpp_only.isChecked():
            return True  # Только МПП подключен, ЦМ игнорируется
        elif self.status_CM and not only_mpp:
            return True  # Только ЦМ требуется и он подключен
        elif self.status_MPP and not only_cm:
            return True  # Только МПП требуется и он подключен
        else:
            self.logger.error("Подключение потеряно")
            return False  # Устройства не готовы


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    qtmodern.styles.dark(app)
    logger = log_init()
    w: SerialConnect = SerialConnect(logger)

    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    w.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
    w.show()

    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
        except asyncio.CancelledError:
            ...
