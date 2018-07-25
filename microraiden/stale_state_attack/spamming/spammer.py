#!/usr/bin/python

import logging
import time
from threading import Thread, active_count
from web3 import Web3, HTTPProvider
from .utils.crypto import privkey_to_addr
from .utils.transaction import create_signed_transaction
from .manager import SpamManager
from .worker import SpamWorker


class Spammer(Thread):
    '''
    The Spammer class can be used to generate a blockchain congestion.
    '''

    def __init__(
        self,
        private_key: str,
        rpc_addr: str='http://127.0.0.1',
        rpc_port: int=8545,
        number_threads: int=1,
        nonce_offset: int=0,
        target_block: int=None,
        block_size: int=220,
    ):
        self.logger = logging.getLogger('spam')

        # Initialize web3
        self.web3 = Web3(HTTPProvider('{}:{}'.format(rpc_addr, rpc_port)))
        self.network_id = int(self.web3.version.network)

        self.private_key = private_key
        self.account_address = privkey_to_addr(private_key)

        initial_nonce = self.web3.eth.getTransactionCount(self.account_address, 'pending') + nonce_offset

        # Initialize spam manager.
        self.manager = SpamManager(
            web3=self.web3,
            initial_nonce=initial_nonce,
            target_block=target_block,
            block_size=block_size,
        )

        # Initialize and start spamming worker threads
        self.threads = []
        for i in range(number_threads):
            thread = SpamWorker(
                web3=self.web3,
                manager=self.manager,
                private_key=private_key,
            )
            self.threads.append(thread)
            thread.start()

        Thread.__init__(self)

    def run(self):
        for thread in self.threads:
            thread.do_send = True

        self.logger.info('Start network spamming')
        self.do_run = True

        while self.do_run:
            num_pending_transactions = int(self.web3.txpool.status.pending, 16)
            desired_pending_txs = self.manager.desired_pending_txs()
            num_queued_transactions = len(self.manager.tx_queue)
            desired_queued_txs = self.manager.desired_queued_txs()
            remaining_blocks = self.manager.remaining_blocks()

            if (self.manager.target_block is not None) & (not self.is_target_block_reached()):
                self.logger.debug(
                    'Current block = {} / Target block = {}'.format(self.web3.eth.blockNumber, self.manager.target_block))
                self.logger.info('Pending transactions = {} / Desired Pending = {} / Queued transactions = {} / Desired queued = {} / Threads = {} / Remaining blocks = {}'.format(
                    num_pending_transactions, desired_pending_txs, num_queued_transactions, desired_queued_txs, active_count(), remaining_blocks))
            else:
                self.logger.debug('Current block = {}'.format(self.web3.eth.blockNumber))
                self.logger.info('Pending transactions = {} / Desired Pending = {} / Queued transactions = {} / Threads = {}'.format(
                    num_pending_transactions, desired_pending_txs, num_queued_transactions, active_count()))

            time.sleep(3)
    
    def spam_tx(self, num_tx):
        '''
        Spam the network with the given number of transactions at once.
        '''        
        # Create trigger transaction.
        nonce = self.manager.reserve_nonce()
        trigger_tx = create_signed_transaction(
            network_id=self.network_id,
            private_key=self.private_key,
            to=self.account_address,
            nonce=nonce,
            data=str(time.time()),
        )

        self.sending_continue()

        self.logger.info(
            'Spamming the network with {} transactions...'
            .format(num_tx)
        )
        self.manager.wait_num_transactions_sent(num_tx)

        self.sending_pause()

        # Send trigger transaction
        self.web3.eth.sendRawTransaction(trigger_tx)

    def stop(self):
        '''
        Stop the execution of this and all spam worker threads.
        '''
        self.do_run = False
        for thread in self.threads:
            thread.stop()
        self.logger.info('Stopped network spamming')

    def sending_pause(self):
        '''
        Stop to broadcast transactions.
        '''
        for thread in self.threads:
            thread.do_send = False
        self.logger.info('Pause spamming.')

    def sending_continue(self):
        '''
        Start to broadcast transactions.
        '''
        for thread in self.threads:
            thread.do_send = True
        self.logger.info('Start spamming.')

    def is_target_block_reached(self) -> bool:
        '''
        Returns True if the target block number has already been created.
        '''
        if self.manager.target_block is None:
            return False
        return self.web3.eth.blockNumber >= self.manager.target_block

    def update_target_block(self, target_block):
        '''
        Update the block until which the network should be spammed.
        '''
        self.manager.target_block = target_block
