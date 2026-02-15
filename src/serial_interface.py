import serial
from serial.tools import list_ports
from loguru import logger
from serial import Serial
from typing import Optional
from pymodbus.client import ModbusSerialClient
from pymodbus.pdu import ModbusResponse
from src.log_config import log_init, log_s
from src.modbus_worker import ModbusWorker
import logging

def is_connect():
    def decorator(func):
        def _wraper(*args, **kwargs):
            logger = log_init()
            client: Serial|None = args[0]
            if client:
                if client.is_open:
                    try:
                        func(*args, **kwargs)
                    except Exception as e:
                        logger.error(e)
                        ser_close(client)
                else:
                    logger.error(f"Потеряно соединение {client.port}")
            else:
                logger.error(f"Нет подключения")
        return _wraper
    return decorator

def open_serial(hwid: str, baudrate: int) -> Serial|None:
    logger = log_init()
    client = None # type:ignore
    # for port in list_ports.comports():
    #     print(port.hwid)
        # if hwid in port.hwid:
    try:
        client: Serial = serial.Serial(port=hwid, 
                                baudrate=baudrate, 
                                    parity=serial.PARITY_ODD,
                                    # timeout=None,
                                    stopbits=serial.STOPBITS_ONE,
                                    bytesize=serial.EIGHTBITS)
        # print(client.is_open)
        serial_info =f"Baudrate = {client.baudrate}"\
                        + f", Parity = {client.parity}"\
                        + f", Stopbits = {client.stopbits}"\
                        + f", Bytesize = {client.bytesize}"
        logger.debug(f'Connect to {hwid}: {serial_info}')

    except Exception as e:
        logger.error(e)
        # logger.error(f"ERROR PORT CONNECTION {port.device}: {e}")
    if not client:
        logger.error(f"{hwid} NOT IN LIST SERIAL")
    return client


def ser_close(client: Serial|ModbusSerialClient):
    logger = log_init()
    try:
        client.close()
        if isinstance(client, Serial):
            logger.info(f'Close {client.port}')
        if isinstance(client, ModbusSerialClient):
            logger.info(f'Close {client.comm_params.host}')
    except Exception as e:
        logger.error(f"ERROR CLOSE CLIENT: {e}")

def open_serial_mb(hwid: str, id: int, baudrate: int) -> ModbusSerialClient|None:
    """Подключкние к МПП
    Подключение происходит одновременно к ЦМ и МПП.
    Для подключение к МПП нужно задать ID.
    При успешном подключении ЦМ выдаст структуру ddii_mpp_data.

    Parameters:
    self (экземпляр Engine): текущий экземпляр класса Engine.
    id (int): ID MPP.
    baudrate (int): Скорость передачи данных для последовательной связи.

    Returns:
    None
    """
    logger = log_init()
    client = None
    for port in list_ports.comports():
        if hwid in port.hwid:
            try:
                client = ModbusSerialClient(
                    port.device,
                    timeout=1,
                    baudrate=baudrate,
                    bytesize=8,
                    parity="N",
                    stopbits=1,
                    handle_local_echo=True,
                )
                connected: bool = client.connect()
                if connected:
                    serial_info = f"Baudrate = {client.comm_params.baudrate}"\
                                + f", Parity = {client.comm_params.parity}"\
                                + f", Stopbits = {client.comm_params.stopbits}"\
                                + f", Bytesize = {client.comm_params.bytesize}"
                    logger.debug(f'Connect to {client.comm_params.host}: {serial_info}')
                if check_connect(client, id):
                    logger.debug("Соединение c МПП успешно установлено")
                else:
                    logger.debug("Соединение c МПП не установлено")
            except Exception as e:
                logger.error(f"ERROR PORT CONNECTION {port.device}: {e}")
    if not client:
        logger.error(f"{hwid} NOT IN LIST SERIAL")
    return client


def check_connect(client: ModbusSerialClient, id: int) -> bool:
    """
    Проверка подключения
    """
    ######## MPP #######
    logger = log_init()
    mw = ModbusWorker()
    try:
        response: ModbusResponse = client.read_holding_registers(0x0000, 4, slave=id)
        log_s(mw.send_handler.mess)
        return True
    except Exception as e:
        logger.error(str(e))
        return False

