"""Keep native Scheduler startup messages short without dropping subscriptions.

Core commands: https://wiki.dynamita.com/en/sumocore-commands
Variable subscription: https://wiki.dynamita.com/en/javax
"""
from pathlib import Path


def write_startup_script(folder, commands, variables):
    """Move the potentially large follow list into a local Core script.

    Scheduler still subscribes to Sumo__Time itself. Each other variable gets
    one complete follow command, after initialization and before start. The
    script must remain available for the full asynchronous job lifetime.
    """
    if not commands or commands[-1].strip().rstrip(';') != 'start':
        raise ValueError('SUMO startup must end with start.')
    follows = []
    for name in dict.fromkeys(variables):
        if not name or any(c.isspace() or c in ';|"\x00' for c in name):
            raise ValueError(f'Invalid SUMO subscription name: {name!r}')
        if name != 'Sumo__Time':
            follows.append(f'follow {name};')
    script = Path(folder) / 'startup.scs'
    script.write_text('\n'.join([
        *(command.strip().rstrip(';') + ';' for command in commands[:-1]),
        *follows, 'start;', '',
    ]), encoding='utf-8')
    return script
