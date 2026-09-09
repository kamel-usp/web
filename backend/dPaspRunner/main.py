import os
from itertools import islice

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
    #: When positive, return only the first `max_lines` lines. The editor asks
    #: for a bounded prefix so that opening an uploaded data file does not send
    #: megabytes of CSV through the proxy and into a text editor that cannot
    #: usefully show it. `total_lines` still reports the real length.
    max_lines: int = 0


@app.post("/blob/fetch")
async def fetch_blob(f: FileToRead):
    """Return a file's text, optionally only its first `max_lines` lines.

    Always reports `total_lines`, `shown_lines` and `bytes`, so a caller
    showing a prefix can say how much it is hiding. A truncated `content`
    holds exactly `shown_lines` lines with no trailing newline, so that a
    text editor displaying it does not show a phantom final line.
    """
    try:
        path = blob_path(f.filename)
        size = os.path.getsize(path)

        with open(path, "r") as handle:
            if f.max_lines <= 0:
                content = handle.read()
                return {
                    "content": content,
                    "truncated": False,
                    "total_lines": _line_count(content),
                    "shown_lines": _line_count(content),
                    "bytes": size,
                }

            head = list(islice(handle, f.max_lines))
            # Count the tail without holding it: this file may be far larger
            # than anything worth loading into memory to answer a fetch.
            tail = sum(1 for _ in handle)

        content = "".join(head)
        truncated = tail > 0
        if truncated and content.endswith("\n"):
            content = content[:-1]

        return {
            "content": content,
            "truncated": truncated,
            "total_lines": len(head) + tail,
            "shown_lines": len(head),
            "bytes": size,
        }
    except (ValueError, OSError) as exc:
        # UnicodeDecodeError is a ValueError, so a binary upload lands here
        # rather than raising through the endpoint.
        print(f"/blob/fetch: {exc}")
        return {
            "content": "",
            "truncated": False,
            "total_lines": 0,
            "shown_lines": 0,
            "bytes": 0,
        }


def _line_count(text: str) -> int:
    """Physical lines in `text`, counting as file iteration does.

    A trailing newline ends the last line rather than starting an empty one,
    so "a\\nb\\n" and "a\\nb" are both two lines.
    """
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


class FileToDelete(BaseModel):
    filename: str


@app.post("/blob/delete")
async def delete_blob(f: FileToDelete):
    try:
        os.remove(blob_path(f.filename))
        return {"status": "ok"}
    except (ValueError, OSError):
        return {"status": "There is no file with this filename"}
