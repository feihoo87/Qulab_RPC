# Qulab_RPC
[![View build status](https://travis-ci.org/feihoo87/Qulab_RPC.svg?branch=master)](https://travis-ci.org/feihoo87/Qulab_RPC)
[![Coverage Status](https://coveralls.io/repos/github/feihoo87/Qulab_RPC/badge.svg?branch=master)](https://coveralls.io/github/feihoo87/Qulab_RPC?branch=master)
[![Updates](https://pyup.io/repos/github/feihoo87/Qulab_RPC/shield.svg)](https://pyup.io/repos/github/feihoo87/Qulab_RPC/)
[![Python 3](https://pyup.io/repos/github/feihoo87/Qulab_RPC/python-3-shield.svg)](https://pyup.io/repos/github/feihoo87/Qulab_RPC/)
[![PyPI version](https://badge.fury.io/py/QuLab-RPC.svg)](https://badge.fury.io/py/QuLab-RPC)

RPC for Qulab

## Installation
We encourage installing QuLab-RPC via the pip tool (a python package manager):
```bash
python -m pip install QuLab-RPC
```

To install from the latest source, you need to clone the GitHub repository on your machine.
```bash
git clone https://github.com/feihoo87/QuLab_RPC.git
```

Then dependencies and QuLab can be installed in this way:
```bash
cd QuLab_RPC
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Usage

Server

```python
import asyncio
import math


def start(loop):
    module = math
    server = ZMQServer(port=8765, loop=loop)
    server.set_module(module)
    server.start()

if __name__ == "__main__":
    import asyncio

    loop = asyncio.get_event_loop()

    start(loop)

    try:
        loop.run_forever()
    finally:
        loop.close()
```

Client
```python
client = ZMQClient(addr)

y = await client.sin(3.14)
```


## Running Tests
To run tests:

```
python -m pytest
```

## Reporting Issues
Please report all issues [on github](https://github.com/feihoo87/QuLab_RPC/issues).

## License

[MIT](https://opensource.org/licenses/MIT)
