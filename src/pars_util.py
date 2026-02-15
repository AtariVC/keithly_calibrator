from loguru import logger



def pars_16b(data: bytes) -> list[int]:
    """
    Parser 16 bytes data with big endian
    """
    try:
        data_out = [int.from_bytes(data[i:i+2], byteorder='big') for i in range(0, len(data), 2)]
        return data_out
    except Exception as e:
        logger.error(f'PARS 16b ERROR: {e}')
        return []


def pars_32b(data: bytes) -> list[int]:
    """
    Parser 32 bytes data with big endian
    """
    try:
        data_out = [int.from_bytes(data[i:i+4], byteorder='big') for i in range(0, len(data), 4)]
        return data_out
    except Exception as e:
        logger.error(f'PARS 32b ERROR: {e}')
        return []