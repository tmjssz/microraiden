# _Stale State Attack_ Simulation

This microraiden client simulates a stale state attack where a channel is uncooperatively closed and settled with an outdated balance. The simulation performs the following steps:

1.  Open a channel with deposit=1 (or topup existing channel)
2.  Send off-chain payment over that channel
    a. Increase channel's balance to 1
    b. Send GET request to the `/echodyn/1` endpoint of the echo server proxy
3.  Send **uncooperative close** transaction with outdated balance=0
4.  Start spamming the blockchain network with multiple threads
    * Continue spamming until challenge period is over
5.  Send **settle** transaction and wait for its confirmation

## Problem Description

The mechanism of revoking an uncooperative channel close during a timeout period brings up a challenge that the microraiden protocol does not provide a solution for yet. After an uncooperative channel close, the counterparty's revoke transaction may not get mined on time in case of a blockchain congestion. A particularly high transaction load during the timeout period could fill up all respective blocks so that the revoke transaction is delayed and the channel gets settled with incorrect balances. This situation could also be initiated by a stale state attack where the attacker closes a channel with an old state and instantly spams the network with a large number of empty on-chain transactions in order to delay the revoke transaction. Another attack scenario could be that the attacker closes many different channels with outdated balances at the same time resulting in many on-chain transactions. All the defenders who try to dispute their channel's close request would have to compete with one another for available block space before the block timeout ends. This scenario is particularly problematic with hub-like network structures where single participants maintain a large number of state channels. Coupled with a spam attack the problem gets even more critical. Apart from a congested blockchain, the network gets confronted with a similar problem if corrupt miners refuse to mine revoke transactions or just create empty blocks.

## Run Simulation

1.  Start a local private network with at least one miner and the deployed microraiden contract. This can be done with the python script in `./geth-cluster`.

    * If you run your own network, make sure to deploy the microraiden contract in your local testnet, e.g. with this script: https://github.com/tmjssz/microraiden/blob/master/contracts/deploy/deploy_testnet.py
      * There must be a configuration for the network id of your private network in `NETWORK_CONFIG_DEFAULTS`of https://github.com/tmjssz/microraiden/blob/master/microraiden/config.py


      ```python
      # Example for network id = 15
      15: NetworkConfig(
          channel_manager_address='0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da',
          start_sync_block=0
      ),
      ```

2.  Run the **echo server** proxy: `python3 -m microraiden.examples.echo_server`

    ```shell
    Usage: echo_server.py [OPTIONS]

    Options:
      --private-key TEXT  The server's private key path.  [required]
      --rpcport INTEGER   Port of the RPC server
      --help              Show this message and exit.
    ```

    With the testnet from `./geth-cluster` running, the command is:

    ```shell
    python3 -m microraiden.examples.echo_server --private-key ./microraiden/stale_state_attack/geth-cluster/.blockchain/miner/keystore/UTC--2017-11-17T23-03-01.537330770Z--f17f52151ebef6c7334fad080c5704d77216b732 --rpcport 9546
    ```

    * For more details on installing and running the proxy see: https://github.com/tmjssz/microraiden#quick-start

3.  Run the attacker client: `python3 -m microraiden.stale_state_attack.main`

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

    With the testnet from `./geth-cluster` running, the command is:

    ```shell
    python3 -m microraiden.stale_state_attack.main --receiver "0xf17f52151ebef6c7334fad080c5704d77216b732" --private-key "c87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3" --channel-manager "0xf25186B5081Ff5cE73482AD761DB0eB0d25abfBF" --rpcport 9545
    ```

## Note

In order to deploy the microraiden contract with a challenge period < 500 for testing do the following:

* Modify the contract constructor: https://github.com/tmjssz/microraiden/blob/master/contracts/contracts/RaidenMicroTransferChannels.sol

  ```python
  require(_challenge_period >= 500); # define your desired value
  ```

* Remove the following line, if you use the python script https://github.com/tmjssz/microraiden/blob/master/contracts/deploy/deploy_testnet.py
  ```python
  assert challenge_period >= 500, 'Challenge period should be >= 500 blocks'
  ```
