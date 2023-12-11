import os
import random
is_mock = os.getenv("MOCK") == "y"

if not is_mock:
    import pasp

def run_program (sem, psem, code):
    if is_mock: 
        return [random.random() for i in range(code.count("#query"))]
    else:
        P = pasp.parse(code, from_str=True, semantics=sem)
        ans = pasp.exact(P, psemantics=psem)
        return list(map(lambda v: v.tolist(), ans))