# State Stale Attack

## Run

1. Start a local private network with at least one miner
2. Deploy the microraiden contract in your local testnet, e.g. with this script: https://github.com/raiden-network/microraiden/blob/master/contracts/deploy/deploy_testnet.py
3. Start the microraiden echo server: `python3 -m microraiden.examples.echo_server`
  ```shell
  Usage: echo_server.py [OPTIONS]

  Options:
    --private-key TEXT  The server's private key path.  [required]
    --rpcport INTEGER   Port of the RPC server
    --help              Show this message and exit.
  ```
4. Run the attacker client: `python3 microraiden/stale_state_attack/main.py`
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