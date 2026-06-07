from enum import Enum


class RecordingState(Enum):

    IDLE = "idle"

    RECORDING = "recording"

    PROCESSING = "processing"

    COMPLETE = "complete"

    ERROR = "error"