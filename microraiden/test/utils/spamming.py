import gevent
import logging
from web3 import Web3

log = logging.getLogger('spammer')


class Spammer(gevent.Greenlet):
    def __init__(
        self,
        web3: Web3,
        input_file: str,
        offset: int=0,
    ):
        gevent.Greenlet.__init__(self)

        self.web3 = web3
        self.offset = offset

        try:
            self.input_file = open(input_file, 'r')
        except Exception as err:
            log.error('failed to open file with transaction data: %s', err)
            raise

        self.transactions = self.input_file.read().splitlines()
        if len(self.transactions) == 0:
            err = RuntimeError('no transaction data found in file {}'.format(input_file))
            log.error(err)
            raise err

        log.info('found {} transactions'.format(len(self.transactions)))

        self.num_sent = 0

    def get_transaction(self, index: int=0) -> str:
        if len(self.transactions) < index + 1:
            return None
        return self.transactions[index]

    def _run(self):
        for i, txn in enumerate(self.transactions):
            if i < self.offset:
                continue
            try:
                self.web3.eth.sendRawTransaction(txn)
                self.num_sent += 1
            except Exception as err:
                log.error('failed to send transaction: %s', err)
