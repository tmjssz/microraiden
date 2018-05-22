#!/usr/bin/python

import sys
import os
import logging
import click
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

from web3 import Web3, HTTPProvider
from cheater import Cheater


@click.command()
@click.option(
    '--rpcaddr',
    default='http://127.0.0.1',
    help='Address of the RPC server.',
    type=str
)
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server.',
    type=int
)
@click.option(
    '--channel-manager',
    default='0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da',
    help='Address of the channel manager contract.',
    type=str
)
@click.option(
    '--receiver',
    required=True,
    help='Address of the account that the proxy is running with.',
    type=str
)
@click.option(
    '--proxy-address',
    default='http://127.0.0.1:5000',
    help='Url of the microraiden echo server.',
    type=str
)
@click.option(
    '--private-key',
    required=True,
    help='Hex-encoded private key.',
    type=str
)
def main(rpcaddr: str, rpcport: int, channel_manager: str, receiver: str, proxy_address: str, private_key: str):
    # Initialize web3
    web3 = Web3(HTTPProvider('{}:{}'.format(rpcaddr, rpcport)))

    # Initialize cheater
    cheater = Cheater(
        web3=web3,
        private_key=private_key,
        channel_manager_address=channel_manager,
        receiver=receiver,
        proxy_address=proxy_address,
    )

    # Start stale state attack
    cheater.start()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # pylint: disable=E1120
    main()
    # pylint: enable=E1120
