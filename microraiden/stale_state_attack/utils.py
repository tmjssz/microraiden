#!/usr/bin/python

import gevent
import requests
import logging
import time
import rlp
from ethereum.transactions import Transaction
from eth_utils import decode_hex, encode_hex
from munch import Munch
from urllib3.exceptions import HTTPError
from web3 import Web3
from web3.contract import Contract
from typing import List, Any
from microraiden import HTTPHeaders
from microraiden.client.channel import Channel
from microraiden.utils import (
    privkey_to_addr,
    sign_transaction,
    get_event_blocking,
    create_transaction_data,
)

log = logging.getLogger('channel_utils')


def send_offchain_payment(channel, resource_url: str):
    '''
    Send an off-chain payment through the given channel by sending a request 
    to the given fee-based resource_url of the proxy.
    '''
    headers = Munch()
    headers.balance = str(channel.balance)
    headers.balance_signature = encode_hex(channel.balance_sig)
    headers.sender_address = channel.sender
    headers.open_block = str(channel.block)
    headers = HTTPHeaders.serialize(headers)

    response = requests.get(resource_url, headers=headers)

    if response.status_code != 200:
        raise HTTPError(response.status_code, response.headers)


def create_signed_transaction(
        web3: Web3,
        private_key: str,
        to: str,
        data: bytes=b'',
        gas_limit: int=130000,
        gas_price: int=20000000000,
        nonce: int=None,
        value: int=0,
) -> str:
    """
    Creates a signed on-chain transaction compliant with EIP155.
    """
    from_ = privkey_to_addr(private_key)

    if nonce is None:
        nonce = web3.eth.getTransactionCount(from_, 'pending')

    tx = Transaction(nonce, gas_price, gas_limit, to, value, data)
    tx.sender = decode_hex(from_)

    network_id = int(web3.version.network)
    sign_transaction(tx, private_key, network_id)
    return encode_hex(rlp.encode(tx))


def create_signed_contract_transaction(
        args: List[Any],
        contract: Contract,
        func_name: str,
        private_key: str,
        nonce: int=None,
) -> str:
    """
    Creates a signed on-chain contract transaction compliant with EIP155.
    """
    data = create_transaction_data(contract, func_name, args)
    return create_signed_transaction(
        web3=contract.web3,
        private_key=private_key,
        to=contract.address,
        data=data,
        gas_limit=130000,
        gas_price=30000000000,
        nonce=nonce,
    )


def create_close_channel_transaction(channel, balance=None):
    '''
    Create an uncooperative channel close transaction with the given balance.
    '''
    if channel.state != Channel.State.open:
        log.error('Channel must be open to request a close.')
        return
    log.info(
        'Creating close transaction for channel to {} created at block #{}.'
        .format(channel.receiver, channel.block)
    )

    if balance is not None:
        channel.update_balance(balance)

    return create_signed_contract_transaction(
        args=[
            channel.receiver,
            channel.block,
            channel.balance
        ],
        contract=channel.core.channel_manager,
        func_name='uncooperativeClose',
        private_key=channel.core.private_key,
    )


def create_settle_channel_transaction(channel):
    '''
    Create an settle channel close transaction.
    '''
    if channel.state != Channel.State.settling:
        log.error('Channel must be in the settlement period to settle.')
        return None
    log.info(
        'Creating settle transaction for channel to {} created at block #{}.'
        .format(channel.receiver, channel.block)
    )

    return create_signed_contract_transaction(
        args=[
            channel.receiver,
            channel.block
        ],
        contract=channel.core.channel_manager,
        func_name='settle',
        private_key=channel.core.private_key,
    )


def wait_for_open(channel, confirmations: int=0):
    '''
    Wait for an OPEN event for the given channel with the given number of block {confirmations}.
    '''
    web3 = channel.core.web3
    log.debug('Waiting for channel creation event on the blockchain...')
    opened_event = get_event_blocking(
        channel.core.channel_manager,
        'ChannelCreated',
        from_block=channel.block,
        timeout=36000,
        to_block='latest',
        argument_filters={
            '_sender_address': channel.core.address,
            '_receiver_address': channel.receiver
        }
    )

    if (confirmations > 0):
        current_block = web3.eth.blockNumber
        if (current_block - opened_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_block_generation(web3, current_block + confirmations)

    return opened_event


def wait_for_close(channel, confirmations: int=0):
    '''
    Wait for a CLOSE event for the given channel.
    '''
    web3 = channel.core.web3
    current_block = web3.eth.blockNumber
    log.info('Waiting for close confirmation event...')
    closed_event = get_event_blocking(
        channel.core.channel_manager,
        'ChannelCloseRequested',
        from_block=current_block + 1,
        timeout=36000,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )

    if (confirmations > 0):
        current_block = web3.eth.blockNumber
        if (current_block - closed_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_block_generation(web3, current_block + confirmations)

    channel.state = Channel.State.settling
    return closed_event


def wait_for_settle(channel, confirmations: int=0):
    '''
    Wait for a SETTLE event for the given channel.
    '''
    web3 = channel.core.web3
    current_block = web3.eth.blockNumber
    log.info('Waiting for settle confirmation event...')
    settled_event = get_event_blocking(
        channel.core.channel_manager,
        'ChannelSettled',
        from_block=current_block + 1,
        timeout=36000,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )

    if (confirmations > 0):
        current_block = web3.eth.blockNumber
        if (current_block - settled_event['blockNumber'] < confirmations):
            log.debug('Waiting for {} confirmations...'.format(confirmations))
            wait_for_block_generation(web3, current_block + confirmations)

    return settled_event


def wait_for_block_generation(web3, block_number):
    '''
    Wait until the block with the given number is generated.
    '''
    if block_number <= web3.eth.blockNumber:
        # The given block number lies in the past.
        return

    block_filter = web3.eth.filter('latest')
    while True:
        for event in block_filter.get_new_entries():
            if web3.eth.blockNumber >= block_number:
                # The given block number was generated.
                return
        time.sleep(2)
