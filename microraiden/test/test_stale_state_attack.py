import logging
from eth_utils import encode_hex
from web3 import Web3
from microraiden import Client
from microraiden.client import Channel
from microraiden.utils import get_logs
from microraiden.channel_manager import ChannelManager
from microraiden.test.utils.spamming import Spammer
import gevent
import pytest

log = logging.getLogger(__name__)

min_free_gas = 130000

GREEN = '\033[92m'
RED = '\033[91m'
COLOR_END = '\033[0m'


@pytest.fixture
def confirmed_open_channel(
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


def get_settled_event(channel, from_block):
    logs = get_logs(
        channel.core.channel_manager,
        'ChannelSettled',
        from_block=from_block,
        to_block='latest',
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': channel.receiver,
            '_open_block_number': channel.block
        }
    )

    if len(logs) > 0:
        return logs[0]

    return None


def test_close_with_stale_state_during_congestion(
        channel_manager: ChannelManager,
        client: Client,
        confirmed_open_channel: Channel,
        spammer: Spammer,
        sender_address: str,
        use_tester: bool,
        wait_for_blocks,
        web3: Web3
):
    # if not use_tester:
    #     pytest.skip('This test takes several hours on real blockchains.')

    blockchain = channel_manager.blockchain
    channel_id = (confirmed_open_channel.sender, confirmed_open_channel.block)

    # Make an off-chain payment.
    sig = encode_hex(confirmed_open_channel.create_transfer(5))
    channel_manager.register_payment(confirmed_open_channel.sender,
                                     confirmed_open_channel.block, 5, sig)

    receivers_channel = channel_manager.channels[channel_id]
    assert receivers_channel.balance == 5

    # Set cheat balance.
    confirmed_open_channel.update_balance(0)

    # Close the channel uncooperatively with wrong balance.
    close_event = confirmed_open_channel.close()
    close_tx = web3.eth.getTransaction(close_event['transactionHash'])
    log.info('Sent close transaction (tx={})'.format(close_tx['hash'].hex()))

    # Start spamming.
    first_txn = spammer.get_transaction(0)
    web3.eth.sendRawTransaction(first_txn)
    log.info('Sent very first spam transaction')

    # Get the block number from which the channel can be settled.
    _, _, settle_block, _, _ = channel_manager.channel_manager_contract.call().getChannelInfo(
        confirmed_open_channel.sender, confirmed_open_channel.receiver, confirmed_open_channel.block
    )
    log.info('Settle block: #{}'.format(settle_block))

    block_filter = web3.eth.filter('latest')

    # Wait until (a) the challenge period is over or (b) the channel is settled.
    start_block = web3.eth.blockNumber
    while web3.eth.blockNumber < settle_block:
        settled_event = get_settled_event(confirmed_open_channel, start_block)
        if settled_event is not None:
            log.info('Channel settled at block #{}'.format(settled_event['blockNumber']))
            spammer.stop()
            break

        for event in block_filter.get_new_entries():
            block = web3.eth.getBlock(event.hex())
            num_tx = len(block['transactions'])
            gas_free = block['gasLimit'] - block['gasUsed']

            output = '#{} \t {} \t {} \t {}%'.format(
                block['number'], num_tx, gas_free, round(100 * gas_free / block['gasLimit']))

            if gas_free < min_free_gas:
                log.info('{}{}{}'.format(RED, output, COLOR_END))
            else:
                log.info('{}{}{}'.format(GREEN, output, COLOR_END))
        wait_for_blocks(1)
