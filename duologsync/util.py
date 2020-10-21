"""
Unrelated, but useful functions used in various places throughout DuoLogSync.
"""

import os
import json
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import duo_client
from duologsync.config import Config
from duologsync.program import Program, ProgramShutdownError
from duologsync.__version__ import __version__
import six

EXECUTOR = ThreadPoolExecutor(3)


async def restless_sleep(duration):
    """
    Wrapper for the asyncio.sleep function to sleep for duration seconds
    but check every second that DuoLogSync is still running. This is
    necessary in the case that the program should be shutting down but
    a producer is in the middle of a 2 minute poll and will not be aware
    of program shutdown until much later.

    @param duration The number of seconds to sleep for
    """

    while duration > 0:
        await asyncio.sleep(1)

        # Poll for program running state
        if Program.is_running():
            duration = duration - 1
            continue

        # Otherwise, program is done running, raise an exception to be caught
        raise ProgramShutdownError


async def run_in_executor(function_obj):
    """
    The function represented by function_obj is a high latency call which will
    block the event loop. Thus, the function is run in an executor - a
    dedicated thread pool - which allows for the event loop to do other work
    while the given function is being made.

    @param function_obj A high-latency, callable object to run in the executor

    @return the result of calling the function in function_obj
    """

    result = await asyncio.get_event_loop().run_in_executor(
        EXECUTOR,
        function_obj
    )

    return result


def get_log_offset(log_type, recover_log_offset, checkpoint_directory, child_account_id=None):
    """
    Retrieve the offset from which logs of log_type should be fetched either by
    using the default offset or by using a timestamp saved in a checkpoint file

    @param log_type             Name of the log for which recovery is occurring
    @param recover_log_offset   Whether checkpoint files should be used to
                                retrieve log offset info
    @param checkpoint_directory Directory containing log offset checkpoint files

    @return the last offset read for a log type based on checkpointing data
    """

    milliseconds_per_second = 1000
    log_offset = Config.get_api_offset()

    # Auth must have timestamp represented in milliseconds, not seconds
    if log_type == Config.AUTH:
        log_offset *= milliseconds_per_second

    # In this case, look for a checkpoint file from which to read the log offset
    if recover_log_offset:
        try:
            checkpoint_file_path = os.path.join(
                checkpoint_directory,
                f"{log_type}_checkpoint_data_" + child_account_id + ".txt")\
                if child_account_id else os.path.join(
                checkpoint_directory,
                f"{log_type}_checkpoint_data.txt")

            # Open the checkpoint file, 'with' statement automatically closes it
            with open(checkpoint_file_path) as checkpoint:
                # Set log_offset equal to the contents of the checkpoint file
                log_offset = json.loads(checkpoint.read())

        # Most likely, the checkpoint file doesn't exist
        except OSError:
            Program.log(f"Could not read checkpoint file for {log_type} logs, "
                        "consuming logs from {log_offset} timestamp")

    return log_offset


def create_admin(ikey, skey, host, is_msp=False, proxy_server=None, proxy_port=None):
    """
    Create an Admin object (from the duo_client library) with the given values.
    The Admin object has many functions for using Duo APIs and retrieving logs.

    @param ikey Duo Client ID (Integration Key)
    @param skey Duo Client Secret for proving identity / access (Secret Key)
    @param host URI where data / logs will be fetched from
    @param is_msp Indicates where we are using MSP account for logs retrieval
    @param proxy_server Host/IP of Http Proxy if in use or None
    @param proxy_port Port of Http Proxy if in use or None
    @return a newly created Admin object
    """

    if is_msp:
        admin = duo_client.Accounts(
            ikey=ikey,
            skey=skey,
            host=host,
            user_agent=f"Duo Log Sync/{__version__}"
        )
        Program.log(f"duo_client Account_Admin initialized for ikey: {ikey}, host: {host}",
                    logging.INFO)
    else:
        admin = duo_client.Admin(
            ikey=ikey,
            skey=skey,
            host=host,
            user_agent=f"Duo Log Sync/{__version__}"
        )
        Program.log(f"duo_client Admin initialized for ikey: {ikey}, host: {host}",
                    logging.INFO)

    if proxy_server and proxy_port:
        admin.set_proxy(host=proxy_server, port=proxy_port)
        Program.log(f"duo_client Proxy configured: {proxy_server}:{proxy_port}", logging.INFO)


    return admin


def normalize_params(params):
    """
    Return copy of params with strings listified
    and unicode strings utf-8 encoded.
    """
    # urllib cannot handle unicode strings properly. quote() excepts,
    # and urlencode() replaces them with '?'.
    def encode(value):
        if isinstance(value, six.text_type):
            return value.encode("utf-8")
        return value

    def to_list(value):
        if value is None or isinstance(value, six.string_types):
            return [value]
        return value
    return dict(
        (encode(key), [encode(v) for v in to_list(value)])
        for (key, value) in list(params.items()))
