from fastapi import FastAPI
from contextlib import asynccontextmanager
from containerManager import containerManager

day = 60 * 60 * 24

global cm
cm = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cm
    # startup code
    cm = containerManager(2 * day)
    yield
    # shutdown code
    cm.stopAllContainers()


app = FastAPI(lifespan=lifespan)

@app.get("/container_for_user/{user_id}")
async def get_container_for_user(user_id: str):
    global cm
    print(f"Requesting container for user_id: {user_id}")
    id = await cm.getContainer(user_id)
    return {"id": id}
