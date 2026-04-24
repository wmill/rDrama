#!/usr/bin/env python3

import sys

from common import _ensure_host_infra, _host_flask


def run_dev(argv):
    flask_run_args = argv[1:]
    if not flask_run_args:
        flask_run_args = ["--debug", "run", "--host=0.0.0.0", "--port=5555"]

    _ensure_host_infra(reset=False)

    setup_commands = [
        ["db", "upgrade"],
        ["cron_setup"],
    ]

    for command in setup_commands:
        _host_flask(
            command,
            on_stdout_line=lambda line: print(line, end=""),
            on_stderr_line=lambda line: print(line, end=""),
        )

    result = _host_flask(
        flask_run_args,
        env_updates={
            "ENABLE_SERVICES": "true",
            "ENFORCE_PRODUCTION": "False",
            "WERKZEUG_DEBUG_PIN": "off",
        },
        on_stdout_line=lambda line: print(line, end=""),
        on_stderr_line=lambda line: print(line, end=""),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    run_dev(sys.argv)
