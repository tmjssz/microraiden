import logging
import os
import pytest
from web3 import Web3
from microraiden.test.utils.spam import Spammer
from microraiden import constants

log = logging.getLogger(__name__)


@pytest.fixture
def min_free_gas() -> int:
    return 130000


@pytest.fixture(scope='session')
def spammer(web3: Web3) -> Spammer:
    input_file = os.path.join(constants.MICRORAIDEN_DIR, 'microraiden',
                              'test', 'data', 'spam.txt')
    spam = Spammer(
        web3=web3,
        input_file=input_file,
        offset=1,
    )
    spam.start()
    return spam
