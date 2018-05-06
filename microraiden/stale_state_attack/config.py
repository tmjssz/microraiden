# private key of account that makes the attack
PRIVATE_KEY = 'c87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3'

# address of attacked account
RECEIVER_ADDRESS = '0xf17f52151ebef6c7334fad080c5704d77216b732'

# address of microraiden channel manager contract
CHANNEL_MANAGER_ADDRESS = '0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da'
CHALLENGE_PERIOD = 6

# url of attacked microraiden proxy
PROXY_URL = 'http://localhost:5000/echodyn/'

# transaction settings
SPAM_BATCH_SIZE = 500   # number of transactions to send at once
MIN_PENDING_TXS = 500   # minimum number of pending transactions during spamming period
GAS_PRICE = 30000000000 # gas price to send transactions with
GAS_LIMIT = 130000      # gas limit to send transactions with
WAIT_TIMEOUT = 3600     # timeout in seconds to wait for channel event confirmations