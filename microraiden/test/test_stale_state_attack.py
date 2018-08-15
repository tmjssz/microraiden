import datetime
import gevent
import logging
import pytest
from eth_utils import encode_hex, is_same_address
from microraiden import Client
from microraiden.channel_manager import ChannelManager
from microraiden.client import Channel
from microraiden.test.utils.spam import Spammer
from microraiden.utils import get_logs
from web3 import Web3

log = logging.getLogger(__name__)

GREEN = '\033[92m'
RED = '\033[91m'
COLOR_END = '\033[0m'


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

    if logs:
        return logs[0]

    return None


def test_close_with_stale_state_during_congestion(
        channel_manager: ChannelManager,
        open_channel: Channel,
        min_free_gas: int,
        spammer: Spammer,
        use_tester: bool,
        wait_for_blocks,
        web3: Web3
):
    # if not use_tester:
    #     pytest.skip('This test takes several hours on real blockchains.')

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

    # Set cheat balance.
    open_channel.update_balance(0)

    # Close the channel uncooperatively with cheat balance.
    close_event = open_channel.close()
    close_tx = web3.eth.getTransaction(close_event['transactionHash'])
    log.info('Sent close transaction (tx=%s)', close_tx['hash'].hex())

    # Start spamming by sending the very first spam transaction.
    # This makes all until now sent spam transactions that were queued by the miners
    # (because of their too high nonce) appear as 'pending' in the network at once.
    first_txn = spammer.get_transaction(0)
    web3.eth.sendRawTransaction(first_txn)
    log.info('Sent very first spam transaction')

    # Get the block number from which the channel can be settled.
    _, _, settle_block, _, _ = channel_manager.channel_manager_contract.call().getChannelInfo(
        open_channel.sender, open_channel.receiver, open_channel.block
    )
    log.info('Sender can settle the channel at block #%s', settle_block)

    # Wait until (a) the challenge period is over or (b) the channel is settled.
    block_filter = web3.eth.filter('latest')
    start_block = web3.eth.blockNumber
    settled_event = None
    while web3.eth.blockNumber < settle_block:
        settled_event = get_channel_event(
            open_channel, 'ChannelSettled', start_block, 'latest')
        if settled_event is not None:
            # Settle event was received -> stop waiting.
            break

        # Get the last created block.
        for event in block_filter.get_new_entries():
            block = web3.eth.getBlock(event.hex())
            num_tx = len(block['transactions'])
            gas_free = block['gasLimit'] - block['gasUsed']
            gas_free_percentage = round(100 * gas_free / block['gasLimit'])
            is_congested = gas_free < min_free_gas

            # Log some info about the block.
            log.info(
                '%s#%s\t%s\t%s\t\t%s %%%s',
                RED if is_congested else GREEN,
                block['number'],
                num_tx,
                gas_free,
                gas_free_percentage,
                COLOR_END
            )

            if not is_congested:
                log.warning('Uncongested block #%s created (%s transactions, %s %% free gas)',
                            block['number'], num_tx, gas_free_percentage)

        wait_for_blocks(1)

    # Check if the challenge period is over.
    if web3.eth.blockNumber >= settle_block:
        log.info('Settle block #%s is reached', settle_block)

    # Wait for the settle event again.
    while settled_event is None:
        settled_event = get_channel_event(
            open_channel, 'ChannelSettled', start_block, 'latest')
        wait_for_blocks(1)

    # Get the settle transaction.
    settle_tx = web3.eth.getTransaction(settled_event['transactionHash'])

    # Get address of account that settled the channel.
    settled_by_addr = settle_tx['from']
    is_settled_by_receiver = is_same_address(settled_by_addr, open_channel.receiver)

    # Determine which party settled the channel.
    settled_by = 'receiver' if is_settled_by_receiver else 'sender'
    log.info('Channel has been settled by %s at block #%s',
             settled_by, settled_event['blockNumber'])

    # Get the block containing the close transaction.
    close_block = web3.eth.getBlock(close_event['blockNumber'])

    # Get the block containing the settle transaction.
    settle_block = web3.eth.getBlock(settled_event['blockNumber'])

    # Calculate the elapsed time between close and settle.
    if (close_block is not None) & (settle_block is not None):
        elapsed_time = datetime.timedelta(
            seconds=settle_block['timestamp'] - close_block['timestamp']
        )
        log.info('Elapsed time between close and settle -> %s', str(elapsed_time))

    # assert not is_settled_by_receiver, 'channel was settled by sender'
    assert is_settled_by_receiver, 'channel was settled by receiver'

    # Stop spamming.
    spammer.stop()
