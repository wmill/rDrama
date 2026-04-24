#!/usr/bin/env python3

import sys
from common import _ensure_host_infra, _host_flask, _operation

def run_command(argv):
    host_mode = False
    flask_args = []
    for arg in argv[1:]:
        if arg == "--host":
            host_mode = True
            continue
        flask_args.append(arg)

    if host_mode:
        _ensure_host_infra(reset=False)
        result = _host_flask(
            flask_args,
            on_stdout_line=lambda line: print(line, end=""),
            on_stderr_line=lambda line: print(line, end=""),
        )
    else:
        result = _operation(
            "command",
            [[
                "python3",
                "-m",
                "flask",
            ] + flask_args],
        )

    sys.exit(result.returncode)

if __name__ == '__main__':
    run_command(sys.argv)
