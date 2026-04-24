#!/usr/bin/env python3

import sys
from common import _host_operation, _operation

def run_test(args):
    host_mode = False
    pytest_args = []
    for arg in args[1:]:
        if arg == "--host":
            host_mode = True
            continue
        pytest_args.append(arg)

    pytest_command = [
        "pytest",
        "-s",
        "--cov=files",
        "--cov-report=html",
        "--cov-report=term",
    ] + pytest_args

    if host_mode:
        result = _host_operation(
            "tests",
            [pytest_command],
            reset=True,
        )
    else:
        result = _operation(
            "tests",
            [[
                "python3",
                "-m",
                "pytest",
                "-s",
                "--cov=files",
                "--cov-report=html",
                "--cov-report=term",
            ] + pytest_args],
            reset=True,
        )

    sys.exit(result.returncode)

if __name__=='__main__':
    run_test(sys.argv)
