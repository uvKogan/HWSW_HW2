"""
Compute-only FaaS function: project_medals.

Unlike every other function here it does NOT go through the state runtime --
it reads nothing and writes nothing, so it skips the sqlite load/save
entirely. That is the point: an independent, side-effect-free CPU task is the
clean embarrassingly-parallel case, and letting each invocation run in its
own process is exactly where FaaS beats the single GIL-bound monolith. See
bench/parallel_throughput.py.
"""

import json
import sys

from common.operations import project_medals

if __name__ == "__main__":
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.loads(sys.stdin.read() or "{}")
    json.dump(project_medals({}, params), sys.stdout)
