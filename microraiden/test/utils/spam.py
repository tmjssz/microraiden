import gevent
import logging
from web3 import Web3
from eth_utils import decode_hex, big_endian_to_int, to_checksum_address
import rlp

log = logging.getLogger('spammer')


class Spammer(gevent.Greenlet):
    def __init__(self, web3: Web3, input_file: str, num: int, offset: int = 0):
        gevent.Greenlet.__init__(self)

        self.web3 = web3
        self.num = num
        self.offset = offset

        try:
            self.input_file = open(input_file, 'r')
        except Exception as err:
            log.error('failed to open file with transaction data: %s', err)
            raise

        # Get raw transactions from file.
        self.transactions = self.input_file.read().splitlines()
        if not self.transactions:
            err = RuntimeError('no transaction data found in file {}'.format(input_file))
            log.error(err)
            raise err

        # Check that offset is not higher than number of given transactions.
        if len(self.transactions) < self.offset + 1:
            err = RuntimeError('offset={} is too high, only {} transactions were found'.format(
                self.offset, len(self.transactions)))
            log.error(err)
            raise err

        # Check that number of loaded spam transactions is large enough for the desired spam amount.
        if self.num is not None and len(self.transactions) - self.offset < self.num:
            err = RuntimeError('num={} is too high with offset={}, only {} transactions were found'.format(
                self.num, self.offset, len(self.transactions)))
            log.error(err)
            raise err

        # Decode first transaction to get first nonce and sender address.
        first_tx = rlp.decode(decode_hex(self.transactions[0]))
        self.first_nonce = big_endian_to_int(first_tx[0])
        self.sender_address = to_checksum_address(first_tx[3])
        self.gas_price = big_endian_to_int(first_tx[1])

        # Get the next valid nonce value.
        self.nonce = self.web3.eth.getTransactionCount(self.sender_address, 'pending')

        log.info('Loaded %s spam transactions (sender=%s)',
                 len(self.transactions), self.sender_address)

        # Make sure that first nonce is not too high.
        if self.first_nonce > self.nonce:
            err = RuntimeError(
                'given spam transactions start with a too high nonce of {} (next valid nonce = {})'
                .format(self.first_nonce, self.nonce)
            )
            log.error(err)
            raise err

        # Make sure that not all transactions have too low nonce values.
        last_nonce = self.first_nonce + len(self.transactions) - 1
        if last_nonce < self.nonce:
            err = RuntimeError(
                'too low nonce values {}-{} in the given spam transactions (next valid nonce = {})'
                .format(self.first_nonce, last_nonce, self.nonce)
            )
            log.error(err)
            raise err

        self.do_run = True
        self.num_sent = 0

    def get_next_valid_transaction(self) -> str:
        '''
        Returns the raw transaction that has a valid nonce value.
        '''
        # Get the next valid nonce value.
        self.nonce = self.web3.eth.getTransactionCount(self.sender_address, 'pending')
        return self.get_transaction(self.nonce)

    def get_transaction(self, index: int = 0) -> str:
        '''
        Returns the raw transaction at the given index from the list of loaded transactions.
        If the index is not existing, None is returned.
        '''
        if (len(self.transactions) < index + 1) | (index < 0):
            return None
        return self.transactions[index]

    def _run(self):
        if self.offset > 0:
            log.info('Start sending %s spam transactions with nonce offset=%s', self.num, self.offset)
        else:
            log.debug('Start sending %s spam transactions', self.num)

        # Skip transactions with a too low nonce value.
        if self.first_nonce + self.offset < self.nonce:
            skip_amount = self.nonce - self.first_nonce
            log.warning(
                'Skipping the first %s transactions because of too low nonce values', skip_amount)
            self.offset += skip_amount

        for i, raw_txn in enumerate(self.transactions):
            # Stop spamming if do_run flag is set to false.
            if not self.do_run:
                break

            # Stop spamming if desired number of transactions has already been sent.
            if self.num is not None and self.num_sent >= self.num:
                break

            # Skip transactions that with an index smaller than the offset.
            if i < self.offset:
                continue

            # Send the transaction.
            try:
                self.web3.eth.sendRawTransaction(raw_txn)
                self.num_sent += 1
            except Exception as err:
                log.error('failed to send transaction: %s', err)

        log.debug('Sent %s spam transactions', self.num_sent)

    def stop(self):
        self.do_run = False
