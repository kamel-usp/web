from fastapi import FastAPI
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
def run_code(run_req: RunRequest):
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
