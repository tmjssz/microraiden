import logging
import pytest
from web3 import Web3
from microraiden.test.utils.spamming import Spammer

log = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def spammer(web3: Web3) -> Spammer:
    spammer = Spammer(
        web3=web3,
        input_file='/Users/tim/Develop/microraiden/microraiden/test/data/spam_raw_txs.txt',
        offset=1,
    )
    spammer.start()
    return spammer
