#!/usr/bin/python

import time
from web3 import Web3
from collections import deque


class SpamManager():
    '''
    The SpamManager class coordinates the correct generation of spam transactions.
    '''

    def __init__(
        self,
        web3: Web3,
        initial_nonce: int=0,
        target_block: int=None,
        block_size: int=220,
        max_tx_queue_size: int=10000,
    ):
        self.web3 = web3
        self.initial_nonce = initial_nonce
        self.target_block = target_block
        self.block_size = block_size
        self.max_tx_queue_size = max_tx_queue_size

        # Initialize transaction counter.
        self.tx_counter = 0

        # Initialize queue for waiting transactions.
        self.tx_queue = deque()
        self.tx_sent_counter = 0

    def reserve_nonce(self) -> int:
        '''
        Return the next nonce and increase the transaction counter.
        '''
        self.tx_counter += 1
        return self.initial_nonce + self.tx_counter - 1

    def enqueue_transaction(self, tx: str):
        '''
        Append the given transaction to the end of the queue.
        '''
        self.tx_queue.append(tx)

    def next_transaction(self) -> str:
        '''
        Returns the next transaction from the queue.
        '''
        if self.tx_queue:
            self.tx_sent_counter += 1
            return self.tx_queue.popleft()
        return None

    def remaining_blocks(self) -> int:
        '''
        Return the number of blocks until the target block.
        '''
        if self.target_block is None:
            return None
        return max(0, self.target_block - self.web3.eth.blockNumber)

    def desired_pending_txs(self) -> int:
        '''
        Returns the number of desired pending transactions.
        '''
        if self.remaining_blocks() is None:
            return 500 * self.block_size
        return self.remaining_blocks() * self.block_size

    def desired_queued_txs(self) -> int:
        '''
        Returns the number of desired queued transactions.
        '''
        num_pending_transactions = int(self.web3.txpool.status.pending, 16)
        return max(0, min(self.desired_pending_txs() - num_pending_transactions, self.max_tx_queue_size))

    def wait_for_full_tx_queue(self, num_transactions: int=None):
        '''
        Wait until the queue of transactions to be sent next
        has reached the minimum number of transactions.
        '''
        target_size = num_transactions
        if target_size is None:
            target_size = self.desired_queued_txs()

        while len(self.tx_queue) < target_size:
            time.sleep(1)

    def wait_for_empty_tx_queue(self):
        '''
        Wait until the queue of transactions to be sent next is empty.
        '''
        while len(self.tx_queue) > 0:
            time.sleep(1)

    def wait_num_transactions_sent(self, num_transactions):
        '''
        Wait until the given number of transactions has been broadcasted.
        '''
        while self.tx_counter < num_transactions:
            time.sleep(1)

    def is_tx_queue_full(self) -> bool:
        '''
        Returns true if the transaction queue has the desired length.
        '''
        desired_tx_queue_size = self.desired_queued_txs()
        return len(self.tx_queue) >= desired_tx_queue_size
