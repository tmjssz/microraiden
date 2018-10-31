import datetime
import logging
import pytest
import rlp
import os
import gevent
from eth_utils import encode_hex, is_same_address, decode_hex, big_endian_to_int
from microraiden.channel_manager import ChannelManager
from microraiden import Client
from microraiden.client import Channel
from microraiden.test.utils.spam import Spammer
from web3.providers.rpc import HTTPProvider
from microraiden.constants import CONTRACTS_ABI_JSON
from microraiden.utils import get_logs, create_signed_contract_transaction
from functools import reduce
from web3 import Web3

log = logging.getLogger(__name__)

GREEN = '\033[92m'
RED = '\033[91m'
COLOR_END = '\033[0m'

block_space_proof = True


@pytest.fixture(scope='session')
def channel_manager_address():
    if block_space_proof:
        return '0xFB88dE099e13c3ED21F80a7a1E49f8CAEcF10df6'
    else:
        return '0x8f0483125FCb9aaAEFA9209D8E9d7b9C8B9Fb90F'


@pytest.fixture(scope='session')
def contract_abi_path():
    root_path = "./"
    if not block_space_proof:
        root_path = "../../microraiden-contract-origin/microraiden/"
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), root_path + CONTRACTS_ABI_JSON)


@pytest.fixture
def channel_manager(
        receiver_privkey,
        channel_manager_contract,
        token_contract,
        state_db_path,
):
    rpc = HTTPProvider('http://127.0.0.1:9545')
    web3 = Web3(rpc)

    manager = ChannelManager(
        web3,
        channel_manager_contract,
        token_contract,
        receiver_privkey,
        n_confirmations=5,
        state_filename=state_db_path
    )

    def fail(greenlet):
        raise greenlet.exception

    manager.link_exception(fail)
    manager.start()

    yield manager
    manager.stop()


@pytest.fixture(scope='session')
def token_address(
    web3,
    channel_manager_address,
    channel_manager_abi
):
    channel_manager = web3.eth.contract(
        abi=channel_manager_abi,
        address=channel_manager_address
    )
    return channel_manager.call().token()


@pytest.fixture
def open_channels(
    channel_manager: ChannelManager,
    client: Client,
    receiver_address: str,
    wait_for_blocks
):
    def _open_channels(number: int):
        channels = []
        for x in range(number):
            channel = client.open_channel(receiver_address, 10)
            wait_for_blocks(channel_manager.n_confirmations + 1)
            gevent.sleep(channel_manager.blockchain.poll_interval)
            assert (channel.sender, channel.block) in channel_manager.channels

            channel_id = (channel.sender, channel.block)

            # Make an off-chain payment through the opened channel.
            sig = encode_hex(channel.create_transfer(5))
            channel_manager.register_payment(
                channel.sender,
                channel.block,
                5,
                sig,
            )

            # Make sure that that the payment was successfull.
            receivers_channel = channel_manager.channels[channel_id]
            assert receivers_channel.balance == 5

            channels.append(channel)

        return channels

    return _open_channels


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

        # Arguments for settle transaction.
        settle_args = [channel_payed.receiver, channel_payed.block]

        if (block_space_proof):
            # Create block space proof.
            headers = invalid_headers(3)
            log.info('Settle with block headers: %s', headers)
            rlp_headers = rlp.encode(headers)
            settle_args.append(rlp_headers)

        # Send settle transaction.
        settle_tx = create_signed_contract_transaction(
            private_key=channel_payed.core.private_key,
            contract=channel_payed.core.channel_manager,
            func_name='settle',
            args=settle_args,
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
# @pytest.mark.parametrize("", [0, 1])
def test_uncooperative_close(
        channel_manager: ChannelManager,
        open_channels,
        min_free_gas: int,
        use_tester: bool,
        invalid_headers,
        valid_headers,
        wait_for_blocks,
        wait_for_settled_channel,
        web3: Web3
):
    # Open the channels.
    channels = open_channels(10)

    # Simulate failing channel manager.
    channel_manager.stop()

    # Array for storing the used gas of each settle transaction.
    gas_used_list = []

    for channel in channels:
        # Close the channel uncooperatively.
        close_event = channel.close()
        close_tx = web3.eth.getTransaction(close_event['transactionHash'])
        log.info('Sent close transaction (tx=%s)', close_tx['hash'].hex())

        # Get the block number from which the channel can be settled.
        _, _, settle_block, _, _ = channel.core.channel_manager.call().getChannelInfo(
            channel.sender, channel.receiver, channel.block
        )
        log.info('Sender can settle the channel at block #%s', settle_block)

        # Wait until the challenge period is over.
        block_filter = web3.eth.filter('latest')
        start_block = web3.eth.blockNumber
        settled_event = None
        while web3.eth.blockNumber < settle_block:
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

        # Challenge period is over.
        log.info('Settle block #%s is reached', settle_block)

        # Arguments for settle transaction.
        settle_args = [channel.receiver, channel.block]

        if (block_space_proof):
            # Create block space proof.
            headers = valid_headers(3)
            log.info('Settle with block headers: %s', headers)
            rlp_headers = rlp.encode(headers)
            settle_args.append(rlp_headers)

        # Send settle transaction.
        settle_tx = create_signed_contract_transaction(
            private_key=channel.core.private_key,
            contract=channel_manager.channel_manager_contract,
            func_name='settle',
            args=settle_args,
            gas_price=22000000000,
            gas_limit=1300000,
        )
        settle_tx_hash = web3.eth.sendRawTransaction(settle_tx)
        log.info('Sent settle transaction (tx=%s)', settle_tx_hash.hex())

        # Wait for the settle event.
        settle_tx = wait_for_settled_channel(channel, start_block)
        log.info('Channel settled at block #%s', settle_tx['blockNumber'])

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
        gas_used = settle_receipt['gasUsed']
        gas_used_list.append(gas_used)
        log.info('Gas used for settle transaction: %s', str(gas_used))

    log.info(gas_used_list)
    avg_gas_used = round(reduce(lambda x, y: x + y, gas_used_list) / len(gas_used_list))
    log.info('Average gas used = %s', str(avg_gas_used))
