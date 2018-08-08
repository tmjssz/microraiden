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
from microraiden import HTTPHeaders
from microraiden.client.channel import Channel
from microraiden.utils import (
    privkey_to_addr,
    sign_transaction,
    get_event_blocking,
)

log = logging.getLogger('channel_utils')

min_free_gas = 130000


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


def get_valid_headers(web3, num):
    block_headers = []
    offset = 0

    while len(block_headers) < num:
        offset += 1
        block_number = web3.eth.blockNumber - offset
        if (block_number <= 0):
            break

        # Get the block.
        block = web3.eth.getBlock(block_number)

        # Check if block is congested.
        gasFree = block.gasLimit - block.gasUsed
        if gasFree < min_free_gas:
            continue

        header = get_block_header(block)
        block_headers.append(header)

    return block_headers


def get_congested_headers(web3, num):
    block_headers = []
    offset = 0

    while len(block_headers) < num:
        offset += 1
        block_number = web3.eth.blockNumber - offset
        if (block_number <= 0):
            break

        # Get the block.
        block = web3.eth.getBlock(block_number)

        # Check if block is congested.
        gasFree = block.gasLimit - block.gasUsed
        if gasFree >= min_free_gas:
            continue

        header = get_block_header(block)
        block_headers.append(header)

    return block_headers


def get_block_header(block):
    '''
    Returns a list containing all data from the given block's header.
    '''
    return [
        block.parentHash,
        block.sha3Uncles,
        decode_hex(block.miner[2:]),
        block.stateRoot,
        block.transactionsRoot,
        block.receiptsRoot,
        block.logsBloom,
        block.difficulty,
        block.number,
        block.gasLimit,
        block.gasUsed,
        block.timestamp,
        block.extraData,
        block.mixHash,
        int(block.nonce.hex(), 16)
    ]
