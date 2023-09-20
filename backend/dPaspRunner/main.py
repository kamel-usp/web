from fastapi import FastAPI
from pydantic import BaseModel
import sys

# docker build -t dpasp-runner .
# docker run -p 127.0.0.1:8000:8000 -t dpasp-runner
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

    sys.stdout = new_stdout = ListStream()
    sys.stderr = new_stdout

    try:
        exec(code)
    except Exception as e:
        print(e)

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    result = new_stdout.flush()
    print(result)

    return {"result": result}
