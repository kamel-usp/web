import os
is_mock = os.getenv("MOCK") == "y"

if not is_mock:
    import pasp

def run_program (sem, psem, code):
    if is_mock:
        return "Mock Output"
    else:
        P = pasp.parse(code, from_str=True, semantics=sem)
        return pasp.exact(P, psemantics=psem)