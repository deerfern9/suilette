from pysui import handle_result
from pysui.sui.sui_bcs import bcs
from pysui.sui.sui_types import *
from pysui import SuiConfig, SyncClient
from pysui.abstracts import SignatureScheme
from pysui.sui.sui_types.bcs import Argument
from pysui.sui.sui_txn import SyncTransaction
from pysui.sui.sui_types.address import SuiAddress
from pysui.sui.sui_clients.sync_client import SuiClient
from pysui.sui.sui_txn.transaction_builder import PureInput

import time
import random
import requests
from loguru import logger
from typing import Optional
from pydantic import BaseModel

sui_rpc = 'https://sui-mainnet-rpc.nodereal.io'
delay = 1 * 3600


class Sui8192TransactionResult(BaseModel):
    address: str
    digest: str


class SuiTxResult(Sui8192TransactionResult):
    reason: Optional[str]


def read_file(filename):
    result = []
    with open(filename, 'r') as file:
        for tmp in file.readlines():
            result.append(tmp.replace('\n', ''))

    return result


def write_to_file(filename, text):
    with open(filename, 'a') as file:
        file.write(f'{text}\n')


def get_game_object_id():
    response = {'result': {'status': '1'}}
    while response['result']['status'] in ['1', '3']:
        headers = {
            'authority': 'www.suilette.com',
            'accept': 'application/json, text/plain, */*',
            'referer': 'https://www.suilette.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        }

        response = requests.get('https://www.suilette.com/api/sui-game', headers=headers).json()
        if response['result']['status'] in ['1', '3']:
            time.sleep(1)
    return response['result']['game_object_id']


def get_all_token(client, token):
    while True:
        try:
            """ Возвращает все объекты адреса (если они есть) и их баланс """

            # Создаёт(если его нет) элемент "client"
            client = client if client else SuiClient(SuiConfig.default_config())
            # Достаёт все объекты указанного токена

            all_coin_type = client.get_coin(SuiString(token)).result_data.data

            # Обрабатывает объекты
            gas_objects: list[all_coin_type] = handle_result(
                client.get_gas(
                    client.config.active_address
                )
            ).data

            return all_coin_type

        except:
            time.sleep(5)


def get_sui_config(mnemonic: str) -> SuiConfig:
    sui_config = SuiConfig.user_config(rpc_url=sui_rpc)
    if '0x' in mnemonic:
        sui_config.add_keypair_from_keystring(keystring={
            'wallet_key': mnemonic,
            'key_scheme': SignatureScheme.ED25519
        })
    else:
        sui_config.recover_keypair_and_address(
            scheme=SignatureScheme.ED25519,
            mnemonics=mnemonic,
            derivation_path="m/44'/784'/0'/0'/0'"
        )
    sui_config.set_active_address(address=SuiAddress(sui_config.addresses[0]))

    return sui_config


def get_sui_coin_objects_for_merge(client):
    all_coin_type = get_all_token(client, "0x2::sui::SUI")

    gas_objects: list[all_coin_type] = handle_result(
        client.get_gas(
            client.config.active_address)
    ).data

    zero_coins = [x for x in gas_objects if int(x.balance) == 0]
    non_zero_coins = [x for x in gas_objects if int(x.balance) > 0]

    richest_coin = max(non_zero_coins, key=lambda x: int(x.balance), default=None)
    gas_amount_coin = min(non_zero_coins, key=lambda x: int(x.balance), default=None)

    if richest_coin:
        non_zero_coins.remove(richest_coin)

    return zero_coins, non_zero_coins, richest_coin, gas_amount_coin


def transaction_run(txb: SyncTransaction):
    """Example of simple executing a SuiTransaction."""
    # Set sender if not done already
    if not txb.signer_block.sender:
        txb.signer_block.sender = txb.client.config.active_address

    # Execute the transaction
    tx_result = txb.execute(gas_budget="55865000")
    if tx_result.is_ok():
        owner = tx_result.result_data.balance_changes[0]['owner']['AddressOwner']
        digest = tx_result.result_data.digest
        logger.success(f"Suilette Success! {owner} | Transaction success! Digest: {digest}")
        write_to_file('Digests.txt', f'{owner};{digest}')
        return tx_result.result_data

    else:
        logger.error(f"Transaction error {tx_result}")


def create_gas_object(amount, client: SuiClient = None):
    client = client if client else SuiClient(SuiConfig.default_config())
    txer = SyncTransaction(client)

    amount = int(amount * 10 ** 9)
    spcoin = txer.split_coin(coin=bcs.Argument("GasCoin"), amounts=[amount])
    txer.transfer_objects(transfers=[spcoin], recipient=client.config.active_address)

    tx_result = txer.execute(gas_budget="55865000")

    if tx_result.is_ok():
        return logger.success("Create gas object done")
    else:
        return logger.error("Create gas object error")


def init_transaction(client, merge_gas_budget: bool = False) -> SyncTransaction:
    return SyncTransaction(
        client=client,
        initial_sender=client.config.active_address,
        merge_gas_budget=merge_gas_budget)


def build_and_execute_tx(client, transaction: SyncTransaction,
                         gas_object: ObjectID = None) -> SuiTxResult:
    build = transaction.inspect_all()
    if build.error:
        return SuiTxResult(
            address=str(client.active_address),
            digest='',
            reason=build.error
        )
    else:
        try:
            if gas_object:
                rpc_result = transaction.execute(use_gas_object=gas_object, gas_budget="55865000")
            else:
                rpc_result = transaction.execute(gas_budget="55865000")
            if rpc_result.result_data:
                if rpc_result.result_data.status == 'success':
                    try:
                        return SuiTxResult(
                            address=str(client.config.active_address),
                            digest=rpc_result.result_data.digest
                        )
                    except:
                        pass
                else:
                    try:
                        return SuiTxResult(
                            address=str(client.config.active_address),
                            digest=rpc_result.result_data.digest,
                            reason=rpc_result.result_data.status
                        )
                    except:
                        pass
            else:
                try:
                    return SuiTxResult(
                        address=str(client.config.active_address),
                        digest='',
                        reason=str(rpc_result.result_string)
                    )
                except:
                    pass
        except Exception as e:
            logger.exception(e)


def merge_sui_coins_tx(client):
    merge_results = []

    zero_coins, non_zero_coins, richest_coin, _ = get_sui_coin_objects_for_merge(client)
    if len(zero_coins) and len(non_zero_coins):
        logger.info('Попытка to merge zero_coins.')
        transaction = init_transaction(client)
        transaction.merge_coins(merge_to=transaction.gas, merge_from=zero_coins)
        try:
            build_result = build_and_execute_tx(
                client,
                transaction=transaction,
                gas_object=ObjectID(richest_coin.object_id)
            )
        except:
            pass
        if build_result:
            merge_results.append(build_result)
            time.sleep(5)
        zero_coins, non_zero_coins, richest_coin, _ = get_sui_coin_objects_for_merge(client)

    if len(non_zero_coins):
        logger.info('Попытка to merge non_zero_coins.')
        transaction = init_transaction(client)
        transaction.merge_coins(merge_to=transaction.gas, merge_from=non_zero_coins)
        build_result = build_and_execute_tx(
            client,
            transaction=transaction,
            gas_object=ObjectID(richest_coin.object_id)
        )
        if build_result:
            merge_results.append(build_result)


def suilette(client):
    txer = SyncTransaction(client)
    spcoin = txer.split_coin(coin=Argument("GasCoin"), amounts=[1_000_000_000])
    address_ = str(client.config.active_address)

    txer.move_call(
        target="0xa1b6bcedb10a96173b4f3bedfd1fbdbdd50f306034b8fcc08c0b55b45554b7b0::drand_based_roulette::place_bet",
        arguments=[
            spcoin,
            SuiU8(random.randint(0, 1)),
            SuiArray([]),
            PureInput().as_input(ObjectID(get_game_object_id())),
            ObjectID('0xd6af8952697ba02000bf87e4c55cd69d54e96c7474d2a9f905e2537d9183fb5c'),
            SuiArray([SuiString(address_)]),
            SuiArray([]),
            SuiArray([]),
        ],
        type_arguments=['0x2::sui::SUI']
    )

    return transaction_run(txer)


def main():
    mnemonics = read_file('mnemonics.txt')
    random.shuffle(mnemonics)
    avg_delay = delay / len(mnemonics)
    for mnemonic in mnemonics:
        config = get_sui_config(mnemonic)
        try:
            client_ = SyncClient(config)
            while len(get_all_token(client_, "0x2::sui::SUI")) not in [0, 1]:
                merge_sui_coins_tx(client_)
            time.sleep(0.2)
            suilette(client_)
            time.sleep(random.uniform(avg_delay*0.5, avg_delay*0.9))
        except Exception as e:
            logger.error(f'{config.active_address} | Error: {e}')
            if mnemonics.count(mnemonic) <= 5:
                mnemonics.append(mnemonic)
            else:
                write_to_file('Error.txt', mnemonic)


if __name__ == '__main__':
    main()
