from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys

# docker build -t dpasp-runner .
# docker run -p 127.0.0.1:8000:8000 -t dpasp-runner
app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # You can specify the HTTP methods you want to allow
    allow_headers=["*"],  # You can specify the HTTP headers you want to allow
)


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


@app.post("/api")
def run_container(code_input: CodeInput):
    code = code_input.code

    sys.stdout = new_stdout = ListStream()

    exec(code)

    sys.stdout = sys.__stdout__

    result = new_stdout.flush()
    print(result)

    return {"result": result}
