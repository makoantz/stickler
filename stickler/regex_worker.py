"""Child process for bounded regex evaluation. Standard library only; run with -I.

stdin:  {"patterns": [[key, pattern], ...], "texts": [text, ...]}
stdout: {"hits": [[key, text_index], ...]}
"""

import json
import re
import sys

request = json.load(sys.stdin)
compiled = [(key, re.compile(pattern)) for key, pattern in request["patterns"]]
hits = [[key, i] for i, text in enumerate(request["texts"]) for key, rx in compiled if rx.search(text)]
json.dump({"hits": hits}, sys.stdout)
