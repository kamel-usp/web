import os
from fastapi import FastAPI, UploadFile
from pydantic import BaseModel
import pasp

app = FastAPI()

class ListStream:
    def __init__(self):
        self.data = []

    def write(self, s):
        self.data.append(s)

    def flush(self):
        str1 = "".join(self.data)
        return str1


class RunRequest(BaseModel):
    sem: str = "stable"
    psem: str = "credal"
    code: str


@app.post("/run")
async def run_code(run_req: RunRequest):
    sem = run_req.sem
    psem = run_req.psem
    code = run_req.code

    out = ListStream()
    try:
        P = pasp.parse(code, from_str=True, semantics=sem)
        print(pasp.exact(P, psemantics=psem), file=out)
    except Exception as e:
        print(e, file=out)

    result = out.flush()

    return {"result": result}


blob_folder = "~/blobs/"

@app.post("/blob_upload")
async def upload_blob(src: UploadFile):
    chunk_size = 512
    with open(f"{blob_folder}{src.filename}", "wb") as dest:
        for chunk in iter(lambda: await src.read(chunk_size), b''):
            dest.write(chunk)
    return {"status": "ok"}

@app.post("/blob_list")
async def list_blobs():
    return {"files" : os.listdir(blob_folder)}

@app.post("/blob_delete")
async def delete_blob(filename: str):
    if os.remove(f"{blob_folder}{filename}"):
        return {"status": "ok"}
    else:
        return {"status": "There is no file with this filename"}





