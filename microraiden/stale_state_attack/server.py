"""
This is dummy code showing how the minimal app could look like.
In his case we don't use a proxy, but directly a server
"""
import logging
import os
import click
from flask import request
from web3 import Web3, HTTPProvider

from microraiden.channel_manager import ChannelManager
from microraiden.make_helpers import make_channel_manager
from microraiden.config import NETWORK_CFG
from microraiden.proxy import PaywalledProxy
from microraiden.proxy.resources import Expensive


log = logging.getLogger(__name__)


class DynamicPriceResource(Expensive):
    def get(self, url: str, param: int):
        log.info('Resource requested: {} with param "{}"'.format(request.url, param))
        return param

    def price(self):
        return int(request.view_args['param'])


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
    '--rpcaddr',
    default='http://127.0.0.1',
    help='Address of the RPC server.',
    type=str
)
@click.option(
    '--rpcport',
    default=8545,
    help='Port of the RPC server',
    type=int
)
def main(channel_manager: str, private_key: str, rpcaddr: str, rpcport: int):
    web3 = Web3(HTTPProvider('{}:{}'.format(rpcaddr, rpcport)))
    run(private_key, web3, channel_manager)


def run(
        private_key: str,
        web3: Web3,
        channel_manager_addr: str,
        state_file_path: str = os.path.join(click.get_app_dir('microraiden'), 'echo_server.db'),
        join_thread: bool = True
):
    dirname = os.path.dirname(state_file_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    NETWORK_CFG.set_defaults(int(web3.version.network))

    # set up a paywalled proxy
    # arguments are:
    #  - private key to use for receiving funds
    #  - file for storing state information (balance proofs)
    channel_manager = make_channel_manager(
        private_key,
        channel_manager_addr,
        state_file_path,
        web3
    )
    app = PaywalledProxy(channel_manager)

    # Resource with a price determined by the second parameter.
    app.add_paywalled_resource(
        DynamicPriceResource,
        "/echo/<int:param>"
    )

    # Start the app. proxy is a WSGI greenlet, so you must join it properly.
    app.run(debug=True)

    if join_thread:
        app.join()
    else:
        return app
    # Now use echo_client to get the resources.


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # pylint: disable=E1120
    main()
    # pylint: enable=E1120
