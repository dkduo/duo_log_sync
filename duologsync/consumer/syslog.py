"""
Definition of function for returning a Syslog Header following either RFC5424 or RFC3164 standards
https://tools.ietf.org/html/rfc5424
https://tools.ietf.org/html/rfc3164
"""

import socket
from datetime import datetime, timezone

DEFAULT_PRIORITY = 38  # facility=4 (Auth) and severity=6 (Informational), (facility x 8) + severity
SYSLOG_VERSION = 1
DEFAULT_FORMAT = 'RFC5424'  # 'RFC5424' or 'RFC3164'


def get_syslog_header(format=DEFAULT_FORMAT, timestamp=datetime.now(timezone.utc), priority=DEFAULT_PRIORITY):
    """
    Return a syslog header in the supplied format using the supplied timestamp.

    @param format                Which RFC version to use, either RFC5424 or RFC3164

    @param timestamp             Timestamp to be used when generating the syslog header

    @param priority              The number contained within these angle brackets is known as the
                                 Priority value (PRIVAL) and represents both the Facility and Severity.


    @return a syslog header
    """
    syslog_pri = f"<{priority}>"

    if format.upper() == 'RFC5424':
        syslog_pri_version = f"{syslog_pri}{SYSLOG_VERSION}"
        syslog_date_time = timestamp.isoformat(sep='T', timespec='milliseconds')
        first_part = ' '.join([syslog_pri_version, syslog_date_time])

    elif format.upper() == 'RFC3164':
        syslog_date_time = timestamp.strftime("%b %d %H:%M:%S")
        first_part = ''.join([syslog_pri, syslog_date_time])

    else:
        raise ValueError(
            f"{format} is not a supported syslog format")

    syslog_header = ' '.join([first_part, socket.gethostname()])

    return syslog_header
