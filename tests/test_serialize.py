import pickle

import numpy as np
import pytest

from qurpc.serialize import *


def test_serialize():
    buff = pack((123, 456))
    assert isinstance(buff, bytes)
    assert unpack(buff) == [123, 456]
    x = np.linspace(0, 1, 101)
    buff = pack(x)
    assert isinstance(buff, bytes)
    assert np.all(x == unpack(buff))

    try:
        1 / 0
    except Exception as e:
        buff = pack(e)
        assert isinstance(buff, bytes)
        assert isinstance(unpack(buff), ZeroDivisionError)


class A:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y


def test_error():
    with pytest.raises(TypeError):
        pack(A(3, 5))
    buff = b'\xc75\x03\x80\x03ctest_serialize\nA\nq\x00)\x81q\x01}q\x02(X\x01\x00\x00\x00xq\x03K\x03X\x01\x00\x00\x00yq\x04K\x05ub.'
    ext = unpack(buff)
    assert ext.code == 3
    assert pickle.loads(ext.data) == A(3, 5)


def test_register():
    register(A, pickle.dumps, pickle.loads)
    print(pack(A(3, 5)))
    assert A(3, 5) == unpack(pack(A(3, 5)))


def test_compress():
    x = '123abc' * 1000
    buff = pack(x)
    cbuff = packz(x)
    assert len(buff) > len(cbuff)
    assert np.all(x == unpackz(cbuff))
