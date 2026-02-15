#!/usr/bin/env python3
"""
Простой relay-сервер для проброса Modbus TCP <-> Serial (ДДИИ)
"""

import argparse
import asyncio
import logging

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
from pymodbus.pdu import ModbusRequest
from pymodbus.server import StartAsyncTcpServer
from pymodbus.transaction import ModbusRtuFramer


class SerialProxyDataStore(ModbusSlaveContext):
    """Простой прокси для перенаправления TCP-запросов в Serial."""

    def __init__(self, serial_client: AsyncModbusSerialClient):
        super().__init__()
        self.serial_client = serial_client

    async def execute(self, request: ModbusRequest):
        try:
            unit = request.unit_id or 1
            pdu = request.encode()
            response = await self.serial_client.protocol.execute(pdu, unit)
            return response
        except Exception as e:
            logging.error(f"Ошибка обработки запроса: {e}")
            return request.doException(1)


async def main():
    parser = argparse.ArgumentParser(description="Relay Modbus TCP->Serial (ДДИИ)")
    parser.add_argument("--port", required=True, help="Serial порт, напр. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--tcp-port", type=int, default=502)
    parser.add_argument("--tcp-host", default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

    serial_client = AsyncModbusSerialClient(
        method="rtu",
        port=args.port,
        baudrate=args.baud,
        timeout=1,
        bytesize=8,
        parity="N",
        stopbits=1,
        framer=ModbusRtuFramer,
    )
    ok = await serial_client.connect()
    if not ok:
        logging.error("Не удалось подключиться к Serial-порту.")
        return
    logging.info(f"✅ Serial подключено: {args.port} ({args.baud} бод)")
