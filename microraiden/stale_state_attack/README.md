# State Stale Attack

## Run

1. Start a local private network with at least one miner
2. Deploy the microraiden contract in your local testnet, e.g. with this script: https://github.com/raiden-network/microraiden/blob/master/contracts/deploy/deploy_testnet.py
  * There must be a configuration for the network id of your private network in `NETWORK_CONFIG_DEFAULTS`of https://github.com/raiden-network/microraiden/blob/master/microraiden/config.py
    Example:
    ```python
    15: NetworkConfig(
        channel_manager_address='0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da',
        start_sync_block=0
    ),
    ```
3. Start the microraiden echo server: `python3 -m microraiden.examples.echo_server`
  ```shell
  Usage: echo_server.py [OPTIONS]

  Options:
    --private-key TEXT  The server's private key path.  [required]
    --rpcport INTEGER   Port of the RPC server
    --help              Show this message and exit.
  ```
4. Run the attacker client: `python3 -m microraiden.stale_state_attack.main`
  ```shell
  Usage: main.py [OPTIONS]

  Options:
    --rpcaddr TEXT          Address of the RPC server.
    --rpcport INTEGER       Port of the RPC server.
    --channel-manager TEXT  Address of the channel manager contract.
    --receiver TEXT         Address of the account that the proxy is running
                            with.  [required]
    --proxy-address TEXT    Url of the microraiden echo server.
    --private-key TEXT      Hex-encoded private key.  [required]
    --help                  Show this message and exit.
  ```

## Note

In order to deploy the microraiden contract with a challenge period < 500 for testing do the following:

* Modify the contract constructor: https://github.com/raiden-network/microraiden/blob/master/contracts/contracts/RaidenMicroTransferChannels.sol
  ```python
  require(_challenge_period >= 500); # define your desired value
  ``
  
* Remove the following line, if you use the python script https://github.com/raiden-network/microraiden/blob/master/contracts/deploy/deploy_testnet.py
  ```python
  assert challenge_period >= 500, 'Challenge period should be >= 500 blocks'
  ```
