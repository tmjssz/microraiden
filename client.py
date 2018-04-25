from microraiden import HTTPHeaders, Client, Session
import requests
from eth_utils import encode_hex
from munch import Munch
import logging

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

def main():
    client = Client(private_key=privkey, key_password_path=None, channel_manager_address=channel_manager_address)

    channel = client.get_suitable_channel(receiver, 10)
    # channel.create_transfer(9)

    # print_channel(channel)

    # send_payment(channel, 3)
    channel.close(0)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()