from fastapi import (
    FastAPI
)

from fastapi.staticfiles import (
    StaticFiles
)

from pathlib import (
    Path
)

from routers.tts_router import (
    router as tts_router
)

from services.tts_service import (
    tts_service
)


app = FastAPI()


OUTPUT_DIR = Path(
    "outputs"
)

OUTPUT_DIR.mkdir(
    exist_ok=True
)


@app.on_event(
    "startup"
)
def startup():

    tts_service.load_model()


# WAV 파일 외부 공개
app.mount(
    "/outputs",
    StaticFiles(
        directory=str(
            OUTPUT_DIR
        )
    ),
    name="outputs"
)


app.include_router(
    tts_router
)