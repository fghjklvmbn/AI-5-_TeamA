from enum import Enum

class RecordingState(Enum):
    IDLE = "대기중"
    RECORDING = "녹음중"
    PROCESSING = "처리중"
    COMPLETE = "완료"
    ERROR = "오류"