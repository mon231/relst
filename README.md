# Relst package


## Installation

clone the project:
```bash
git clone https://github.com/mon231/relst
```

install as a package:
```bash
pip install ./relst
```

## Usage

server side:
```py
import random
from relst.server import RelstTextualServer


class EchoMethodName:
    def get_random_value(self):
        return random.choice(('m', 1, 5.5, False))

    @staticmethod
    def return_str_function() -> str:
        return 'function'

    @staticmethod
    async def get_length(string: str) -> int:
        return len(string)

    def _will_not_be_exposed():
        return 'MySecretCode'


request_handler = EchoMethodName()
server = RelstTextualServer(SERVER_PORT, request_handler)
server.serve()
```
