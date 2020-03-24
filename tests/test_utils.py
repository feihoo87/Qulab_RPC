from qurpc.utils import *


def test_randomID():
    assert isinstance(randomID(), bytes)
    assert len(randomID()) == 20

    s = set()

    for i in range(10):
        rid = randomID()
        assert not rid in s
        s.add(rid)


def f(a, d=1):
    pass

def g(*args):
    pass

def h(**kw):
    pass

def test_acceptArg():
    assert acceptArg(f, 'a')
    assert acceptArg(f, 'a', keyword=True)
    assert acceptArg(f, 'a', keyword=False)

    assert acceptArg(f, 'd')
    assert acceptArg(f, 'd', keyword=True)
    assert acceptArg(f, 'd', keyword=False)

    assert not acceptArg(f, 'e')
    assert not acceptArg(f, 'e', keyword=True)
    assert not acceptArg(f, 'e', keyword=False)

    assert not acceptArg(g, 'a')
    assert not acceptArg(g, 'a', keyword=True)
    assert acceptArg(g, 'a', keyword=False)

    assert not acceptArg(g, 'd')
    assert not acceptArg(g, 'd', keyword=True)
    assert acceptArg(g, 'd', keyword=False)

    assert not acceptArg(g, 'e')
    assert not acceptArg(g, 'e', keyword=True)
    assert acceptArg(g, 'e', keyword=False)

    assert acceptArg(h, 'a')
    assert acceptArg(h, 'a', keyword=True)
    assert acceptArg(h, 'a', keyword=False)

    assert acceptArg(h, 'd')
    assert acceptArg(h, 'd', keyword=True)
    assert acceptArg(h, 'd', keyword=False)

    assert acceptArg(h, 'e')
    assert acceptArg(h, 'e', keyword=True)
    assert acceptArg(h, 'e', keyword=False)