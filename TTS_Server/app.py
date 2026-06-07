from fastapi import (
    FastAPI
)

from routers.tts_router import (
    router as tts_router
)

from services.tts_service import (
    tts_service
)


app = FastAPI()


@app.on_event(
    "startup"
)
def startup():

    tts_service.load_model()


app.include_router(
    tts_router
)