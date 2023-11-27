import os
import random
is_mock = os.getenv("MOCK") == "y"

if not is_mock:
    import pasp

def run_program (sem, psem, code):
    if is_mock: 
        return [random.random() for i in range(code.count("#query"))]
    else:
        # TODO: return stdout and stderr
        # TODO: pasp.approx.aseo(P, 100, psemantics = ...)

        # program.Q
        # https://github.com/kamel-usp/dpasp/blob/master/pasp/program.py
        P = pasp.parse(code, from_str=True, semantics=sem)
        return pasp.exact(P, psemantics=psem)