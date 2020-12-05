"""
A simple bencoding implementation in pure Python.
Consult help(encode) and help(decode) for more info.
>>> encode(42) == b'i42e'
True
>>> decode(b'i42e')
42
"""


class Bencached():

    __slots__ = ['bencoded']

    def __init__(self, s):
        self.bencoded = s


def encode_bencached(x, r):
    r.append(x.bencoded)


def encode_int(x, r):
    r.append(f"i{x}e".encode())


def encode_bool(x, r):
    if x:
        encode_int(1, r)
    else:
        encode_int(0, r)


def encode_string(x, r):
    if isinstance(x, str):
        x = x.encode()
    r.extend((str(len(x)).encode(), b':', x))


def encode_list(x, r):
    r.append(b'l')
    for i in x:
        encode_func[type(i)](i, r)
    r.append(b'e')


def encode_dict(x, r):
    r.append(b'd')
    for k, v in sorted(x.items()):
        if isinstance(k, str):
            k = k.encode()
        r.extend((str(len(k)).encode(), b':', k))
        encode_func[type(v)](v, r)
    r.append(b'e')


encode_func = {
    Bencached: encode_bencached,
    int: encode_int,
    str: encode_string,
    bytes: encode_string,
    list: encode_list,
    tuple: encode_list,
    dict: encode_dict,
    bool: encode_bool
}


def decode_int(x, ptr):
    ptr += 1
    end = x.index(b'e', ptr)
    if x[ptr] == b'-'[0]:
        if x[ptr + 1] == b'0'[0]:
            raise ValueError
    elif x[ptr] == b'0'[0] and end != ptr + 1:
        raise ValueError
    n = int(x[ptr:end])
    return n, end + 1


def decode_string(x, ptr):
    colon = x.index(b':', ptr)
    n = int(x[ptr:colon])
    if x[ptr] == b'0'[0] and colon != ptr + 1:
        raise ValueError
    colon += 1
    return x[colon:colon + n], colon + n


def decode_list(x, ptr):
    r, ptr = [], ptr + 1
    while x[ptr] != b'e'[0]:
        v, ptr = decode_func[x[ptr]](x, ptr)
        r.append(v)
    return r, ptr + 1


def decode_dict(x, ptr):
    r, ptr = {}, ptr + 1
    while x[ptr] != b'e'[0]:
        k, ptr = decode_string(x, ptr)
        if isinstance(k, bytes):
            k = k.decode()
        r[k], ptr = decode_func[x[ptr]](x, ptr)
    return r, ptr + 1


decode_func = {b'l'[0]: decode_list, b'd'[0]: decode_dict, b'i'[0]: decode_int}

for i in range(10):
    decode_func[f"{i}".encode()[0]] = decode_string


def encode(obj):
    """
    bencodes given object. Given object should be a int,
    bytes, list or dict. If a str is given, it'll be
    encoded as ASCII.
    >>> [encode(i) for i in (-2, 42, b"answer", b"")] \
            == [b'i-2e', b'i42e', b'6:answer', b'0:']
    True
    >>> encode([b'a', 42, [13, 14]]) == b'l1:ai42eli13ei14eee'
    True
    >>> encode({'bar': b'spam', 'foo': 42, 'mess': [1, b'c']}) \
            == b'd3:bar4:spam3:fooi42e4:messli1e1:cee'
    True
    """
    r = []
    try:
        encode_func[type(obj)](obj, r)
    except KeyError:
        raise ValueError(
            "Allowed types: int, bytes, list, dict; not %s", type(obj))
    r = b''.join(r)
    return r


def decode(s):
    """
    Decodes given bencoded bytes object.
    >>> decode(b'i-42e')
    -42
    >>> decode(b'4:utku') == b'utku'
    True
    >>> decode(b'li1eli2eli3eeee')
    [1, [2, [3]]]
    >>> decode(b'd3:bar4:spam3:fooi42ee') == {'bar': b'spam', 'foo': 42}
    True
    """
    if isinstance(s, str):
        s = s.encode()
    try:
        r, l = decode_func[s[0]](s, 0)
    except (IndexError, KeyError, ValueError):
        raise ValueError("not a valid bencoded string")
    if l != len(s):
        raise ValueError("invalid bencoded value (data after valid prefix)")
    return r


__all__ = ['decode', 'encode']
