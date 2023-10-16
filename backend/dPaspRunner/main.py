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


class CodeInput(BaseModel):
    code: str


@app.post("/run")
def run_code(code_input: CodeInput):
    code = code_input.code

    out = ListStream()
    try:
        P = pasp.parse(code, from_str=True)
        print(pasp.exact(P), file=out)
    except Exception as e:
        print(e, file=out)

    result = out.flush()

    return {"result": result}
