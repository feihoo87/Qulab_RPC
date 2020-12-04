import pickle

import pytest

from qurpc.bencoder import decode, encode, Bencached

msg = {
    'w': {
        'a': -1,
        'b': 2,
        'c': {
            'p': b'world',
            'q': 0
        }
    },
    'x': 1,
    'y': [1, 2, 3],
    'z': b'hello'
}


def test_encode():
    assert encode(2283) == b'i2283e'
    assert encode("hello") == b'5:hello'
    assert encode(b"hello") == b'5:hello'
    assert encode([1, 2, 'xyz', True, False]) == b'li1ei2e3:xyzi1ei0ee'

    assert encode(
        msg
    ) == b'd1:wd1:ai-1e1:bi2e1:cd1:p5:world1:qi0eee1:xi1e1:yli1ei2ei3ee1:z5:helloe'


def test_decode():
    assert decode(b'i2283e') == 2283
    assert decode('i2283e') == 2283
    assert decode(b'5:hello') == b"hello"
    assert decode(b'0:') == b""
    assert decode(b'li1ei2e3:xyzi1ei0ee') == [1, 2, b'xyz', 1, 0]
    assert pickle.dumps(
        decode(
            b'd1:wd1:ai-1e1:bi2e1:cd1:p5:world1:qi0eee1:xi1e1:yli1ei2ei3ee1:z5:helloe'
        )) == pickle.dumps(msg)


def test_Bencached():
    assert encode(Bencached(b"xyz")) == b"xyz"


def test_error():
    with pytest.raises(ValueError):
        decode(b'6:hello')

    with pytest.raises(ValueError):
        decode(b'x122e')

    with pytest.raises(ValueError):
        decode(b'0 :')

    with pytest.raises(ValueError):
        decode(b'i-0e')

    with pytest.raises(ValueError):
        decode(b'i0123e')
