#!/usr/bin/python

import threading
import time
import logging
import config as config
from microraiden.utils import privkey_to_addr
from utils import create_signed_transaction

class SpamManager(threading.Thread):
    def __init__(
        self,
        web3,
        private_key: str=config.PRIVATE_KEY,
        number_threads: int=1,
        nonce_offset: int=0,
        min_pending_txs: int=config.MIN_PENDING_TXS,
        callback = None,
    ):
        self.web3 = web3
        self.private_key = private_key
        self.number_threads = number_threads
        self.nonce_offset = nonce_offset
        self.min_pending_txs = min_pending_txs
        self.callback = callback

        self.logger = logging.getLogger('spamming')
        self.threads = []

        threading.Thread.__init__(self)

    def run(self):
        global tx_counter

        tx_counter = 0
        initial_nonce = self.web3.eth.getTransactionCount(privkey_to_addr(self.private_key), 'pending') + self.nonce_offset
        self.target_block = None
        self.do_run = True

        # Start Threads
        for i in range(self.number_threads):
            thread = SpamThread(
                web3=self.web3,
                thread_id=i,
                private_key=self.private_key,
                initial_nonce=initial_nonce,
                min_pending_txs=self.min_pending_txs,
            )
            self.threads.append(thread)
            thread.start()
        
        while (self.do_run == True) & (self.target_block_reached() == False):
            if self.target_block is not None:
                self.logger.debug('Current block = {} / Target block = {}'.format(self.web3.eth.blockNumber, self.target_block))
                self.logger.info('Pending transactions = {} / Target block = {} / Remaining blocks = {}'.format(int(self.web3.txpool.status.pending, 16), self.target_block, self.target_block - self.web3.eth.blockNumber))
            else:
                self.logger.debug('Current block = {}'.format(self.web3.eth.blockNumber))
                self.logger.info('Pending transactions = {}'.format(int(self.web3.txpool.status.pending, 16)))
            time.sleep(10)
        
        if self.do_run:
            self.callback(initial_nonce + tx_counter)

    def update_target_block(self, block):
        self.target_block = block
        for thread in self.threads:
            thread.update_target_block(block)

    def target_block_reached(self) -> bool:
        if self.target_block is None:
            return False
        return self.web3.eth.blockNumber >= self.target_block

    def stop(self):
        self.do_run = False
        for thread in self.threads:
            thread.stop()
        self.logger.info('Stopped network spamming')


class SpamThread(threading.Thread):
    def __init__(
        self,
        web3,
        thread_id: int = 0,
        private_key: str = config.PRIVATE_KEY,
        initial_nonce: int = 0,
        min_pending_txs: int = config.MIN_PENDING_TXS,
    ):
        self.web3 = web3
        self.thread_id = thread_id
        self.private_key = private_key
        self.account_address = privkey_to_addr(private_key)
        self.initial_nonce = initial_nonce
        self.min_pending_txs = min_pending_txs

        self.logger = logging.getLogger('spammer-{}'.format(thread_id))

        threading.Thread.__init__(self)
    
    def create_transaction(self, nonce):
        return create_signed_transaction(
            private_key=self.private_key,
            web3=self.web3, 
            to=self.account_address,
            nonce=nonce,
            data=str(time.time()),
            gas_price=config.GAS_PRICE,
            gas_limit=config.GAS_LIMIT
        )
    
    def run(self):
        global tx_counter

        self.do_run = True
        self.target_block = None

        while (self.do_run == True) & (self.target_block_reached() == False):
            if int(self.web3.txpool.status.pending, 16) < self.min_pending_txs:
                tx_counter += 1
                nonce = self.initial_nonce + tx_counter - 1
                tx = self.create_transaction(nonce)
                self.web3.eth.sendRawTransaction(tx)
    
    def target_block_reached(self) -> bool:
        if self.target_block is None:
            return False
        return self.web3.eth.blockNumber >= self.target_block
    
    def update_target_block(self, block):
        self.target_block = block
    
    def stop(self):
        self.do_run = False
