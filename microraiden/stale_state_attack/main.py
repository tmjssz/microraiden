#!/usr/bin/python

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..'))

import config as config
from web3 import Web3, HTTPProvider
from cheater import Cheater
import logging, click

@click.command()
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server',
    type=int
)
def main(rpcport: int):
    # Initialize web3
    web3 = Web3(HTTPProvider('http://127.0.0.1:' + str(rpcport)))

    # Initialize cheater
    cheater = Cheater(
        web3=web3,
        private_key=config.PRIVATE_KEY,
        channel_manager_address=config.CHANNEL_MANAGER_ADDRESS,
        congestion_level=config.CONGESTION_LEVEL,
    )

    # Start stale state attack
    cheater.start()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
