import sys
import asyncio
import logging
import duo_client

from concurrent.futures import ThreadPoolExecutor
from duologsync.config_generator import ConfigGenerator
from duologsync.__version__ import __version__
from duologsync.util import create_writer, update_last_offset_read

class LogSyncBase:

    def __init__(self, args):
        self.loop = asyncio.get_event_loop()

        self._executor = ThreadPoolExecutor(3)
        self.last_offset_read = {}

        self.config = ConfigGenerator().get_config(args.ConfigPath)

        self.admin_api = self.init_duoclient(self.config)

        self.writer = None

    def init_duoclient(self, config):
        try:
            client = duo_client.Admin(
                ikey=config['duoclient']['ikey'],
                skey=config['duoclient']['skey'],
                host=config['duoclient']['host'],
                user_agent=('Duo Log Sync/' + __version__),
            )
            logging.info("Adminapi initialized for ikey {} and host {}...".
                         format(config['duoclient']['ikey'],
                                config['duoclient']['host']))
        except Exception as e:
            logging.error("Unable to create duo client. Pls check credentials...")
            sys.exit(1)

        return client

    def start(self):
        """
        Driver class for duologsync application which initializes event loop
        and sets producer consumer for different endpoints as specified by
        user in config file.
        """
        from duologsync.producer.authlog_producer import AuthlogProducer
        from duologsync.producer.telephony_producer import TelephonyProducer
        from duologsync.consumer.authlog_consumer import AuthlogConsumer
        from duologsync.consumer.telephony_consumer import TelephonyConsumer
        from duologsync.producer.adminaction_producer import AdminactionProducer
        from duologsync.consumer.adminaction_consumer import AdminactionConsumer

        self.writer = self.loop.run_until_complete(
            create_writer(self.config, self.loop)
        )

        # Enable endpoints based on user selection
        tasks = []
        enabled_endpoints = self.config['logs']['endpoints']['enabled']
        for endpoint in enabled_endpoints:
            new_queue = asyncio.Queue(loop=self.loop)
            producer = consumer = None

            # Populate last_offset_read for each enabled endpoint
            if self.config['recoverFromCheckpoint']['enabled']:
                update_last_offset_read(
                    self.config['logs']['checkpointDir'],
                    self.last_offset_read,
                    endpoint
                )

            if endpoint == 'auth':
                producer = AuthlogProducer(self.config, self.last_offset_read,
                                           new_queue, self)
                consumer = AuthlogConsumer(self.config, self.last_offset_read,
                                           new_queue, self.writer)
            elif endpoint == "telephony":
                producer = TelephonyProducer(self.config, self.last_offset_read,
                                             new_queue, self)
                consumer = TelephonyConsumer(self.config, self.last_offset_read,
                                             new_queue, self.writer)
            elif endpoint == "adminaction":
                producer = AdminactionProducer(self.config,
                                               self.last_offset_read,
                                               new_queue, self)
                consumer = AdminactionConsumer(self.config,
                                               self.last_offset_read,
                                               new_queue, self.writer)
            else:
                logging.info("%s is not a recognized endpoint", endpoint)
                del new_queue
                continue

            tasks.append(asyncio.ensure_future(producer.produce()))
            tasks.append(asyncio.ensure_future(consumer.consume()))

        self.loop.run_until_complete(asyncio.gather(*tasks))
        self.loop.close()
