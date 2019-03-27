import unittest
from operations.token_holders import ClickhouseTokenHolders
from unittest.mock import MagicMock, ANY, patch
from tests.test_utils import TestClickhouse
import numpy as np
import math

TRANSFER_EVENT = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
EVENT_ADDRESS_LENGTH = len("0x000000000000000000000000263627126a771fa9745763495d3975614e235298")
EVENT_VALUE_LENGTH = len("0x0000000000000000000000000000000000000000000a50161174cc045b3a8000")
TRANSACTION_ADDRESS_LENGTH = len("0x5cf04716ba20127f1e2297addcf4b5035000c9eb")


class ClickhouseTokenHoldersTestCase(unittest.TestCase):
    def setUp(self):
        self.indices = {
            "token_transaction": TEST_TOKEN_TX_INDEX,
            "event": TEST_EVENTS_INDEX,
            "contract_description": TEST_CONTRACT_INDEX
        }
        self.client = TestClickhouse()
        self.client.prepare_indices({
            "event": TEST_EVENTS_INDEX,
            "contract_description": TEST_CONTRACT_INDEX
        })
        self.client.send_sql_request("DROP TABLE IF EXISTS {}".format(self.indices["token_transaction"]))
        self.token_holders = ClickhouseTokenHolders(self.indices)
        self.token_holders.extract_token_transactions()

    def tearDown(self):
        self.client.send_sql_request("DROP TABLE IF EXISTS {}".format(self.indices["token_transaction"]))

    def test_big_hex_to_float_clickhouse(self):
        hexes = {
            ("0x0000000000000000000000000000000000000000000004bf53596c1b5f580000", 18): 22418.8,
            ("0x0000000000000000000000000000000000000000000000000000000000000001", 18): 1e-18,
            ("0x0000000000000000000000000000000010000000000000000000000000000000", 0): 0x10000000000000000000000000000000,
        }
        for (big_hex, decimals), number in hexes.items():
            self.client.bulk_index(index=TEST_EVENTS_INDEX, docs=[{
                "id": big_hex,
                "data": big_hex
            }])
            request_string = self.token_holders._generate_sql_for_data()
            sql = """
                SELECT value
                FROM (
                    SELECT
                        {} AS decimals, 
                        {}
                    FROM {}
                    WHERE id = '{}'
                    LIMIT 1
                )
            """.format(decimals, request_string, TEST_EVENTS_INDEX, big_hex)
            result = self.client.send_sql_request(sql)
            self.assertAlmostEqual(result, number)

    def _create_transfer_event(self, id, from_address, to_address, value, address):
        return {
            "id": id,
            "transactionHash": id,
            "blockNumber": 10,
            "topics": [
                TRANSFER_EVENT,
                "{0:#0{1}x}".format(int(from_address, 0), EVENT_ADDRESS_LENGTH),
                "{0:#0{1}x}".format(int(to_address, 0), EVENT_ADDRESS_LENGTH),
            ],
            "data": "{0:#0{1}x}".format(value * (10 ** 18), EVENT_VALUE_LENGTH),
            "address": address,
        }

    def test_extract_token_transactions_from_erc20_transfer_events(self):
        test_contracts = [{
            "id": "0x01",
            "decimals": 17
        }]
        test_events = [
            self._create_transfer_event("0x1.0", "0x1", "0x2", 100, "0x01"),
            {
                "id": "0x1.1",
                "topics": [
                    "0x"
                ],
                "data": '0x',
                "address": '0x01',
                "blockNumber": 1,
                "transactionHash": "0x"
            }
        ]
        test_token_transactions = [{
            "from": "{0:#0{1}x}".format(1, TRANSACTION_ADDRESS_LENGTH),
            "to": "{0:#0{1}x}".format(2, TRANSACTION_ADDRESS_LENGTH),
            "transactionHash": "0x1.0",
            "blockNumber": 10,
            "value": 1000
        }]
        test_transactions_ids = ["0x1.0"]
        self.client.bulk_index(index=TEST_CONTRACT_INDEX, docs=test_contracts)
        self.client.bulk_index(index=TEST_EVENTS_INDEX, docs=test_events)
        token_transactions = self.client.search(index=TEST_TOKEN_TX_INDEX,
                                                fields=["id", "to", "from", "value", "blockNumber", "transactionHash"])
        self.assertCountEqual([transaction["_id"] for transaction in token_transactions], test_transactions_ids)
        self.assertCountEqual([transaction["_source"] for transaction in token_transactions], test_token_transactions)

    def test_extract_token_transactions_if_exists(self):
        self.token_holders.extract_token_transactions()

    def test_extract_token_transactions_ignore_duplicates(self):
        test_contract = {
            "id": "0x01",
            "decimals": 18,
        }
        test_event = self._create_transfer_event("0x1.0", "0x1", "0x2", 100, "0x01")
        self.client.bulk_index(index=TEST_CONTRACT_INDEX, docs=[test_contract])
        self.client.bulk_index(index=TEST_EVENTS_INDEX, docs=[test_event, test_event])
        count = self.client.count(index=TEST_TOKEN_TX_INDEX)
        assert count == 1

    def test_extract_contract_addresses_recreate(self):
        test_contract = {
            "id": "0x01",
            "decimals": 18,
        }
        self.client.send_sql_request("DROP TABLE {}".format(TEST_TOKEN_TX_INDEX))
        self.client.bulk_index(index=TEST_CONTRACT_INDEX, docs=[test_contract])
        self.client.bulk_index(index=TEST_EVENTS_INDEX, docs=[
            self._create_transfer_event("0x1.0", "0x1", "0x2", 100, "0x01")
        ])
        self.token_holders.extract_token_transactions()
        count = self.client.count(index=TEST_TOKEN_TX_INDEX)
        assert count == 1


TEST_CONTRACT_INDEX = 'test_ethereum_contracts'
TEST_ITX_INDEX = 'test_ethereum_internal_txs'
TEST_TOKEN_TX_INDEX = 'test_token_txs'
TEST_BLOCK_INDEX = 'test_block'
TEST_EVENTS_INDEX = 'test_ethereum_events'
TEST_EVENT_INPUTS_INDEX = 'test_ethereum_events_inputs'

TEST_TOKEN_ADDRESSES = ['0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d',
                        '0xa74476443119a942de498590fe1f2454d7d4ac0d'
                        ]
TEST_PARENT_TXS = ['0x8a634bd8b381c09eec084fd7df6bdce03ccbc92f247f59d4fcc22e02131c0158',
                   '0xf349e35ce06112455d01e63ee2d447f626a88b646749c1cf2bffe474afeb703a']
TEST_TOKEN_NAMES = ['Aeternity', 'Golem Network Token']
TEST_TOKEN_SYMBOLS = ['AE', 'GNT']
TEST_TOKEN_TXS = [
    {'from': '0x6b25d0670a34c1c7b867cd9c6ad405aa1759bda0', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d',
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'},
                                  {'type': 'uint256', 'value': '2266000000000000000000'}]}, 'blockNumber': 5635149,
     'hash': '0xd8f583bcb81d12dc2d3f18e0a015ef0f6e71c177913ef8f251e37b6e4f7f1f26'},
    {'from': '0xc917e19946d64aa31d1aeacb516bae2579995aa9', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d',
     'error': 'Out of gas', 'decoded_input': {'name': 'transferFrom', 'params': [
        {'type': 'address', 'value': '0xc917e19946d64aa31d1aeacb516bae2579995aa9'},
        {'type': 'address', 'value': '0x4e6b129bbb683952ed1ec935c778d74a77b352ce'},
        {'type': 'uint256', 'value': '356245680000000000000'}]}, 'blockNumber': 5635142,
     'hash': '0xca811570188b2e5d186da8292eda7e0bf7dde797a68d90b9ac2e014e321a94b2'},
    {'from': '0x6b25d0670a34c1c7b867cd9c6ad405aa1759bda0', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d',
     'blockNumber': 5635149, 'hash': '0x2497b3dcbce36c4d2cbe42931fa160cb39703ae5487bf73044520410101e7c8c'},
    {'from': '0x892ce7dbc4a0efbbd5933820e53d2c945ef9f722', 'to': '0x51ada638582e51c931147c9abd2a6d63bc02e337',
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be'},
                                  {'type': 'uint256', 'value': '2294245680000000000000'}]}, 'blockNumber': 5632141,
     'hash': '0x4188f8c914b5f58f911674ff766d45da2a19c1375a8487841dc4bdb5214c3aa2'},
    {'from': '0x930aa9a843266bdb02847168d571e7913907dd84', 'to': '0xa74476443119a942de498590fe1f2454d7d4ac0d',
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0xc18118a2976a9e362a0f8d15ca10761593242a85'},
                                  {'type': 'uint256', 'value': '2352000000000000000000'}]}, 'blockNumber': 5235141,
     'hash': '0x64778c57705c4bad6b2ef8fd485052faf5c40d2197a44eb7105ce71244ded043'}
]
TEST_TOKEN_ITXS = [
    {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0x", "gasUsed": "0x0",
     "type": "call", "gas": "0x8fc", "traceAddress": [2], "transactionPosition": 42, "value": "0x13b4da79fd0e0000",
     "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235,
     "from": "0xf04436b2edaa1b777045e1eefc6dba8bd2aebab8", "callType": "call", "output": "0x",
     "transactionHash": "0x366c6344bdb4cb1bb8cfbce5770419b03f49d631d5803e5fbcf8de9b8f1a5d66.4",
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'},
                                  {'type': 'uint256', 'value': '2266000000000000000000'}]}},
    {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0x", "gasUsed": "0x0",
     "type": "call", "gas": "0x8fc", "traceAddress": [0, 0], "transactionPosition": 89, "value": "0x1991d2e42bc5c00",
     "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235,
     "from": "0xa36ae0f959046a18d109dc5b1fb8df655cf0aa81", "callType": "call", "output": "0x",
     "transactionHash": "0xce37439c6809ca9d1b1d5707c7df34ceec1e4e472f0ca07c87fa449a93b02431.4",
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'},
                                  {'type': 'uint256', 'value': '2266000000000000000000'}]}},
    {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0xc281d19e",
     "gasUsed": "0x5a4", "type": "call", "gas": "0x303d8", "traceAddress": [1], "transactionPosition": 102,
     "value": "0x0", "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235,
     "from": "0xd91e45416bfbbec6e2d1ae4ac83b788a21acf583", "callType": "call",
     "output": "0x00000000000000000000000026588a9301b0428d95e6fc3a5024fce8bec12d51",
     "transactionHash": "0x04692fb0a2d1a9c8b6ea8cfc643422800b81da50df1578f3494aef0ef9be6009.4",
     'decoded_input': {'name': 'transfer',
                       'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'},
                                  {'type': 'uint256', 'value': '2266000000000000000000'}]}}
]

TEST_MINT_ADDRESSES = {
    "blockTimestamp": "2017-12-26T22:39:56",
    "from": "0xec4f63c53223c54cf0eb7a57c2f984ab5e5bfdac",
    "creates": None,
    "input": "0xf190ac5f00000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000de0b6b3a7640000000000000000000000000000000000000000000000000000000000000000009600000000000000000000000036230df54a0265a96af387dd23bacc2a58cfbd9a0000000000000000000000002fd6320ee113b83f0a4636dece0e6330fb1ca605000000000000000000000000ba9e442d7357984815716bfcb7471f3b349b2618000000000000000000000000ee056a44e39219de1d0027cbe81756d8cf26da49000000000000000000000000d0926f304d8e101bc9366345213ce45ee579065d00000000000000000000000037254d31a6bec7c5789f68287aac897d7ca3244d00000000000000000000000043ba366eb497fa986eb2031d01e1e9a74054d318000000000000000000000000aa6aa499b8241ae0699fe4346e366c9cf7bc6e700000000000000000000000008a39c67843d18384960b0c65bf5db46fdadbde84000000000000000000000000aec6372d9d80f4e6e04e5195e5e778a65647ae9e0000000000000000000000004125e658640d5b0a86441fc10ea02f9230f9b8e7000000000000000000000000c11b7067acaac311d2b77b91b8655663ba8731990000000000000000000000009050ebc8e2b0b6a123634d0fad9a44b35aef548a000000000000000000000000be59e1a83508c70b2cf0bf7415c3512cabbbf05200000000000000000000000064dcee549acf529da0605e8736beed64276bd755000000000000000000000000223eb313426ff2a6fe8e7683020c54bf7930521d000000000000000000000000fe7c793ed4f16b6d05ec763d98389590b0c812e1000000000000000000000000071bd3aa323b82df25b27407d314f104e69deaac000000000000000000000000c06d5cc009a7ade2b08fc49118e9ea690a6994f80000000000000000000000003ed01da8472800e6213931d624dbec3c3e4eb0cf0000000000000000000000006eb60cf761d51500d31250c3a3bd6e2ce6d21377000000000000000000000000879019114f873e291c94866af98e87382188e38b0000000000000000000000008e563f01316be4d44c084030e7ff896afe450ad9000000000000000000000000fbcd0645dfe99fb6470b2df617c4df78fb0582090000000000000000000000007a1f999a9501d50861cd54bd6dd2a001eb6ed80700000000000000000000000046eb3f5e97db81cc6c9d32102ed01614b80c2af9000000000000000000000000ab4117dfbcdfc8e8966fc5128d2e1d4c4807580f00000000000000000000000061dc365e74b318187a07970f68001c36e2613da00000000000000000000000006bbfcc3d25799fd4e9c4fd17d3fd350a57665f160000000000000000000000004260e9cffe03787181ebc152f5fd00bfef3f52cf000000000000000000000000c1608e55471cc27ec5437f0ae2355315473f841d00000000000000000000000064d603faeb69451e1cb6bc253d76c92048875a13000000000000000000000000c4dd4c7eb15bfd48aa35509dd390e2f014227bea0000000000000000000000005e7d4f04d0cd0e57a8d28cf3b56f8e1b478b7bbf00000000000000000000000036b68ca8c8f8e9b4ec7e083773bc19e485768e630000000000000000000000007aa76d0c2bee3a7995b8a798fcd56ee32c0b56050000000000000000000000005542803080981f61a0a859bf41065ba1ac1475e0000000000000000000000000d003436e741a706f683647374896a9ff5891823000000000000000000000000089f6aaa4f58211aaa24c87010670688ef3374f80000000000000000000000000534757e5f5d980e73d837c786a58a8abf2691d100000000000000000000000000061533a3829c585db7ecb7d3cf9651d31c1bc23000000000000000000000000810b326b15856eca9b3b083182997ae0d181f7960000000000000000000000008824885c9a56eb7b63bd517d542626d12a4e55010000000000000000000000006292bda9278e3372acf3114fd8a4de9271625578000000000000000000000000324e45fb5bb54982c7ee084ca54277d966880d2f00000000000000000000000016893e10b99a59afd2c60331e0b49241d4d4d7cc00000000000000000000000080ea495e24eb7a8a3f6564c46fe0715578c74688000000000000000000000000d1ee5ea14f1edfe1efd1c39e97bdd4b7df3f6dcc0000000000000000000000000e9e0c5723c1dbf7120ea52cb81ab1f08b5a452b000000000000000000000000f1775a48a3488edb81034e25dc9772c83c74df120000000000000000000000003df3b28a46859176078336197a9e3d436283efb2000000000000000000000000bb1396676bdce688a2050ad1a10f2f73f60f2f7300000000000000000000000082da55c051b977a84b3deaec3169c478f6e3e2a90000000000000000000000001dcf5557d81c9547e8cd86133c7e66471f121e7500000000000000000000000037ed9d4025c65e12706e5c5e2d119ff47da9b78f000000000000000000000000faa43e0faabd8bc859be9b85db079a818d77e604000000000000000000000000a2262ca10a472b73d8a640d5c7dd71d03775238f000000000000000000000000e5bb2be67ad6ea88b9e3effa9b214cdfd6756ee70000000000000000000000006ed165d527127a7e20d658ef6d7fa7997fd4f97c0000000000000000000000006e7f248c959f4b364adf9b0fcfd6340dfbaaec1c000000000000000000000000ee665a8abfc6c02dade26072f0b6855f61c561a40000000000000000000000008b52ceb9f1004eb7b60f369e323581340339cf75000000000000000000000000cc852edb0c0115f03a0fd9aeff48bfc101914b2e000000000000000000000000200c601aa7449aa2cc2ccbd5f46645941654cde100000000000000000000000043f16f609ab45e89b95985d3ef4a28de97011627000000000000000000000000b7a23cc3e8c61f4aaef5f6a17173a29fbf2da628000000000000000000000000b5a05c6e7ea3ddcf4a42cfebb097796a2afd47da0000000000000000000000001323367b36f387319494c2c37b60cd482218473b000000000000000000000000e87897b164f841caf4b72b672b0422707d13833d0000000000000000000000004ec5f054ee87c51e4321f2f113e0337bbb314b6d00000000000000000000000063b21a269a7bbd63cf53997c43a7a5a95e40062400000000000000000000000000a3d158cf962f698c50b9402ebfb0e40c928536000000000000000000000000e630b30bc224c9892d7547569f1e16ffd501d47300000000000000000000000000fab3e776084660815773dbb5f56b05f78afd9c0000000000000000000000007153d3412ae77673100917f0f27b280de4befd2e0000000000000000000000002955a2d35904914637d37b4b290d3418c81cdc0c00000000000000000000000000a539248b104621fa75d171c33692425975dc32000000000000000000000000a8ebcfb7f8a7a9d6721cbf15a154986a2df909cb00000000000000000000000022b080ce0119f82d938524e61be35d03e3521efd0000000000000000000000006d79e413646214530e2b6fd39cb4d4f8e8263f660000000000000000000000001a1a57dd243f74ea2e594795ffda2fb80bf89a1a000000000000000000000000f40acf3e0a12e2534d1f2ccbcff78ad610defbf0000000000000000000000000f5a1deec0bea778b80547ab8eca779eb99b0280a000000000000000000000000fcec74b7ecba248ee727c3a8beb62a4e85554b060000000000000000000000007d424336be9f81982a08c8338c804ef8617f843900000000000000000000000084466fe4857177b2f11692ff198ad289408db13f000000000000000000000000a2afd1fa1e188457a9c6db1bd50424250eb784ce000000000000000000000000a66f03dc235473642d0322d50716d5a25d4ba1460000000000000000000000000cb5428bf8f8cdda4eeb46d4db8094602c7f369a000000000000000000000000552de0a5966d13f4a59719dd4d032651d1aecd97000000000000000000000000b8138dc6f1a1c868d319684b5f62256d081cf9d2000000000000000000000000b49fcc248a2bba533527f4e06e96b5c2182844c5000000000000000000000000c530c704740f865280c37b471b92f9790a695b8c000000000000000000000000abc70d6044edaff29e7c153005d8286a3847d7dc000000000000000000000000ecc874511bb8077445a757e9540b30dfe69dfd9f000000000000000000000000a65d5f1486e8ea401a20e337ab135c64f357de48000000000000000000000000c44bd46afbbc9c41fb76eb064598db39c9f52b6c0000000000000000000000007a08ed303cdea0a4809158740335e7759cf4da2600000000000000000000000024f57d0be8fb9f9ef4f1e912dfc4f8ef06fdcce7000000000000000000000000a69eb8efbbb5c4fd4092d110a023773ba23509f600000000000000000000000062d4f2b9e56b6b4111b961dd41eea98667831be8000000000000000000000000b10ce34857128de7346944d9050f107c131e279f000000000000000000000000823538ef6fbc3e8944138a92380bf1217726907a000000000000000000000000539cdb209674378507ee586a06f2fb4b2f1b594900000000000000000000000080e6db644c334f73966127b485734370a31381b9000000000000000000000000d47b4cc77d53a6785c969fe99d7379801148c3780000000000000000000000001d36c5d2f77280376b857ba83a28d7a3ed7e580f000000000000000000000000c2974033b2488690b521c5d32c6b7993e40441d2000000000000000000000000c6ad60ea09f61d1d42eca99a31f853af86e141f60000000000000000000000006b7580d3bc2ee3e4dbf82c426625dbcecc0342140000000000000000000000009ca6404f7eaedc3aefe9839d78cab5eaceb84e8400000000000000000000000060c4775b2377bca9d7ff724606aa17fdba038ce6000000000000000000000000ac9bb6a6b131d9529d05dc8728e432167eaa9e680000000000000000000000008a80aa5835c08fed3a7d8820f02c17babdb2c0510000000000000000000000009ab74e8494bce9219377675b5f50514b807f578c00000000000000000000000044f303f4847405176981e2f3e773773df5d3fc420000000000000000000000009b21e11514c418d3279e0a8ea41cb8618cc39a1500000000000000000000000080ec51509ec3644e201b15e578246890727edbca00000000000000000000000012a2aa3e5898426f6ae6def1a7915d82f0f5113400000000000000000000000028bc4fcc5dcd62abbbd140e7364f73575bf8c2c3000000000000000000000000c1535158cfb9352bf6a441373afb1737259ec403000000000000000000000000eac45e4aa47eef6810ad75d930e83fed544024f30000000000000000000000000de98266d8021090068f15b466c6ae389b5b0744000000000000000000000000bf6b500ad8df9cdd777655d6faa97fd9f475748a000000000000000000000000f406317925ad6a9ea40cdf40cc1c9b0dd65ca10c000000000000000000000000c88fcf7668e5fa3b180e964dcc990896e36bcd39000000000000000000000000f22b904c4926a925825deb75d9a9645d10f788160000000000000000000000008eca04e62b5887fbc0862884919f6a27677260b90000000000000000000000001c1ef062943fc4f0777b50ee98e794ddf16b94b2000000000000000000000000301ab3ad422ee85447b96d93e7ee710925fc6e6b0000000000000000000000004c2230715e37675957233227b78784e8ff6fc4750000000000000000000000008b163f35b076c53e44d0975b3c07a27e7364153f00000000000000000000000005fc91878c77a6d49116bc5451afc7bb8ee904f3000000000000000000000000a98887cd3504c8a5f39e0fafc21978fef8d483c100000000000000000000000055772ec91f52b084d752ff9daaa41af713febb280000000000000000000000004fbd4432a6cc4606bdaa83f7233da29cfbf3a4c40000000000000000000000008a35be53529cd6ebfeb5033a89b42995123b376f000000000000000000000000bee3b5acece21526ebb14e983441f787d5f192e7000000000000000000000000cafaac75f9d2f91dd92dc865d0c98c0aff33982e00000000000000000000000059e339b921ccb69f6e00663126af7888862f6b1c000000000000000000000000dacf6478b90a55a2e054960134f4ea2378074f180000000000000000000000003c1f833e7cc6b37cc9145103106a0957d6e0ea9d00000000000000000000000053e53a6f9ec5a9d02993a82042cc96c78c8505200000000000000000000000001538f85a6241f7470464b6469094174b1310e040000000000000000000000000a31b5816c1c461069e4bcd42ea8ca00fa0a257d6000000000000000000000000e174f334e6874196f37d1df019b3177ed5c0881d000000000000000000000000edc148759dfdffa3eeff01ea64b2abf20642799f0000000000000000000000008dcf18eca7b6a5afd17f0dba07c94e53d9f4117b000000000000000000000000cfebcd59bccbe2549eadc1e7bbcffd0cee699ff10000000000000000000000004cb8b2421df9878f61300e64765fc70eb23bf329",
    "transactionIndex": 26,
    "hash": "0x62e2f27cd5ada06ec9a7a4cb351d51ce697c07beadaeb1e30f5e2e2e9031ba58",
    "blockNumber": 4802804,
    "value": 0.0,
    "to": "0x1234567461d3f8db7496581774bd869c83d51c93",
    "decoded_input": {
        "name": "mintToAddresses",
        "params": [
            {
                "type": "address[]",
                "value": "['0x36230df54a0265a96af387dd23bacc2a58cfbd9a', '0x2fd6320ee113b83f0a4636dece0e6330fb1ca605', '0xba9e442d7357984815716bfcb7471f3b349b2618', '0xee056a44e39219de1d0027cbe81756d8cf26da49', '0xd0926f304d8e101bc9366345213ce45ee579065d', '0x37254d31a6bec7c5789f68287aac897d7ca3244d', '0x43ba366eb497fa986eb2031d01e1e9a74054d318', '0xaa6aa499b8241ae0699fe4346e366c9cf7bc6e70', '0x8a39c67843d18384960b0c65bf5db46fdadbde84', '0xaec6372d9d80f4e6e04e5195e5e778a65647ae9e', '0x4125e658640d5b0a86441fc10ea02f9230f9b8e7', '0xc11b7067acaac311d2b77b91b8655663ba873199', '0x9050ebc8e2b0b6a123634d0fad9a44b35aef548a', '0xbe59e1a83508c70b2cf0bf7415c3512cabbbf052', '0x64dcee549acf529da0605e8736beed64276bd755', '0x223eb313426ff2a6fe8e7683020c54bf7930521d', '0xfe7c793ed4f16b6d05ec763d98389590b0c812e1', '0x071bd3aa323b82df25b27407d314f104e69deaac', '0xc06d5cc009a7ade2b08fc49118e9ea690a6994f8', '0x3ed01da8472800e6213931d624dbec3c3e4eb0cf', '0x6eb60cf761d51500d31250c3a3bd6e2ce6d21377', '0x879019114f873e291c94866af98e87382188e38b', '0x8e563f01316be4d44c084030e7ff896afe450ad9', '0xfbcd0645dfe99fb6470b2df617c4df78fb058209', '0x7a1f999a9501d50861cd54bd6dd2a001eb6ed807', '0x46eb3f5e97db81cc6c9d32102ed01614b80c2af9', '0xab4117dfbcdfc8e8966fc5128d2e1d4c4807580f', '0x61dc365e74b318187a07970f68001c36e2613da0', '0x6bbfcc3d25799fd4e9c4fd17d3fd350a57665f16', '0x4260e9cffe03787181ebc152f5fd00bfef3f52cf', '0xc1608e55471cc27ec5437f0ae2355315473f841d', '0x64d603faeb69451e1cb6bc253d76c92048875a13', '0xc4dd4c7eb15bfd48aa35509dd390e2f014227bea', '0x5e7d4f04d0cd0e57a8d28cf3b56f8e1b478b7bbf', '0x36b68ca8c8f8e9b4ec7e083773bc19e485768e63', '0x7aa76d0c2bee3a7995b8a798fcd56ee32c0b5605', '0x5542803080981f61a0a859bf41065ba1ac1475e0', '0xd003436e741a706f683647374896a9ff58918230', '0x89f6aaa4f58211aaa24c87010670688ef3374f80', '0x534757e5f5d980e73d837c786a58a8abf2691d10', '0x0061533a3829c585db7ecb7d3cf9651d31c1bc23', '0x810b326b15856eca9b3b083182997ae0d181f796', '0x8824885c9a56eb7b63bd517d542626d12a4e5501', '0x6292bda9278e3372acf3114fd8a4de9271625578', '0x324e45fb5bb54982c7ee084ca54277d966880d2f', '0x16893e10b99a59afd2c60331e0b49241d4d4d7cc', '0x80ea495e24eb7a8a3f6564c46fe0715578c74688', '0xd1ee5ea14f1edfe1efd1c39e97bdd4b7df3f6dcc', '0x0e9e0c5723c1dbf7120ea52cb81ab1f08b5a452b', '0xf1775a48a3488edb81034e25dc9772c83c74df12', '0x3df3b28a46859176078336197a9e3d436283efb2', '0xbb1396676bdce688a2050ad1a10f2f73f60f2f73', '0x82da55c051b977a84b3deaec3169c478f6e3e2a9', '0x1dcf5557d81c9547e8cd86133c7e66471f121e75', '0x37ed9d4025c65e12706e5c5e2d119ff47da9b78f', '0xfaa43e0faabd8bc859be9b85db079a818d77e604', '0xa2262ca10a472b73d8a640d5c7dd71d03775238f', '0xe5bb2be67ad6ea88b9e3effa9b214cdfd6756ee7', '0x6ed165d527127a7e20d658ef6d7fa7997fd4f97c', '0x6e7f248c959f4b364adf9b0fcfd6340dfbaaec1c', '0xee665a8abfc6c02dade26072f0b6855f61c561a4', '0x8b52ceb9f1004eb7b60f369e323581340339cf75', '0xcc852edb0c0115f03a0fd9aeff48bfc101914b2e', '0x200c601aa7449aa2cc2ccbd5f46645941654cde1', '0x43f16f609ab45e89b95985d3ef4a28de97011627', '0xb7a23cc3e8c61f4aaef5f6a17173a29fbf2da628', '0xb5a05c6e7ea3ddcf4a42cfebb097796a2afd47da', '0x1323367b36f387319494c2c37b60cd482218473b', '0xe87897b164f841caf4b72b672b0422707d13833d', '0x4ec5f054ee87c51e4321f2f113e0337bbb314b6d', '0x63b21a269a7bbd63cf53997c43a7a5a95e400624', '0x00a3d158cf962f698c50b9402ebfb0e40c928536', '0xe630b30bc224c9892d7547569f1e16ffd501d473', '0x00fab3e776084660815773dbb5f56b05f78afd9c', '0x7153d3412ae77673100917f0f27b280de4befd2e', '0x2955a2d35904914637d37b4b290d3418c81cdc0c', '0x00a539248b104621fa75d171c33692425975dc32', '0xa8ebcfb7f8a7a9d6721cbf15a154986a2df909cb', '0x22b080ce0119f82d938524e61be35d03e3521efd', '0x6d79e413646214530e2b6fd39cb4d4f8e8263f66', '0x1a1a57dd243f74ea2e594795ffda2fb80bf89a1a', '0xf40acf3e0a12e2534d1f2ccbcff78ad610defbf0', '0xf5a1deec0bea778b80547ab8eca779eb99b0280a', '0xfcec74b7ecba248ee727c3a8beb62a4e85554b06', '0x7d424336be9f81982a08c8338c804ef8617f8439', '0x84466fe4857177b2f11692ff198ad289408db13f', '0xa2afd1fa1e188457a9c6db1bd50424250eb784ce', '0xa66f03dc235473642d0322d50716d5a25d4ba146', '0x0cb5428bf8f8cdda4eeb46d4db8094602c7f369a', '0x552de0a5966d13f4a59719dd4d032651d1aecd97', '0xb8138dc6f1a1c868d319684b5f62256d081cf9d2', '0xb49fcc248a2bba533527f4e06e96b5c2182844c5', '0xc530c704740f865280c37b471b92f9790a695b8c', '0xabc70d6044edaff29e7c153005d8286a3847d7dc', '0xecc874511bb8077445a757e9540b30dfe69dfd9f', '0xa65d5f1486e8ea401a20e337ab135c64f357de48', '0xc44bd46afbbc9c41fb76eb064598db39c9f52b6c', '0x7a08ed303cdea0a4809158740335e7759cf4da26', '0x24f57d0be8fb9f9ef4f1e912dfc4f8ef06fdcce7', '0xa69eb8efbbb5c4fd4092d110a023773ba23509f6', '0x62d4f2b9e56b6b4111b961dd41eea98667831be8', '0xb10ce34857128de7346944d9050f107c131e279f', '0x823538ef6fbc3e8944138a92380bf1217726907a', '0x539cdb209674378507ee586a06f2fb4b2f1b5949', '0x80e6db644c334f73966127b485734370a31381b9', '0xd47b4cc77d53a6785c969fe99d7379801148c378', '0x1d36c5d2f77280376b857ba83a28d7a3ed7e580f', '0xc2974033b2488690b521c5d32c6b7993e40441d2', '0xc6ad60ea09f61d1d42eca99a31f853af86e141f6', '0x6b7580d3bc2ee3e4dbf82c426625dbcecc034214', '0x9ca6404f7eaedc3aefe9839d78cab5eaceb84e84', '0x60c4775b2377bca9d7ff724606aa17fdba038ce6', '0xac9bb6a6b131d9529d05dc8728e432167eaa9e68', '0x8a80aa5835c08fed3a7d8820f02c17babdb2c051', '0x9ab74e8494bce9219377675b5f50514b807f578c', '0x44f303f4847405176981e2f3e773773df5d3fc42', '0x9b21e11514c418d3279e0a8ea41cb8618cc39a15', '0x80ec51509ec3644e201b15e578246890727edbca', '0x12a2aa3e5898426f6ae6def1a7915d82f0f51134', '0x28bc4fcc5dcd62abbbd140e7364f73575bf8c2c3', '0xc1535158cfb9352bf6a441373afb1737259ec403', '0xeac45e4aa47eef6810ad75d930e83fed544024f3', '0x0de98266d8021090068f15b466c6ae389b5b0744', '0xbf6b500ad8df9cdd777655d6faa97fd9f475748a', '0xf406317925ad6a9ea40cdf40cc1c9b0dd65ca10c', '0xc88fcf7668e5fa3b180e964dcc990896e36bcd39', '0xf22b904c4926a925825deb75d9a9645d10f78816', '0x8eca04e62b5887fbc0862884919f6a27677260b9', '0x1c1ef062943fc4f0777b50ee98e794ddf16b94b2', '0x301ab3ad422ee85447b96d93e7ee710925fc6e6b', '0x4c2230715e37675957233227b78784e8ff6fc475', '0x8b163f35b076c53e44d0975b3c07a27e7364153f', '0x05fc91878c77a6d49116bc5451afc7bb8ee904f3', '0xa98887cd3504c8a5f39e0fafc21978fef8d483c1', '0x55772ec91f52b084d752ff9daaa41af713febb28', '0x4fbd4432a6cc4606bdaa83f7233da29cfbf3a4c4', '0x8a35be53529cd6ebfeb5033a89b42995123b376f', '0xbee3b5acece21526ebb14e983441f787d5f192e7', '0xcafaac75f9d2f91dd92dc865d0c98c0aff33982e', '0x59e339b921ccb69f6e00663126af7888862f6b1c', '0xdacf6478b90a55a2e054960134f4ea2378074f18', '0x3c1f833e7cc6b37cc9145103106a0957d6e0ea9d', '0x53e53a6f9ec5a9d02993a82042cc96c78c850520', '0x1538f85a6241f7470464b6469094174b1310e040', '0xa31b5816c1c461069e4bcd42ea8ca00fa0a257d6', '0xe174f334e6874196f37d1df019b3177ed5c0881d', '0xedc148759dfdffa3eeff01ea64b2abf20642799f', '0x8dcf18eca7b6a5afd17f0dba07c94e53d9f4117b', '0xcfebcd59bccbe2549eadc1e7bbcffd0cee699ff1', '0x4cb8b2421df9878f61300e64765fc70eb23bf329']"
            },
            {
                "type": "uint256",
                "value": "1000000000000000000"
            }
        ]
    },
    "output": "0x",
    "id": "0x62e2f27cd5ada06ec9a7a4cb351d51ce697c07beadaeb1e30f5e2e2e9031ba58"
}
