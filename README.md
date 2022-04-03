# asyncjson

Asynchronous json library with support of nested awaitable objects in data.

The most important features are supporting async functions and async generators on any level of
data structure, even for dict keys.

Now the library contains async version of `json.dumps` function. This library was made to help
stream the heavy json structures without blocking the event loop.

Be aware, this is alpha version of library.

## Installing

`pip install asyncjson`

## Example

```python
import sys
import asyncio
import random
import string
import asyncjson

async def random_number():
    await asyncio.sleep(random.random())
    return random.randrange(0, 100)

async def random_strings():
    for i in range(random.randint(0, 10)):
        await asyncio.sleep(random.random())
        yield ''.join(random.choice(string.ascii_letters) for _ in range(random.randint(1, 10)))

async def run():
    obj = {
        'dictkey': {
            'list': [1, '2', 3.0],
            'random strings': random_strings(),
            'random number': random_number(),
            random_strings(): "joined random strings in key",
            random_number(): "random number in key"
        },
        'another random number': random_number(),
        'awaitable objects in list': ["sample", random_number(), random_strings(), [], {}],
        'intkey': 123,
        'stringkey': "qwer",
    }
    async for i in await asyncjson.dumpgen(obj):
        sys.stdout.write(i)
        sys.stdout.flush()

loop = asyncio.get_event_loop()
loop.run_until_complete(run())
```

Will give the result which will appear piece by piece because of sleeps added for
demonstration purposes:

```json
{
 "dictkey": {
  "list": [
   1, 
   "2", 
   3.0
  ], 
  "random strings": [
   "IuaNSw"
  ], 
  "random number": 65, 
  "ZuuBZyEMYTtqyOzYoILOZXCgnTYYsu": "joined random strings in key", 
  43: "random number in key"
 }, 
 "another random number": 85, 
 "awaitable objects in list": [
  "sample", 
  16, 
  [
   "wQ", 
   "Jp", 
   "xDfTNZCUv"
  ], 
  [], 
  {}
 ], 
 "intkey": 123, 
 "stringkey": "qwer"
}
```

## To be done

- [ ] Implement async versions of `dump`, `loads`, `load` functions
- [ ] Implement async encoder/decoder on C in order to increase performance
