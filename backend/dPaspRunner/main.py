import os

from fastapi import FastAPI
from pydantic import BaseModel

import dpasp_api

app = FastAPI()

#: Per-user scratch space inside the runner container. Programs are executed
#: with this as the working directory so that an uploaded `data.csv` can be
#: referenced by its bare name from a `#python` block.
BLOB_FOLDER = os.getenv("DPASP_BLOB_FOLDER", "/blobs/")

SEMANTICS = ("stable", "partial", "lstable", "smproblog")
PSEMANTICS = ("credal", "maxent")


class RunRequest(BaseModel):
    sem: str = "stable"
    psem: str = "credal"
    code: str


@app.post("/run")
async def run_code(run_req: RunRequest):
    """Run a dPASP program and return a structured result.

    See `dpasp_api.run_program` for the response shape. Client errors in the
    program are reported in the body with `ok: False` rather than as HTTP
    errors, so that the editor can render them in its output panel.
    """
    sem = run_req.sem if run_req.sem in SEMANTICS else "stable"
    psem = run_req.psem if run_req.psem in PSEMANTICS else "credal"

    os.makedirs(BLOB_FOLDER, exist_ok=True)
    return dpasp_api.run_program(sem, psem, run_req.code, cwd=BLOB_FOLDER)


def blob_path(filename: str) -> str:
    """Resolve a blob name to a path, refusing anything outside the folder.

    Filenames arrive from the browser, so `../` and absolute paths have to be
    rejected rather than trusted.
    """
    root = os.path.realpath(BLOB_FOLDER)
    target = os.path.realpath(os.path.join(root, filename))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("invalid filename")
    return target


class FileToSave(BaseModel):
    filename: str
    content: str


@app.post("/blob/upload")
async def upload_blob(f: FileToSave):
    os.makedirs(BLOB_FOLDER, exist_ok=True)
    try:
        path = blob_path(f.filename)
    except ValueError:
        return {"status": "error", "detail": "invalid filename"}
    with open(path, "w") as dest:
        dest.write(f.content)
    return {"status": "ok"}


@app.post("/blob/list")
async def list_blobs():
    os.makedirs(BLOB_FOLDER, exist_ok=True)
    return {"files": sorted(os.listdir(BLOB_FOLDER))}


class FileToRead(BaseModel):
    filename: str


@app.post("/blob/fetch")
async def fetch_blob(f: FileToRead):
    try:
        path = blob_path(f.filename)
        with open(path, "r") as handle:
            return {"content": handle.read()}
    except (ValueError, OSError) as exc:
        print(f"/blob/fetch: {exc}")
        return {"content": ""}


class FileToDelete(BaseModel):
    filename: str


@app.post("/blob/delete")
async def delete_blob(f: FileToDelete):
    try:
        os.remove(blob_path(f.filename))
        return {"status": "ok"}
    except (ValueError, OSError):
        return {"status": "There is no file with this filename"}
