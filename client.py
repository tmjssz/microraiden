from microraiden import HTTPHeaders, Client, Session
from microraiden.utils import get_event_blocking
from eth_utils import encode_hex
from munch import Munch
from web3 import Web3, HTTPProvider
import gevent
import requests
import logging
import click

receiver = '0xf17f52151ebef6c7334fad080c5704d77216b732'
privkey = 'c87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3'
channel_manager_address = '0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da'
endpoint_url = 'http://localhost:5000'


def send_payment(channel, amount):
    headers = Munch()
    headers.balance = str(channel.balance)
    headers.balance_signature = encode_hex(channel.balance_sig)
    headers.sender_address = channel.sender
    headers.open_block = str(channel.block)
    headers = HTTPHeaders.serialize(headers)
    response = requests.get(endpoint_url + '/echodyn/' + str(amount), headers=headers)
    if response.status_code != 200:
        logging.error(
            'Payment failed.\n'
            'Response headers: {}'
            .format(response.headers)
        )
    else:
        logging.info('Successfull payment of {}'.format(amount))

def print_channel(channel):
    logging.info('Active channel: (sender={}, block={})'.format(channel.sender, channel.block))
    logging.debug(
        'Active channel:\n'
        '  Current balance proof:\n'
        '  From: {}\n'
        '  To: {}\n'
        '  Open block: #{}\n'  # used to uniquely identify this channel
        '  State: {}\n'
        '  Balance: {}\n'
        '  Signature: {}\n'
        .format(
            channel.sender, channel.receiver, channel.block, channel.state, channel.balance, channel.balance_sig
        )
    )

def send_empty_transaction(web3: Web3 = None):
    result = web3.eth.sendTransaction({
        'from': web3.eth.accounts[0],
        'to': web3.eth.accounts[0],
        'value': 0,
        # 'gas': gas,
        # 'gasPrice': gasPrice,
    })
    logging.debug('Sent transaction (hash={})'.format(result.hex()))

def spam_network(web3: Web3 = None, number: int = 100):
    logging.info('Spamming network with {} transactions'.format(number))
    for x in range(number):
        send_empty_transaction(web3)

def wait_for_blocks(web3, n):
    target_block = web3.eth.blockNumber + n
    while web3.eth.blockNumber < target_block:
        gevent.sleep(2)

@click.command()
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server',
    type=int
)
def main(rpcport: int):
    web3 = Web3(HTTPProvider('http://127.0.0.1:' + str(rpcport)))
    receiver_address = web3.toChecksumAddress(receiver)

    client = Client(private_key=privkey, key_password_path=None, channel_manager_address=channel_manager_address)

    channel = client.get_suitable_channel(receiver_address, 10)

    logging.debug('Waiting for channel creation event on the blockchain...')
    openedEvent = get_event_blocking(
        channel.core.channel_manager,
        'ChannelCreated',
        from_block=channel.block,
        to_block='latest',
        argument_filters={
            '_sender_address': channel.core.address,
            '_receiver_address': receiver_address
        }
    )

    confirmations = 3
    current_block = web3.eth.blockNumber

    if (current_block - openedEvent['blockNumber'] < confirmations):
        logging.info('Waiting for {} confirmations...'.format(confirmations))
        wait_for_blocks(web3, confirmations)

    channel.create_transfer(3)

    print_channel(channel)

    send_payment(channel, 3)

    channel.close(0)

    logging.debug('Waiting for close confirmation event...')
    closedEvent = get_event_blocking(
        channel.core.channel_manager,
        'ChannelCloseRequested',
        from_block=current_block + 1,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': receiver_address,
            '_open_block_number': channel.block
        }
    )
    logging.info('Channel closed at block #{}'.format(closedEvent['blockNumber']))

    spam_network(web3, 500)

    logging.debug('Waiting for settle confirmation event...')
    settledEvent = get_event_blocking(
        channel.core.channel_manager,
        'ChannelSettled',
        from_block=current_block + 1,
        argument_filters={
            '_sender_address': channel.sender,
            '_receiver_address': receiver_address,
            '_open_block_number': channel.block
        }
    )
    logging.info('Channel settled at block #{}'.format(settledEvent['blockNumber']))

    logging.info('Mined blocks between close -> settle = {}'.format(settledEvent['blockNumber']-closedEvent['blockNumber']))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
