#!/usr/bin/python

from web3 import Web3, HTTPProvider
from geth import LoggingMixin, DevGethProcess
import os
import threading
import subprocess
import time
import click
import tarfile
import shutil

# virtualenv -p python3 env
# . env/bin/activate
# pip install -r requirements.txt


class MyGeth(LoggingMixin, DevGethProcess):
    pass


@click.command()
@click.option(
    '--data-dir',
    default='.blockchain',
    help='Data directory for the databases and keystore.',
    type=str
)
@click.option(
    '--networkid',
    default='15',
    help='Network identifier.',
    type=str
)
@click.option(
    '--passwords-file',
    default='geth-passwords.txt',
    help='Password file to use for non-interactive password input.',
    type=str
)
@click.option(
    '--reset',
    help='Reset the databases of all geth nodes.',
    is_flag=True,
)
def main(data_dir: str, networkid: str, passwords_file: str, reset: bool):
    if reset & os.path.isdir(data_dir):
        print('Resetting blockchain')
        shutil.rmtree(data_dir)
    
    if not os.path.isdir(data_dir):
        print('Extracting blockchain archive')
        tar = tarfile.open('blockchain.tar.gz')
        tar.extractall()

    if not os.path.isdir('logs'):
        os.makedirs('logs')

    geth_miner = MyGeth('miner', data_dir, {
        'rpc_port': '8545',
        'mine': True,
        'network_id': networkid,
        'max_peers': '2',
        'port': '30303',
        'password': passwords_file,
        'unlock': '0,1',
        'ipc_path': None,
        'ipc_disable': True,
        'ws_enabled': False,
    })
    geth_light_node_1 = MyGeth('light1', data_dir, {
        'rpc_port': '9545',
        'miner_threads': None,
        'mine': False,
        'network_id': networkid,
        'max_peers': '2',
        'port': '30342',
        'password': passwords_file,
        'unlock': '0,1',
        'ipc_path': None,
        'ipc_disable': True,
        'ws_enabled': False,
    })
    geth_light_node_2 = MyGeth('light2', data_dir, {
        'rpc_port': '9546',
        'miner_threads': None,
        'mine': False,
        'network_id': networkid,
        'max_peers': '2',
        'port': '30343',
        'password': passwords_file,
        'unlock': '0,1',
        'ipc_path': None,
        'ipc_disable': True,
        'ws_enabled': False,
    })

    geth_miner.start()
    geth_light_node_1.start()
    geth_light_node_2.start()

    geth_miner.wait_for_rpc(timeout=30)
    geth_light_node_1.wait_for_rpc(timeout=30)
    geth_light_node_2.wait_for_rpc(timeout=30)

    web3_miner = Web3(HTTPProvider('http://{}:{}'.format(geth_miner.rpc_host, geth_miner.rpc_port)))
    web3_light1 = Web3(HTTPProvider('http://{}:{}'.format(geth_light_node_1.rpc_host, geth_light_node_1.rpc_port)))
    web3_light2 = Web3(HTTPProvider('http://{}:{}'.format(geth_light_node_2.rpc_host, geth_light_node_2.rpc_port)))

    web3_light1.admin.addPeer(web3_miner.admin.nodeInfo.enode)
    web3_light2.admin.addPeer(web3_miner.admin.nodeInfo.enode)

    print()
    print('Started network peers at http://{}'.format(geth_miner.rpc_host))
    print()
    print('Connected peers:')
    print('| Node         | RPC port | Network port | Peers                      | Mining |')
    print('| ------------ | -------- | ------------ | -------------------------- | ------ |')
    print('| Full node    | {}     | 30303        | Light node 1, Light node 2 | {}   |'.format(geth_miner.rpc_port, geth_miner.is_mining))
    print('| Light node 1 | {}     | 30342        | Full node                  | {}  |'.format(geth_light_node_1.rpc_port, geth_light_node_1.is_mining))
    print('| Light node 2 | {}     | 30343        | Full node                  | {}  |'.format(geth_light_node_2.rpc_port, geth_light_node_2.is_mining))
    print()
    print('Microraiden Channel Manager:')
    print('| Challenge period | Contract address                           |')
    print('| ---------------- | ------------------------------------------ |')
    print('|       500 blocks | 0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da | ')
    print('|        15 blocks | 0xf25186B5081Ff5cE73482AD761DB0eB0d25abfBF | ')
    print()
    print('Accounts:')
    for i, acc in enumerate(web3_miner.eth.accounts):
        print('({}) {}'.format(i, acc))
    print()

    while True:
        pass


if __name__ == '__main__':
    # pylint: disable=E1120
    main()
    # pylint: enable=E1120
