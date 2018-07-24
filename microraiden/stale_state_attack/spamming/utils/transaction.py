#!/usr/bin/python

from typing import Union
from .crypto import privkey_to_addr, sign_transaction
from ethereum.transactions import Transaction
from eth_utils import decode_hex, encode_hex
import rlp


def create_signed_transaction(
        network_id: int,
        private_key: str,
        to: str,
        value: int=0,
        data=b'',
        nonce: int=None,
        gas_price: Union[int, None]=30000000000,
        gas_limit: int=130000
) -> str:
    """
    Creates a signed on-chain transaction compliant with EIP155.
    """
    from_ = privkey_to_addr(private_key)

    tx = Transaction(nonce, gas_price, gas_limit, to, value, data)
    tx.sender = decode_hex(from_)

    sign_transaction(tx, private_key, network_id)
    return encode_hex(rlp.encode(tx))
