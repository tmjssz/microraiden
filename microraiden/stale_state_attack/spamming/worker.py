#!/usr/bin/python

import logging
import time
from threading import Thread
from web3 import Web3
from .utils.crypto import privkey_to_addr
from .utils.transaction import create_signed_transaction
from .manager import SpamManager


class SpamWorker(Thread):
    '''
    The SpamWorker class can be used to repeatedly send empty spam transactions
    into a blockchain network.
    '''

    def __init__(
        self,
        web3: Web3,
        manager: SpamManager,
        private_key: str,
    ):
        self.logger = logging.getLogger('spam-worker')

        self.web3 = web3
        self.private_key = private_key
        self.manager = manager
        self.network_id = int(web3.version.network)

        self.do_send = False

        self.account_address = privkey_to_addr(private_key)

        Thread.__init__(self)

    def run(self):
        self.do_run = True

        while self.do_run:
            if self.do_send:
                num_pending_transactions = int(self.web3.txpool.status.pending, 16)
                desired_pending_level_reached = num_pending_transactions >= self.manager.desired_pending_txs()

                # Send next transaction if more pending transactions are desired
                if not desired_pending_level_reached:
                    self.send_next_transaction()
            else:
                self.create_next_transaction()

    def send_next_transaction(self):
        '''
        Sends the next transaction.
        If the queue is empty, create a new signed transaction instead.
        '''
        if self.do_send:
            tx = self.manager.next_transaction()
            if tx is not None:
                try:
                    # Send next transaction from queue
                    self.web3.eth.sendRawTransaction(tx)
                except ValueError as e:
                    self.logger.error('Sending transaction failed: {}'.format(e))
                except Exception as e:
                    self.logger.error('Sending transaction failed: {}'.format(e))
                    # self.manager.tx_queue.appendleft(tx)
                    # self.logger.info('Trying to resend transaction')
            else:
                self.create_next_transaction()

    def create_next_transaction(self):
        '''
        Create a new spam transaction and append it to the transaction queue.
        '''
        if not self.manager.is_tx_queue_full():
            # If queue is not full, create a new spam transaction
            nonce = self.manager.reserve_nonce()
            tx = create_signed_transaction(
                network_id=self.network_id,
                private_key=self.private_key,
                to=self.account_address,
                nonce=nonce,
                data=str(time.time()),
            )
            self.manager.enqueue_transaction(tx)

    def stop(self):
        '''
        Stop the execution of this thread.
        '''
        self.do_run = False
