import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from containerManager import containerManager

day = 60 * 60 * 24

cm = None
warmup = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cm, warmup

    cm = containerManager(2 * day)

    # Warmed up in the background, not here. Uvicorn binds its listening
    # socket only after this startup block returns, so doing the runner image
    # build inline made the API refuse connections for the whole build — the
    # frontend got ECONNREFUSED rather than something it could display.
    warmup = asyncio.create_task(cm.start())

    yield

    if warmup is not None and not warmup.done():
        warmup.cancel()
    cm.stopAllContainers()


app = FastAPI(lifespan=lifespan)

BUILDING_MESSAGE = (
    "The dPASP runner image is still being built. The first build takes "
    "several minutes: it compiles dPASP against clingo and downloads PyTorch. "
    "Watch progress with: docker compose logs -f container-manager"
)


@app.get("/health")
async def health():
    """Readiness, for humans and for the frontend's error messages."""
    if cm is None:
        return {"status": "starting"}
    if cm.startup_error is not None:
        return {"status": "error", "detail": cm.startup_error}
    if not cm.ready:
        return {"status": "building", "detail": BUILDING_MESSAGE}
    return {
        "status": "ready",
        "active_containers": cm.activeContainerCount(),
        "pooled_containers": len(cm.pre_allocated_containers),
    }


@app.get("/container_for_user/{user_id}")
async def get_container_for_user(user_id: str):
    """Hand back the runner container assigned to a user, creating one if needed.

    Answers 503 with a reason while the image is still building, so the
    editor can tell the user what is happening instead of reporting a bare
    connection failure.
    """
    if cm is None or not cm.ready:
        detail = cm.startup_error if cm is not None and cm.startup_error else BUILDING_MESSAGE
        return JSONResponse({"error": detail}, status_code=503)

    print(f"Requesting container for user_id: {user_id}", flush=True)
    try:
        container_id = await cm.getContainer(user_id)
    except Exception as e:
        message = f"Could not allocate a runner container: {type(e).__name__}: {e}"
        print(message, flush=True)
        return JSONResponse({"error": message}, status_code=503)

    return {"id": container_id}
