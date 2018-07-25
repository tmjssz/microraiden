# _Stale State Attack_ Simulation

This microraiden client simulates a stale state attack where a channel is uncooperatively closed and settled with an outdated balance. The simulation performs the following steps:

1.  Open a channel with deposit=1 (or topup existing channel)
2.  Send off-chain payment over that channel
    * Increase channel's balance to 1
    * Send GET request to the `/echo/1` endpoint of [server.py](./server.py)
3.  Send **uncooperative close** transaction with outdated balance=0
4.  Start spamming the blockchain network via multiple threads
    * Continue spamming until challenge period is over
5.  Send **settle** transaction and wait for its confirmation

## Problem Description

After a channel has been closed uncooperatively a challenge period starts, during which the counterparty can revoke the close request in case it contains an invalid balance. This mechanism brings up a challenge that the microraiden protocol does not provide a solution for yet: A particularly high transaction load during the timeout period could fill up all respective blocks so that the revoke transaction is delayed and the channel gets settled with incorrect balances. This situation could also be initiated by a stale state attack where the attacker closes a channel with an old state and instantly spams the network with a large number of empty on-chain transactions in order to delay the revoke transaction. Another attack scenario could be that the attacker closes many different channels with outdated balances at the same time resulting in many on-chain transactions. All the defenders who try to dispute their channel's close request would have to compete with one another for available block space before the block timeout ends. This scenario is particularly problematic with hub-like network structures where single participants maintain a large number of state channels. Coupled with a spam attack the problem gets even more critical. Apart from a congested blockchain, the network gets confronted with a similar problem if corrupt miners refuse to mine revoke transactions or just create empty blocks.

## Quick Start

1.  Install requirements. For details see: [µRaiden: Installation](../../README.md#installation)
2.  Run Ethereum network with the script in [geth-cluster](./geth-cluster)
3.  Run the microraiden server (with active virtual environment):

    ```shell
    python3 -m microraiden.stale_state_attack.server --private-key "0xae6ae8e5ccbfb04590405997ee2d52d2b330726137b875053c36d94e974d162f" --channel-manager "0xf25186B5081Ff5cE73482AD761DB0eB0d25abfBF" --rpcport 9546
    ```
    
    In case of an error, you might need to clear the server's database first.
    
    ```shell
    rm ~/Library/Application\ Support/microraiden/echo_server.db
    rm ~/Library/Application\ Support/microraiden/echo_server.db.lock
    ```

4.  Run the attack simulation (with active virtual environment):

    ```shell
    python3 -m microraiden.stale_state_attack.main --receiver "0xf17f52151EbEF6C7334FAD080c5704D77216b732" --private-key "c87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3" --channel-manager "0xf25186B5081Ff5cE73482AD761DB0eB0d25abfBF" --rpcport 9545
    ```

## Server options

    ```shell
    Usage: server.py [OPTIONS]

    Options:
      --channel-manager TEXT  Address of the channel manager contract.
      --private-key TEXT      Hex-encoded private key.  [required]
      --rpcaddr TEXT          Address of the RPC server.
      --rpcport INTEGER       Port of the RPC server
      --help                  Show this message and exit.
    ```

## Client options

    ```shell
    Usage: main.py [OPTIONS]

    Options:
      --channel-manager TEXT  Address of the channel manager contract.
      --private-key TEXT      Hex-encoded private key.  [required]
      --proxy-address TEXT    Url of the microraiden echo server.
      --receiver TEXT         Address of the account that the proxy is running
                              with.  [required]
      --rpcaddr TEXT          Address of the RPC server.
      --rpcport INTEGER       Port of the RPC server.
      --help                  Show this message and exit.
    ```

## Deploy µRaiden contracts

In order to run the simulation with your own private network, make sure that the µRaiden contracts are deployed within that network. This can be done with this script: [deploy_testnet.py](../../contracts/deploy/deploy_testnet.py).
Before running that script, add a configuration for your network id in [config.py](../../microraiden/config.py).

```python
# Example for network id = 15
15: NetworkConfig(
    channel_manager_address='0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da',
    start_sync_block=0
),
```

### Short challenge period

The µRaiden contract enforces a minimum challenge period of 500 blocks by default. In order to deploy the microraiden contract for testing with a shorter challenge period, do the following:

* Modify the contract constructor: [RaidenMicroTransferChannels.sol](../../contracts/contracts/RaidenMicroTransferChannels.sol)

  ```python
  require(_challenge_period >= 500); # define your desired value
  ```

* Remove the following line, if you use the python script [deploy_testnet.py](../../contracts/deploy/deploy_testnet.py)
  ```python
  assert challenge_period >= 500, 'Challenge period should be >= 500 blocks'
  ```
