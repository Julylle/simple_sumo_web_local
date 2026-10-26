"""Keep native Scheduler startup messages short without dropping subscriptions.

Core commands: https://wiki.dynamita.com/en/sumocore-commands
Variable subscription: https://wiki.dynamita.com/en/javax
"""
from pathlib import Path
import zipfile


def project_parameter_commands(project):
    """Load the project's base constant inputs before restoring model state.

    Live/DB inputs own the dynamic schedule, so embedded dynamic TSV inputs
    must not run alongside them. The base Value column matches DTT's default
    extract_parameters_from_project scenario selection.
    """
    with zipfile.ZipFile(project) as archive:
        try:
            text = archive.read('parameters.txt').decode('utf-8-sig')
        except KeyError as exc:
            raise ValueError('SUMO project is missing parameters.txt; cannot restore its process settings.') from exc
    commands = []
    constant = False
    header = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('['):
            constant = line == '[CONSTANT INPUT]'
            header = constant
            continue
        if not constant:
            continue
        if header:
            header = False
            continue
        cells = line.split('\t')
        if len(cells) < 2 or not cells[1].strip():
            raise ValueError('Invalid constant input in SUMO parameters.txt: ' + cells[0])
        name, value = cells[0].strip(), cells[1].strip()
        if not name.startswith('Sumo__') or any(c.isspace() or c in ';|"\x00' for c in name):
            raise ValueError('Invalid SUMO parameter name: ' + name)
        if any(c in value for c in ';|\x00'):
            raise ValueError('Invalid SUMO parameter value: ' + name)
        commands.append(f'set {name} {value};')
    return commands


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
