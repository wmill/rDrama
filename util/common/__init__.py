import os
import re
import subprocess
import sys
import time
from pathlib import Path

COMPOSE_MAIN = ["-f", "docker-compose.yml"]
COMPOSE_OPERATION = COMPOSE_MAIN + ["-f", "docker-compose-operation.yml"]
INFRA_SERVICES = ["postgres", "redis"]
SITE_SERVICE = "site"
TEST_DATABASE_NAME = os.environ.get("RDRAMA_TEST_DB", "rdrama_test")


def _ensure_safe_db_name(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        error(f"Unsafe test database name: {name!r}")
    return name


def _docker_test_database_url():
    db_name = _ensure_safe_db_name(TEST_DATABASE_NAME)
    return f"postgresql://postgres@postgres:5432/{db_name}"


def _host_test_database_url():
    db_name = _ensure_safe_db_name(TEST_DATABASE_NAME)
    return f"postgresql://postgres@localhost:5432/{db_name}"


def _execute(command, **kwargs):
    check = kwargs.get("check", True)
    on_stdout_line = kwargs.get("on_stdout_line")
    on_stderr_line = kwargs.get("on_stderr_line")
    env_updates = kwargs.get("env_updates")

    env = os.environ.copy()
    if env_updates:
        env.update(env_updates)

    with subprocess.Popen(
        command,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    ) as proc:
        stdout = ""
        stderr = ""

        if proc.stdout:
            for line in proc.stdout:
                if on_stdout_line:
                    on_stdout_line(line)
                stdout += line

        if proc.stderr:
            for line in proc.stderr:
                if on_stderr_line:
                    on_stderr_line(line)
                stderr += line

        proc.wait()

        if check and proc.returncode != 0:
            print("Command:")
            print(command)
            print(f"Exit code: {proc.returncode}")
            print("STDOUT:")
            print(stdout or None)
            print("STDERR:")
            print(stderr or None)
            raise subprocess.CalledProcessError(
                proc.returncode,
                command,
                stdout or None,
                stderr or None,
            )

        return subprocess.CompletedProcess(
            command,
            proc.returncode,
            stdout or None,
            stderr or None,
        )


def _compose(command, operation_mode=False, **kwargs):
    compose_files = COMPOSE_OPERATION if operation_mode else COMPOSE_MAIN
    return _execute(["docker", "compose"] + compose_files + command, **kwargs)


def _docker(command, **kwargs):
    return _compose(["exec", "-T", SITE_SERVICE] + command, operation_mode=True, **kwargs)


def _host_python():
    candidates = [
        Path(".venv/bin/python"),
        Path(".venv/Scripts/python.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    error("Host virtualenv not found. Run 'poetry install --with dev' first.")


def _host_env_updates(extra_updates=None):
    updates = {}

    lib_dirs = [
        "/opt/homebrew/opt/libpq/lib",
        "/opt/homebrew/opt/postgresql@17/lib",
        "/opt/homebrew/opt/postgresql@16/lib",
        "/opt/homebrew/opt/postgresql@15/lib",
        "/opt/homebrew/opt/postgresql@14/lib",
    ]
    existing_lib_dirs = [path for path in lib_dirs if Path(path).exists()]
    if existing_lib_dirs:
        current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        updates["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(existing_lib_dirs + ([current] if current else []))

    libpq_bin = Path("/opt/homebrew/opt/libpq/bin")
    if libpq_bin.exists():
        updates["PATH"] = f"{libpq_bin}:{os.environ.get('PATH', '')}"

    if extra_updates:
        updates.update(extra_updates)

    return updates


def _host_execute(command, **kwargs):
    env_updates = _host_env_updates(kwargs.pop("env_updates", None))
    kwargs["env_updates"] = env_updates
    return _execute(command, **kwargs)


def _host_flask(command, **kwargs):
    return _host_execute([_host_python(), "-m", "flask", "--app", "files/cli:app"] + command, **kwargs)


def _start_operation_stack(env_updates=None):
    print("Starting containers in operation mode . . .")
    print("  If this takes a while, it's probably building the container.")
    return _compose(["up", "--build", "-d"], operation_mode=True, env_updates=env_updates)


def _start_infra():
    print("Starting Postgres and Redis in Docker . . .")
    return _compose(["up", "-d"] + INFRA_SERVICES)


def _start_operation_infra():
    print("Starting Postgres and Redis in operation mode . . .")
    return _compose(["up", "-d"] + INFRA_SERVICES, operation_mode=True)


def _stop(operation_mode=False, **kwargs):
    print("Stopping containers . . .")
    return _compose(["stop"], operation_mode=operation_mode, **kwargs)


def _down(volumes=False, operation_mode=False, **kwargs):
    print("Removing containers . . .")
    command = ["down"]
    if volumes:
        command.append("-v")
    return _compose(command, operation_mode=operation_mode, **kwargs)


def _wait_for_site(timeout_seconds=60):
    print("Waiting for site container readiness . . .")
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        result = _docker(["python3", "-c", "print('ready')"], check=False)
        if result.returncode == 0:
            print("  Containers started!")
            return
        last_error = result
        time.sleep(1)

    print("Container startup failed. Recent logs:")
    _compose(
        ["logs", "--no-color", SITE_SERVICE, "postgres", "redis"],
        operation_mode=True,
        check=False,
        on_stdout_line=lambda line: print(line, end=""),
        on_stderr_line=lambda line: print(line, end=""),
    )
    raise subprocess.CalledProcessError(
        last_error.returncode if last_error else 1,
        ["docker", "compose", "exec", "-T", SITE_SERVICE, "python3", "-c", "print('ready')"],
        last_error.stdout if last_error else None,
        last_error.stderr if last_error else None,
    )


def _wait_for_infra(timeout_seconds=60, operation_mode=False):
    print("Waiting for Postgres and Redis readiness . . .")
    deadline = time.monotonic() + timeout_seconds
    pg_result = None
    redis_result = None

    while time.monotonic() < deadline:
        pg_result = _compose(
            ["exec", "-T", "postgres", "pg_isready", "-U", "postgres"],
            operation_mode=operation_mode,
            check=False,
        )
        redis_result = _compose(
            ["exec", "-T", "redis", "redis-cli", "ping"],
            operation_mode=operation_mode,
            check=False,
        )
        if pg_result.returncode == 0 and redis_result.returncode == 0:
            print("  Postgres and Redis are ready!")
            return
        time.sleep(1)

    print("Infrastructure startup failed. Recent logs:")
    _compose(
        ["logs", "--no-color"] + INFRA_SERVICES,
        operation_mode=operation_mode,
        check=False,
        on_stdout_line=lambda line: print(line, end=""),
        on_stderr_line=lambda line: print(line, end=""),
    )
    raise subprocess.CalledProcessError(
        1,
        ["docker", "compose", "up", "-d"] + INFRA_SERVICES,
        pg_result.stdout if pg_result else None,
        redis_result.stdout if redis_result else None,
    )


def _reset_infra_services():
    print("Resetting Postgres and Redis containers . . .")
    _compose(["stop"] + INFRA_SERVICES, check=False)
    _compose(["rm", "-f", "-s", "-v"] + INFRA_SERVICES, check=False)


def _psql(sql, operation_mode=False, database="postgres"):
    return _compose(
        ["exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database, "-c", sql],
        operation_mode=operation_mode,
    )


def _psql_file(file_path, operation_mode=False, database="postgres"):
    return _compose(
        ["exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database, "-f", file_path],
        operation_mode=operation_mode,
    )


def _reset_test_database(operation_mode=False):
    db_name = _ensure_safe_db_name(TEST_DATABASE_NAME)
    print(f"Resetting test database '{db_name}' . . .")
    _psql(
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
        operation_mode=operation_mode,
    )
    _psql(f"DROP DATABASE IF EXISTS {db_name};", operation_mode=operation_mode)
    _psql(f"CREATE DATABASE {db_name};", operation_mode=operation_mode)
    _psql_file("/docker-entrypoint-initdb.d/00-schema.sql", operation_mode=operation_mode, database=db_name)
    _psql_file("/docker-entrypoint-initdb.d/10-seed-db.sql", operation_mode=operation_mode, database=db_name)


def _ensure_host_infra(reset=False):
    _start_infra()
    _wait_for_infra()
    if reset:
        _reset_test_database()


def _operation(name, commands, reset=False):
    _stop(operation_mode=True, check=False)

    try:
        test_database_url = _docker_test_database_url()
        _start_operation_infra()
        _wait_for_infra(operation_mode=True)
        if reset:
            _reset_test_database(operation_mode=True)
        _start_operation_stack(env_updates={"DATABASE_URL": test_database_url})
        _wait_for_site()

        commands = [["python3", "-m", "flask", "db", "upgrade"]] + commands
        commands = [["env", f"DATABASE_URL={test_database_url}"] + command for command in commands]

        print(f"Running {name} . . .")
        for command in commands:
            result = _docker(
                command,
                on_stdout_line=lambda line: print(line, end=""),
                on_stderr_line=lambda line: print(line, end=""),
            )

        return result
    finally:
        _stop(operation_mode=True, check=False)


def _host_operation(name, commands, reset=False, bootstrap_db=True):
    _ensure_host_infra(reset=reset)
    test_env = {
        "DBG_LIMITER_DISABLED": "true",
        "DATABASE_URL": _host_test_database_url(),
    }

    if bootstrap_db:
        commands = [["db", "upgrade"]] + commands

    print(f"Running {name} on host . . .")
    for command in commands:
        if command[:2] == ["pytest", "-m"]:
            result = _host_execute(
                [_host_python()] + command,
                env_updates=test_env,
                on_stdout_line=lambda line: print(line, end=""),
                on_stderr_line=lambda line: print(line, end=""),
            )
        elif command and command[0] == "pytest":
            result = _host_execute(
                [_host_python(), "-m"] + command,
                env_updates=test_env,
                on_stdout_line=lambda line: print(line, end=""),
                on_stderr_line=lambda line: print(line, end=""),
            )
        else:
            result = _host_flask(
                command,
                env_updates=test_env,
                on_stdout_line=lambda line: print(line, end=""),
                on_stderr_line=lambda line: print(line, end=""),
            )

    return result

def run_help():
    print("Available commands: (test|dev|command|help)")
    print("Usage: './manage.py <command> [options]'")
    exit(0)

def error(message,code=1):
    print(message,file=sys.stderr)
    exit(code)
