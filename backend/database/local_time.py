"""Local-time SQL views; canonical UTC tables are never rewritten."""
from datetime import datetime
import os
import re
from pathlib import Path


def display_timezone(value=None):
    value = value or os.getenv('SUMO_DISPLAY_TIMEZONE')
    if not value:
        offset = datetime.now().astimezone().strftime('%z')
        value = offset[:3] + ':' + offset[3:]
    if re.fullmatch(r'[+-]\d{2}:\d{2}', value):
        hours, minutes = map(int, value[1:].split(':'))
        if minutes > 59 or hours > 14 or (hours == 14 and minutes):
            raise ValueError('Invalid display timezone offset.')
    elif not re.fullmatch(r'[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+)+', value):
        raise ValueError('Use a UTC offset such as +08:00 or an IANA timezone such as Asia/Shanghai.')
    return value


def install_local_views(connection, timezone=None):
    zone = display_timezone(timezone)
    with connection.cursor() as cursor:
        cursor.execute("SELECT CONVERT_TZ('2026-01-01 00:00:00','+00:00',%s)", (zone,))
        if cursor.fetchone()[0] is None:
            raise ValueError('MySQL cannot resolve this timezone. Load MySQL timezone tables for named zones, '
                             'or use +08:00 for Asia/Shanghai.')
        # display_timezone only allows offsets or safe IANA identifiers, not SQL text.
        sql = Path(__file__).with_name('local_views.sql').read_text().replace('__DISPLAY_TIMEZONE__', zone)
        for statement in sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
    connection.commit()
    return zone
