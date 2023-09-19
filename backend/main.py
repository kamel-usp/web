from fastapi import FastAPI
from contextlib import asynccontextmanager
from containerManager import containerManager

day = 60 * 60 * 24

cm = containerManager(2 * day)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup code

    yield
    # shutdown code
    cm.stopAllContainers()

app = FastAPI(lifespan=lifespan)

@app.get("/container_for_user/{user_id}")
def get_container_for_user(user_id: int):
    print(f"Requesting container for user_id: {user_id}")
    id = cm.getContainer(user_id)
    return {"id": id}

