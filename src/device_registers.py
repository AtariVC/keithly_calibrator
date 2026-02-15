from dataclasses import dataclass, field
from enum import IntEnum


class MPP_REG(IntEnum):
    CMD_REG = 0x0000
    TMP_COUNT = 0x0006
    ACQ1_PEAK = 0x0007
    ACQ2_PEAK = 0x0008
    DDIIN_PEAK = 0x0009
    BIN_NUM = 0x000A
    HH = 0x000B
    HIST_32 = 0x002C
    HIST_16 = 0x0038
    HIST_HCP = 0x003E
    LEVEL = 0x0079

    CALIBR_ALL_CH = 0x0050
    OSCILL_CH0 = 0xA000
    OSCILL_CH1 = 0xA200


class MPP_CMD_REG(IntEnum):
    SET_LEVEL = 0x0001
    SET_HH = 0x0008
    WAVEFORM_RELEASE = 0x0009
    FILTER_BYPASS = 0x000A
    TRIG_COUNT_CLEAR = 0x000B
    START_MEASURE_FORCED = 0x0051


@dataclass(frozen=True)
class MPP_CMD_Payload:
    START_MEASURE: list[int] = field(default_factory=lambda: [0x0002, 0x0001])
    STOP_MEASURE: list[int] = field(default_factory=lambda: [0x0002, 0x0000])


class MB_F_CODE(IntEnum):
    F16 = 0x10
    F03 = 0x03
    F06 = 0x06


@dataclass(frozen=True)
class DeviceProtocol:
    MPP_ID_DEFAULT: int = 14
    CM_ID: int = 1
    DDII_SWITCH_MODE: int = 0x0001
    SILENT_MODE: int = 0x0000
    COMBAT_MODE: int = 0x0001
