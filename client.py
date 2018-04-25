from microraiden import HTTPHeaders, Client, Session
import requests
from eth_utils import encode_hex
from munch import Munch

receiver = '0xf17f52151ebef6c7334fad080c5704d77216b732'
privkey = 'c87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3'
channel_manager_address = '0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da'
endpoint_url = 'http://localhost:5000'

# 'with' statement to cleanly release the client's file lock in the end.
client = Client(private_key=privkey, key_password_path=None, channel_manager_address=channel_manager_address)

channel = client.get_suitable_channel(receiver, 10)
channel.create_transfer(3)
channel.create_transfer(4)

print(
    'Current balance proof:\n'
    'From: {}\n'
    'To: {}\n'
    'Channel opened at block: #{}\n'  # used to uniquely identify this channel
    'State: {}\n'
    'Balance: {}\n'                   # total: 7
    'Signature: {}\n'                 # valid signature for a balance of 7 on this channel
    .format(
        channel.sender, channel.receiver, channel.block, channel.state, channel.balance, channel.balance_sig
    )
)

headers = Munch()
headers.balance = str(channel.balance)
headers.balance_signature = encode_hex(channel.balance_sig)
headers.sender_address = channel.sender
headers.open_block = str(channel.block)
headers = HTTPHeaders.serialize(headers)

print(headers)

response = requests.get(endpoint_url + '/echodyn/1', headers=headers)

print(response)


# session = Session(client=client, close_channel_on_exit=True, endpoint_url=endpoint_url)
# response = session.get('http://localhost:5000/echodyn/1')

# print(response)



# channel.close(0)

# with Client(private_key=privkey, key_password_path=None, channel_manager_address=channel_manager_address) as client:
    # print(client)
    # channel = client.get_suitable_channel(receiver, 10)
    # channel.create_transfer(3)
    # channel.create_transfer(4)

    # print(
    #     'Current balance proof:\n'
    #     'From: {}\n'
    #     'To: {}\n'
    #     'Channel opened at block: #{}\n'  # used to uniquely identify this channel
    #     'Balance: {}\n'                   # total: 7
    #     'Signature: {}\n'                 # valid signature for a balance of 7 on this channel
    #     .format(
    #         channel.sender, channel.receiver, channel.block, channel.balance, channel.balance_sig
    #     )
    # )