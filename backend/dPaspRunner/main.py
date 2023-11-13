import os
from fastapi import FastAPI, UploadFile
from pydantic import BaseModel
import dpasp_api

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
        print (dpasp_api.run_program(sem, psem, code), file=out)
    except Exception as e:
        print(e, file=out)

    result = out.flush()

    return {"result": result}


blob_folder = "/blobs/"

class FileToSave(BaseModel):
    filename: str
    content: str

@app.post("/blob/upload")
async def upload_blob(src: FileToSave):
    with open(f"{blob_folder}{src.filename}", "w") as dest:
        dest.write(src.content)
    return {"status": "ok"}

@app.post("/blob/list")
async def list_blobs():
    return {"files" : os.listdir(blob_folder)}

class FileToDelete(BaseModel):
    filename: str
@app.post("/blob/delete")
async def delete_blob(f: FileToDelete):
    try:
        os.remove(f"{blob_folder}{f.filename}")
        return {"status": "ok"}
    except:
        return {"status": "There is no file with this filename"}





