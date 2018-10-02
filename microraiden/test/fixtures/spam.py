import logging
import os
import gevent
import pytest
from web3 import Web3
from eth_utils import decode_hex, encode_hex, remove_0x_prefix, big_endian_to_int
from ethereum.blocks import BlockHeader
from microraiden.channel_manager import ChannelManager
from microraiden.client import Channel
from microraiden import Client
from microraiden.test.utils.spam import Spammer
from microraiden import constants
from microraiden.utils import get_logs

log = logging.getLogger(__name__)


def get_channel_event(channel, name, from_block, to_block):
    logs = get_logs(
        channel.core.channel_manager,
        name,
        from_block=from_block,
        to_block=to_block,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )

    return logs[0] if logs else None


@pytest.fixture(scope='session')
def min_free_gas() -> int:
    return 130000


@pytest.fixture(scope='session')
def spammer(web3: Web3) -> Spammer:
    input_file = os.path.join(
        constants.MICRORAIDEN_DIR,
        'microraiden',
        'test',
        'data',
        'spam.txt',
    )

    spam = Spammer(
        web3=web3,
        input_file=input_file,
        offset=1,
    )
    spam.start()

    return spam


@pytest.fixture
def open_channel(
        channel_manager: ChannelManager,
        client: Client,
        receiver_address: str,
        wait_for_blocks
):
    channel = client.open_channel(receiver_address, 10)
    wait_for_blocks(channel_manager.n_confirmations + 1)
    gevent.sleep(channel_manager.blockchain.poll_interval)
    assert (channel.sender, channel.block) in channel_manager.channels

    return channel


@pytest.fixture
def channel_payed(
        channel_manager: ChannelManager,
        open_channel: Channel,
):
    channel_id = (open_channel.sender, open_channel.block)

    # Make an off-chain payment through the opened channel.
    sig = encode_hex(open_channel.create_transfer(5))
    channel_manager.register_payment(
        open_channel.sender,
        open_channel.block,
        5,
        sig,
    )

    # Make sure that that the payment was successfull.
    receivers_channel = channel_manager.channels[channel_id]
    assert receivers_channel.balance == 5

    return open_channel


@pytest.fixture
def wait_for_settled_channel(web3: Web3, wait_for_blocks):
    def _wait_for_settled_channel(channel: Channel, from_block: int):
        settled_event = None
        while settled_event is None:
            settled_event = get_channel_event(channel, 'ChannelSettled', from_block, 'latest')
            wait_for_blocks(1)

        # Return the settle transaction.
        return web3.eth.getTransaction(settled_event['transactionHash'])
    return _wait_for_settled_channel


@pytest.fixture(scope='session')
def valid_headers(web3: Web3, min_free_gas: int):
    def _valid_headers(num: int):
        block_headers = []
        offset = 1

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

            block_headers.append(BlockHeader(
                prevhash=block.parentHash,
                uncles_hash=block.sha3Uncles,
                coinbase=decode_hex(remove_0x_prefix(block.miner)),
                state_root=block.stateRoot,
                tx_list_root=block.transactionsRoot,
                receipts_root=block.receiptsRoot,
                bloom=big_endian_to_int(block.logsBloom),
                difficulty=block.difficulty,
                number=block.number,
                gas_limit=block.gasLimit,
                gas_used=block.gasUsed,
                timestamp=block.timestamp,
                extra_data=block.extraData,
                mixhash=block.mixHash,
                nonce=block.nonce,
            ))

        return block_headers

    return _valid_headers


@pytest.fixture(scope='session')
def invalid_headers(web3: Web3):
    def _invalid_headers(num: int):
        block_headers = []
        offset = 0

        while len(block_headers) < num:
            offset += 1
            block_number = web3.eth.blockNumber - offset
            if (block_number <= 0):
                break

            # Get the block.
            block = web3.eth.getBlock(block_number)

            block_headers.append(BlockHeader(
                prevhash=block.parentHash,
                uncles_hash=block.sha3Uncles,
                coinbase=decode_hex(remove_0x_prefix(block.miner)),
                state_root=block.stateRoot,
                tx_list_root=block.transactionsRoot,
                receipts_root=block.receiptsRoot,
                bloom=big_endian_to_int(block.logsBloom),
                difficulty=block.difficulty,
                number=block.number,
                gas_limit=block.gasLimit,
                gas_used=100,
                timestamp=block.timestamp,
                extra_data=block.extraData,
                mixhash=block.mixHash,
                nonce=block.nonce,
            ))

        return block_headers

    return _invalid_headers
