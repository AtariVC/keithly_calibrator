import logging
import struct

# Создание фильтра для pymodbus
class SendFilter(logging.Filter):
    def filter(self, record):
        # message = record.getMessage()
        return False #'SEND:' in message or 'RECV:' in message
    
# Создание обработчика для pymodbus
class SendHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mess = []

    def emit(self, record):
        message = self.format(record)
        # self.mess.append(message)
        # print(message)
        if 'recv:' in message:
            self.mess.append(message)
        if 'send:' in message:
            self.mess.append(message)

class ModbusWorkerLog():
    # Сигнал для обновления интерфейса
    def __init__(self, **kwargs):
        log = logging.getLogger('pymodbus')
        log.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.addFilter(SendFilter())
        log.addHandler(handler)
        self.send_handler = SendHandler()
        log.addHandler(self.send_handler)


class ModbusWorker(ModbusWorkerLog):
    def __init__(self, **kwargs):
        super().__init__()

    # def _REV8(self, byte_str: bytes) -> int:
    #     reversed_bytes : int = (int(byte_str[0]) << 4) + (int(byte_str[0]) >> 4) & 0XFF
    #     return reversed_bytes
    
    def _REV16(self, byte_str: bytes) -> bytes:
        reversed_bytes: bytes = struct.pack('<H', int(byte_str.hex(), 16))
        return reversed_bytes
    
    def _REV32(self, byte_str: bytes) -> bytes:
        reversed_bytes: bytes = self._REV16(byte_str[2:]) + self._REV16(byte_str[:2])
        return reversed_bytes
    
    def byte_to_float(self, byte_str: bytes) -> float:
        # n0: bytes = self._REV32(byte_str)
        n_i: int = int(byte_str.hex(), 16)
        b : bytes = n_i.to_bytes(4, byteorder='little')
        float_t: float = struct.unpack('!f', b)[0]
        return float_t
    
    def float_to_byte(self, val: float) -> bytes:
        byte_str: bytes = struct.pack('<f', val)
        return byte_str


if __name__ == "__main__":
    mw = ModbusWorker()
    # print(mw.byte_to_float(0x33334341.to_bytes(4, 'big'))) # 12.2
    # print(mw._REV16(0x4143.to_bytes(2)).hex())
    # print(mw._REV8(0x35).to_bytes(1).hex())