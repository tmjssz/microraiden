from microraiden import HTTPHeaders
from microraiden.client.channel import Channel
from microraiden.utils import (
    get_event_blocking,
    create_signed_transaction,
    create_signed_contract_transaction,
)
from eth_utils import encode_hex
from munch import Munch
from web3 import Web3
import config as config
import gevent, requests, logging

log = logging.getLogger('channel_utils')

def send_payment(channel, amount: int=0):
    '''
    Send an off-chain payment of the given amount through the given channel.
    '''
    headers = Munch()
    headers.balance = str(channel.balance)
    headers.balance_signature = encode_hex(channel.balance_sig)
    headers.sender_address = channel.sender
    headers.open_block = str(channel.block)
    headers = HTTPHeaders.serialize(headers)
    response = requests.get(config.PROXY_URL + str(amount), headers=headers)
    if response.status_code != 200:
        log.error(
            'Payment failed.\n'
            'Response headers: {}'
            .format(response.headers)
        )
    else:
        log.info('Successfull payment of {}'.format(amount))

def create_close_channel_transaction(channel, balance=None):
    '''
    Create an uncooperative channel close transaction with the given balance.
    '''
    if channel.state != Channel.State.open:
        log.error('Channel must be open to request a close.')
        return
    log.info('Creating close transaction for channel to {} created at block #{}.'.format(
        channel.receiver, channel.block
    ))

    if balance is not None:
        channel.update_balance(balance)

    return create_signed_contract_transaction(
        channel.core.private_key,
        channel.core.channel_manager,
        'uncooperativeClose',
        [
            channel.receiver,
            channel.block,
            channel.balance
        ]
    )

def create_spam_transactions(private_key: str, web3: Web3 = None, account_address: str = '', number: int = 100, nonce_offset: int = 0):
    '''
    Create the given {number} of spam transactions from the account with the given {private_key} to the given {account_address}.
    '''
    log.info('Creating {} transactions...'.format(number))
    transactions = list()
    print(private_key)
    for x in range(number):
        tx = create_signed_transaction(private_key=private_key, web3=web3, to=account_address, nonce_offset=x+nonce_offset, value=x, gas_price=config.GAS_PRICE, gas_limit=config.GAS_LIMIT)
        transactions.append(tx)
    return transactions

def wait_for_blocks(web3, n: int=0):
    '''
    Wait for {n} blocks to be mined.
    '''
    target_block = web3.eth.blockNumber + n
    while web3.eth.blockNumber < target_block:
        gevent.sleep(2)

def wait_for_open(channel, confirmations: int=0):
    '''
    Wait for an OPEN event for the given channel with the given number of block {confirmations}.
    '''
    log.debug('Waiting for channel creation event on the blockchain...')
    opened_event = get_event_blocking(
        channel.core.channel_manager,
        'ChannelCreated',
        from_block=channel.block,
        timeout=config.WAIT_TIMEOUT,
        to_block='latest',
        argument_filters={
            '_sender_address': channel.core.address,
            '_receiver_address': channel.receiver
        }
    )

    if (confirmations > 0):
        current_block = channel.core.web3.eth.blockNumber
        if (current_block - opened_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_blocks(channel.core.web3, confirmations)

def wait_for_close(channel):
    '''
    Wait for a CLOSE event for the given channel.
    '''
    current_block = channel.core.web3.eth.blockNumber
    log.info('Waiting for close confirmation event...')
    return get_event_blocking(
        channel.core.channel_manager,
        'ChannelCloseRequested',
        from_block=current_block + 1,
        timeout=config.WAIT_TIMEOUT,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )

def wait_for_settle(channel):
    '''
    Wait for a SETTLE event for the given channel.
    '''
    current_block = channel.core.web3.eth.blockNumber
    log.info('Waiting for settle confirmation event...')
    return get_event_blocking(
        channel.core.channel_manager,
        'ChannelSettled',
        from_block=current_block + 1,
        timeout=config.WAIT_TIMEOUT,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )
