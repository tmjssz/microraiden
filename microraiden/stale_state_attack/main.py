#!/usr/bin/python

import sys
import os
import logging
import click
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

from web3 import Web3, HTTPProvider
from cheater import Cheater
from microraiden.stale_state_attack.config import (
    PRIVATE_KEY,
    CHANNEL_MANAGER_ADDRESS,
    CONGESTION_LEVEL
)


@click.command()
@click.option(
    '--rpcaddr',
    default='http://127.0.0.1',
    help='Address of the RPC server',
    type=str
)
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server',
    type=int
)
def main(rpcaddr: str, rpcport: int):
    # Initialize web3
    web3 = Web3(HTTPProvider('{}:{}'.format(rpcaddr, rpcport)))

    # Initialize cheater
    cheater = Cheater(
        web3=web3,
        private_key=PRIVATE_KEY,
        channel_manager_address=CHANNEL_MANAGER_ADDRESS,
        congestion_level=CONGESTION_LEVEL,
    )

    # Start stale state attack
    cheater.start()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # pylint: disable=E1120
    main()
    # pylint: enable=E1120
