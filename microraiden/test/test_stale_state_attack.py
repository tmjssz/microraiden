import datetime
import logging
import pytest
import rlp
from eth_utils import encode_hex, is_same_address, decode_hex, big_endian_to_int
from microraiden.channel_manager import ChannelManager
from microraiden.client import Channel
from microraiden.test.utils.spam import Spammer
from microraiden.utils import get_logs, create_signed_contract_transaction
from web3 import Web3

log = logging.getLogger(__name__)

GREEN = '\033[92m'
RED = '\033[91m'
COLOR_END = '\033[0m'


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


# @pytest.mark.skip(reason="no way of currently testing this")
def test_close_with_stale_state_during_congestion(
        channel_manager: ChannelManager,
        channel_payed: Channel,
        min_free_gas: int,
        spammer: Spammer,
        use_tester: bool,
        invalid_headers,
        valid_headers,
        wait_for_blocks,
        wait_for_settled_channel,
        web3: Web3
):
    # Set cheat balance.
    channel_payed.update_balance(0)

    # Close the channel uncooperatively with cheat balance.
    close_event = channel_payed.close()
    close_tx = web3.eth.getTransaction(close_event['transactionHash'])
    log.info('Sent close transaction (tx=%s)', close_tx['hash'].hex())

    # Start spamming by sending the very first spam transaction.
    # This makes all until now sent spam transactions that were queued by the miners
    # (because of their too high nonce) appear as 'pending' in the network at once.
    first_txn = spammer.get_transaction(0)
    web3.eth.sendRawTransaction(first_txn)
    log.info('Sent very first spam transaction')

    # Get the block number from which the channel can be settled.
    _, _, settle_block, _, _ = channel_payed.core.channel_manager.call().getChannelInfo(
        channel_payed.sender, channel_payed.receiver, channel_payed.block
    )
    log.info('Sender can settle the channel at block #%s', settle_block)

    log.info('Number\t#Tx\tGasUsed\tGasLimit\tGasFree\t+GasLimit')
    prevGasLimit = None

    # Wait until (a) the challenge period is over or (b) the channel is settled.
    block_filter = web3.eth.filter('latest')
    start_block = web3.eth.blockNumber
    settled_event = None
    while web3.eth.blockNumber < settle_block:
        settled_event = get_channel_event(
            channel_payed, 'ChannelSettled', start_block, 'latest')
        if settled_event is not None:
            # Settle event was received -> stop waiting.
            break

        # Get the last created block.
        for event in block_filter.get_new_entries():
            block = web3.eth.getBlock(event.hex())
            num_tx = len(block['transactions'])
            gas_free = block['gasLimit'] - block['gasUsed']
            gas_limit_increasement = block['gasLimit'] - \
                prevGasLimit if prevGasLimit is not None else 0
            gas_free_percentage = round(100 * gas_free / block['gasLimit'])
            is_congested = gas_free < min_free_gas

            # Log some info about the block.
            log.info(
                '%s#%s\t%s\t%s\t%s\t\t%s\t%s%s',
                RED if is_congested else GREEN,
                block['number'],
                num_tx,
                block['gasUsed'],
                block['gasLimit'],
                gas_free,
                gas_limit_increasement,
                # gas_free_percentage,
                COLOR_END
            )

            prevGasLimit = block['gasLimit']

        wait_for_blocks(1)

    # Check if the challenge period is over.
    if web3.eth.blockNumber >= settle_block:
        log.info('Settle block #%s is reached', settle_block)

        headers = invalid_headers(3)
        log.info(headers)

        # Send settle transaction.
        settle_tx = create_signed_contract_transaction(
            private_key=channel_payed.core.private_key,
            contract=channel_payed.core.channel_manager,
            func_name='settle',
            args=[
                channel_payed.receiver,
                channel_payed.block,
                rlp.encode(headers)
            ],
            gas_price=22000000000,
            gas_limit=1300000,
        )
        settle_tx_hash = web3.eth.sendRawTransaction(settle_tx)
        log.info('Sent settle transaction (tx=%s)', settle_tx_hash.hex())

    # Wait for the settle event again.
    settle_tx = wait_for_settled_channel(channel_payed, start_block)

    # Get address of account that settled the channel.
    settled_by_addr = settle_tx['from']
    log.info('Settled by %s', settled_by_addr)
    is_settled_by_receiver = is_same_address(settled_by_addr, channel_payed.receiver)

    # Determine which party settled the channel.
    settled_by = 'receiver' if is_settled_by_receiver else 'sender'
    log.info('Channel has been settled by %s at block #%s',
             settled_by, settle_tx['blockNumber'])

    # Get the block containing the close transaction.
    close_block = web3.eth.getBlock(close_event['blockNumber'])

    # Get the block containing the settle transaction.
    settle_block = web3.eth.getBlock(settle_tx['blockNumber'])

    # Calculate the elapsed time between close and settle.
    if (close_block is not None) & (settle_block is not None):
        elapsed_time = datetime.timedelta(
            seconds=settle_block['timestamp'] - close_block['timestamp']
        )
        log.info('Elapsed time between close and settle -> %s', str(elapsed_time))

    # Get the amount of used gas for settle.
    settle_receipt = web3.eth.getTransactionReceipt(settle_tx['hash'])
    log.info('Gas used for settle transaction: %s', str(settle_receipt['gasUsed']))

    # assert not is_settled_by_receiver, 'channel was settled by sender'
    assert is_settled_by_receiver, 'channel was settled by receiver'

    # Stop spamming.
    spammer.stop()


# @pytest.mark.skip(reason="no way of currently testing this")
def test_uncooperative_close(
        channel_manager: ChannelManager,
        channel_payed: Channel,
        min_free_gas: int,
        use_tester: bool,
        invalid_headers,
        valid_headers,
        wait_for_blocks,
        wait_for_settled_channel,
        web3: Web3
):
    # Simulate failing channel manager.
    channel_manager.stop()

    # Set cheat balance.
    channel_payed.update_balance(0)

    # Close the channel uncooperatively with cheat balance.
    close_event = channel_payed.close()
    close_tx = web3.eth.getTransaction(close_event['transactionHash'])
    log.info('Sent close transaction (tx=%s)', close_tx['hash'].hex())

    # Get the block number from which the channel can be settled.
    _, _, settle_block, _, _ = channel_payed.core.channel_manager.call().getChannelInfo(
        channel_payed.sender, channel_payed.receiver, channel_payed.block
    )
    log.info('Sender can settle the channel at block #%s', settle_block)

    # Wait until (a) the challenge period is over or (b) the channel is settled.
    block_filter = web3.eth.filter('latest')
    start_block = web3.eth.blockNumber
    settled_event = None
    while web3.eth.blockNumber < settle_block:
        settled_event = get_channel_event(
            channel_payed, 'ChannelSettled', start_block, 'latest')
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

        wait_for_blocks(1)

    # Check if the challenge period is over.
    if web3.eth.blockNumber >= settle_block:
        log.info('Settle block #%s is reached', settle_block)

        headers = valid_headers(3)
        log.info('Settle with block headers: %s', headers)
        rlp_headers = rlp.encode(headers)

        # Send settle transaction.
        settle_tx = create_signed_contract_transaction(
            private_key=channel_payed.core.private_key,
            contract=channel_payed.core.channel_manager,
            func_name='settle',
            args=[
                channel_payed.receiver,
                channel_payed.block,
                rlp_headers,
            ],
            gas_price=22000000000,
            gas_limit=1300000,
        )
        settle_tx_hash = web3.eth.sendRawTransaction(settle_tx)
        log.info('Sent settle transaction (tx=%s)', settle_tx_hash.hex())

    # Wait for the settle event again.
    settle_tx = wait_for_settled_channel(channel_payed, start_block)

    # Get address of account that settled the channel.
    settled_by_addr = settle_tx['from']
    log.info('Settled by %s', settled_by_addr)
    is_settled_by_sender = is_same_address(settled_by_addr, channel_payed.sender)

    # Determine which party settled the channel.
    settled_by = 'sender' if is_settled_by_sender else 'receiver'
    log.info('Channel has been settled by %s at block #%s',
             settled_by, settle_tx['blockNumber'])

    # Get the block containing the close transaction.
    close_block = web3.eth.getBlock(close_event['blockNumber'])

    # Get the block containing the settle transaction.
    settle_block = web3.eth.getBlock(settle_tx['blockNumber'])

    # Calculate the elapsed time between close and settle.
    if (close_block is not None) & (settle_block is not None):
        elapsed_time = datetime.timedelta(
            seconds=settle_block['timestamp'] - close_block['timestamp']
        )
        log.info('Elapsed time between close and settle -> %s', str(elapsed_time))

    # Get the amount of used gas for settle.
    settle_receipt = web3.eth.getTransactionReceipt(settle_tx['hash'])
    log.info('Gas used for settle transaction: %s', str(settle_receipt['gasUsed']))

    assert is_settled_by_sender, 'channel was settled by receiver'
