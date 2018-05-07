#!/usr/bin/python

from microraiden import HTTPHeaders
from microraiden.client.channel import Channel
from microraiden.utils import (
    privkey_to_addr,
    sign_transaction,
    get_event_blocking,
    create_transaction_data,
    # create_signed_transaction,
    # create_signed_contract_transaction,
)
from ethereum.transactions import Transaction
from eth_utils import decode_hex, encode_hex
from munch import Munch
from web3 import Web3
from web3.contract import Contract
from typing import Union, List, Any
import config as config
import gevent, requests, logging, time, rlp

log = logging.getLogger('channel_utils')

def create_signed_transaction(
        private_key: str,
        web3: Web3,
        to: str,
        value: int=0,
        data=b'',
        nonce: int = None,
        gas_price: Union[int, None] = None,
        gas_limit: int = config.GAS_LIMIT
) -> str:
    """
    Creates a signed on-chain transaction compliant with EIP155.
    """
    from_ = privkey_to_addr(private_key)

    if nonce is None:
        nonce = web3.eth.getTransactionCount(from_, 'pending')
    
    if gas_price is None:
        gas_price = config.GAS_PRICE

    tx = Transaction(nonce, gas_price, gas_limit, to, value, data)
    tx.sender = decode_hex(from_)

    sign_transaction(tx, private_key, int(web3.version.network))
    return encode_hex(rlp.encode(tx))

def create_signed_contract_transaction(
        private_key: str,
        contract: Contract,
        func_name: str,
        args: List[Any],
        value: int=0,
        nonce: int=None,
        gas_price: Union[int, None] = None,
        gas_limit: int = config.GAS_LIMIT
) -> str:
    """
    Creates a signed on-chain contract transaction compliant with EIP155.
    """
    from_ = privkey_to_addr(private_key)

    if nonce is None:
        nonce = contract.web3.eth.getTransactionCount(from_, 'pending')

    if gas_price is None:
        gas_price = config.GAS_PRICE
    
    data = create_transaction_data(contract, func_name, args)

    tx = Transaction(nonce, gas_price, gas_limit, contract.address, value, data)
    tx.sender = decode_hex(from_)

    sign_transaction(tx, private_key, int(contract.web3.version.network))
    return encode_hex(rlp.encode(tx))

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
        private_key=channel.core.private_key,
        contract=channel.core.channel_manager,
        func_name='uncooperativeClose',
        args=[
            channel.receiver,
            channel.block,
            channel.balance
        ],
        value=0,
        nonce=None,
        gas_price=config.GAS_PRICE,
        gas_limit=config.GAS_LIMIT,
    )

def create_settle_channel_transaction(channel, nonce=None):
    '''
    Create an settle channel close transaction.
    '''
    if channel.state != Channel.State.settling:
        log.error('Channel must be in the settlement period to settle.')
        return None
    log.info('Creating settle transaction for channel to {} created at block #{}.'.format(
        channel.receiver, channel.block
    ))
    
    return create_signed_contract_transaction(
        private_key=channel.core.private_key,
        contract=channel.core.channel_manager,
        func_name='settle',
        args=[
            channel.receiver,
            channel.block
        ],
        value=0,
        nonce=nonce,
        gas_price=config.GAS_PRICE,
        gas_limit=config.GAS_LIMIT,
    )

def create_spam_transactions(private_key: str, web3: Web3 = None, account_address: str = '', number: int = 100, min_nonce: int = None):
    '''
    Create the given {number} of spam transactions from the account with the given {private_key} to the given {account_address}.
    '''
    log.debug('Creating {} transactions...'.format(number))
    transactions = list()
    
    if min_nonce is None:
        min_nonce = web3.eth.getTransactionCount(privkey_to_addr(private_key), 'pending')
        
    for x in range(number):
        tx = create_signed_transaction(
            private_key=private_key,
            web3=web3, 
            to=account_address,
            nonce=min_nonce+x,
            data=str(time.time()),
            gas_price=config.GAS_PRICE,
            gas_limit=config.GAS_LIMIT
        )
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
    
    return opened_event

def wait_for_close(channel, confirmations: int=0):
    '''
    Wait for a CLOSE event for the given channel.
    '''
    current_block = channel.core.web3.eth.blockNumber
    log.info('Waiting for close confirmation event...')
    closed_event = get_event_blocking(
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

    if (confirmations > 0):
        current_block = channel.core.web3.eth.blockNumber
        if (current_block - closed_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_blocks(channel.core.web3, confirmations)
    
    channel.state = Channel.State.settling
    return closed_event

def wait_for_settle(channel, confirmations: int=0):
    '''
    Wait for a SETTLE event for the given channel.
    '''
    current_block = channel.core.web3.eth.blockNumber
    log.info('Waiting for settle confirmation event...')
    settled_event = get_event_blocking(
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

    if (confirmations > 0):
        current_block = channel.core.web3.eth.blockNumber
        if (current_block - settled_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_blocks(channel.core.web3, confirmations)

    return settled_event
