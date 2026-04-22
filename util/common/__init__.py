# import pprint
import subprocess
import sys
import time

def _execute(command,**kwargs):
    # print("Running:")
    # pprint.pprint(command)

    check = kwargs.get('check', True)
    on_stdout_line = kwargs.get('on_stdout_line', None)
    on_stderr_line = kwargs.get('on_stderr_line', None)
    with subprocess.Popen(
        command,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as proc:
        stdout = None
        if proc.stdout:
            stdout = ''
            for line in proc.stdout:
                if on_stdout_line:
                    on_stdout_line(line)
                stdout += line

        stderr = None
        if proc.stderr:
            stderr = ''
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
            print(stdout)
            print("STDERR (not interlaced properly, sorry):")
            print(stderr)
            
            raise subprocess.CalledProcessError(
                    proc.returncode,
                    command,
                    stdout or None,
                    stderr or None
            )
        else:
            return subprocess.CompletedProcess(
                    command,
                    proc.returncode,
                    stdout or None,
                    stderr or None
            )

def _docker(command, **kwargs):
    return _execute([
        "docker",
        "compose",
        "exec", '-T',
        "site",
    ] + command,
    **kwargs)

def _compose(command, **kwargs):
    return _execute([
        "docker",
        "compose",
    ] + command,
    **kwargs)

def _start():
    print("Starting containers in operation mode . . .")
    print("  If this takes a while, it's probably building the container.")
    command = [
        '-f', 'docker-compose.yml',
        '-f', 'docker-compose-operation.yml',
        'up',
        '--build',
        '-d',
    ]
    result = _compose(command)

    # alright this seems sketchy, bear with me

    # previous versions of this code used the '--wait' command-line flag
    # the problem with --wait is that it waits for the container to be healthy and working
    # "but wait, isn't that what we want?"
    # ah, but see, if the container will *never* be healthy and working - say, if there's a flaw causing it to fail on startup - it just waits forever
    # so that's not actually useful

    # previous versions of this code also had a check to see if the containers started up properly
    # but this is surprisingly annoying to do if we don't know the containers' names
    # docker compose *can* do it, but you either have to use very new features that aren't supported on Ubuntu 22.04, or you have to go through a bunch of parsing pain
    # and it kind of doesn't seem necessary

    # see, docker compose in this form *will* wait until it's *attempted* to start each container.
    # so at this point in execution, either the containers are running, or they're crashed
    # if they're running, hey, problem solved, we're good
    # if they're crashed, y'know what, problem still solved! because our next command will fail

    # maybe there's still a race condition? I dunno! Keep an eye on this.
    # If there is a race condition then you're stuck doing something gnarly with `docker compose ps`. Good luck!

    return result

def _stop():
    print("Stopping containers . . .")
    result = _compose(['stop'])
    return result

def _down(volumes=False):
    print("Removing containers . . .")
    command = ['down']
    if volumes:
        command.append('-v')
    result = _compose(command)
    return result

def _wait_for_site(timeout_seconds=60):
    print("Waiting for site container readiness . . .")
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        result = _docker(
            ["python3", "-c", "print('ready')"],
            check=False,
        )
        if result.returncode == 0:
            print("  Containers started!")
            return
        last_error = result
        time.sleep(1)

    print("Container startup failed. Recent logs:")
    _compose(
        ['logs', '--no-color', 'site', 'postgres', 'redis'],
        check=False,
        on_stdout_line=lambda line: print(line, end=''),
    )
    raise subprocess.CalledProcessError(
        last_error.returncode if last_error else 1,
        ["docker", "compose", "exec", "-T", "site", "python3", "-c", "print('ready')"],
        last_error.stdout if last_error else None,
        last_error.stderr if last_error else None,
    )

def _operation(name, commands, reset=False):
    # restart to make sure they're in the right mode
    if reset:
        _down(volumes=True)
    else:
        _stop()

    try:
        _start()
        _wait_for_site()

        # prepend our upgrade, since right now we're always using it
        commands = [[
            "python3",
            "-m", "flask",
            "db", "upgrade"
        ]] + commands

        # run operations in docker container
        print(f"Running {name} . . .")
        for command in commands:
            result = _docker(
                command,
                on_stdout_line=lambda line: print(line, end=''),
                on_stderr_line=lambda line: print(line, end=''),
            )

        return result
    finally:
        if reset:
            _down()
        else:
            _stop()

def run_help():
    print("Available commands: (test|migrate|help)")
    print("Usage: './manage.py <command> [options]'")
    exit(0)

def error(message,code=1):
    print(message,file=sys.stderr)
    exit(code)
