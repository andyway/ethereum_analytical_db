from tests.test_utils import TestElasticSearch, mockify
import unittest
from transaction_fees import TransactionFees, _extract_gas_used_sync, _extract_transactions_for_blocks_sync
import httpretty
from unittest.mock import MagicMock, call, Mock, patch
import json
from web3 import Web3
import transaction_fees

class TransactionFeesTestCase(unittest.TestCase):
  def setUp(self):
    self.client = TestElasticSearch()
    self.client.recreate_index(TEST_BLOCK_INDEX)
    self.client.recreate_fast_index(TEST_TRANSACTION_INDEX, "itx")
    self.transaction_fees = TransactionFees({
      "block": TEST_BLOCK_INDEX,
      "internal_transaction": TEST_TRANSACTION_INDEX
    }, parity_host="http://localhost:8545")

  def test_iterate_blocks(self):
    self.client.index(index=TEST_BLOCK_INDEX, doc_type="b", doc={
      "number": 1
    }, id=1, refresh=True)
    self.client.index(index=TEST_BLOCK_INDEX, doc_type="b", doc={
      "number": 2,
      "transactionFees": 1
    }, id=2, refresh=True)
    self.client.index(index=TEST_BLOCK_INDEX, doc_type="b", doc={
      "number": 2,
      "transactionFees": 0
    }, id=2, refresh=True)
    blocks = next(self.transaction_fees._iterate_blocks())
    blocks = [block["_id"] for block in blocks]
    self.assertCountEqual(blocks, ['1'])

  @httpretty.activate
  def test_extract_transactions_for_blocks_sync(self):
    test_blocks = [1, 2]
    test_transactions = [{
      "hash": "0x01",
      "gasPrice": 100,
      "blockNumber": 123
    }]
    test_response = [{
      "hash": t["hash"],
      "gasPrice": hex(Web3.toWei(t["gasPrice"], "ether")),
      "blockNumber": hex(t["blockNumber"])
    } for t in test_transactions]
    httpretty.register_uri(
      httpretty.POST,
      "http://localhost:8545/",
      body=json.dumps({
        "id": 1,
        "jsonrpc": "2.0",
        "result": {
          "transactions": test_response
        }
      })
    )
    result = _extract_transactions_for_blocks_sync(test_blocks, "http://localhost:8545")
    self.assertCountEqual(result, test_transactions + test_transactions)
    assert json.loads(httpretty.last_request().body.decode("utf-8"))["params"][-1]

  def test_extract_transactions_for_blocks(self):
    blocks = ["block" + str(i) for i in range(100)]
    chunks = [["block1"], ["block2"]]
    transactions = [["transactions1"], ["transactions2"]]
    split_mock = MagicMock(return_value=chunks)
    self.transaction_fees.pool.map = MagicMock(return_value=transactions)
    with patch('utils.split_on_chunks', split_mock):
      response = self.transaction_fees._extract_transactions_for_blocks(blocks)
      split_mock.assert_called_with(blocks, 10)
      self.transaction_fees.pool.map.assert_called_with(transaction_fees._extract_transactions_for_blocks_sync, chunks)
      self.assertSequenceEqual(["transactions1", "transactions2"], response)

  @httpretty.activate
  def test_extract_gas_used_sync(self):
    test_gas_used = 21000
    test_transaction_hashes = ["0x01", "0x02"]
    httpretty.register_uri(
      httpretty.POST,
      "http://localhost:8545/",
      body=json.dumps({
        "id": 1,
        "jsonrpc": "2.0",
        "result": {
          "gasUsed": hex(test_gas_used)
        }
      })
    )
    gas_used = _extract_gas_used_sync(test_transaction_hashes, "http://localhost:8545")
    self.assertSequenceEqual(gas_used, {"0x01": test_gas_used, "0x02": test_gas_used})

  def test_extract_gas_used(self):
    hashes = ["hash" + str(i) for i in range(100)]
    chunks = [["hash1"], ["hash2"]]
    gas_used = [{"hash1": "gas1"}, {"hash2": "gas2"}]
    split_mock = MagicMock(return_value=chunks)
    self.transaction_fees.pool.map = MagicMock(return_value=gas_used)
    with patch('utils.split_on_chunks', split_mock):
      response = self.transaction_fees._extract_gas_used(hashes)
      split_mock.assert_called_with(hashes, 10)
      self.transaction_fees.pool.map.assert_called_with(transaction_fees._extract_gas_used_sync, chunks)
      self.assertSequenceEqual({"hash1": "gas1", "hash2": "gas2"}, response)

  def test_update_transactions(self):
    test_transactions = [{"hash": "0x01", "gasPrice": 10, "gasUsed": 100, "test": False}]
    test_elasticsearch_transactions = [{"hash": t["hash"], "id": t["hash"] + ".0"} for t in test_transactions]
    self.client.bulk_index(docs=test_elasticsearch_transactions, index=TEST_TRANSACTION_INDEX, doc_type="itx", refresh=True)
    self.transaction_fees._update_transactions(test_transactions)
    result = self.client.search(index=TEST_TRANSACTION_INDEX, doc_type="itx", query="_exists_:gasPrice")["hits"]['hits']
    assert len(result) == 1
    assert result[0]["_source"]["gasPrice"] == 10
    assert result[0]["_source"]["gasUsed"] == 100
    assert "test" not in result[0]["_source"]

  def test_update_empty_transactions(self):
    self.transaction_fees._update_transactions([])

  def test_count_transaction_fees(self):
    test_blocks = [1234, 1235, 1236]
    test_transactions = [{
      "blockNumber": 1234,
      "gasPrice": 1,
      "gasUsed": 2
    }, {
      "blockNumber": 1234,
      "gasPrice": 2,
      "gasUsed": 3
    }, {
      "blockNumber": 1235,
      "gasPrice": 3,
      "gasUsed": 4
    }]
    result = self.transaction_fees._count_transaction_fees(test_transactions, test_blocks)
    self.assertSequenceEqual(result, {
      1234: 1*2 + 2*3,
      1235: 3*4,
      1236: 0
    })

  def test_update_blocks(self):
    test_blocks = [{"number": 1234, "id": 1234}]
    test_transaction_fees = {1234: 30}
    self.client.bulk_index(docs=test_blocks, index=TEST_BLOCK_INDEX, doc_type="b", refresh=True)
    self.transaction_fees._update_blocks(test_transaction_fees)
    result = self.client.search(index=TEST_BLOCK_INDEX, doc_type="b", query="number:*")["hits"]['hits']
    assert len(result) == 1
    assert result[0]["_source"]["transactionFees"] == 30

  def test_extract_transaction_fees(self):
    test_blocks = [[{"_source": {"number": 1}}, {"_source": {"number": 2}}]]
    test_all_blocks = [b for l in test_blocks for b in l]
    test_all_transactions = [
      {"hash": "0x01"},
      {"hash": "0x02"}
    ]
    test_gas_used = {"0x01": 100, "0x02": 200}
    test_transaction_fees = {1: 2}
    mockify(self.transaction_fees, {
      "_iterate_blocks": MagicMock(return_value=test_blocks),
      "_extract_transactions_for_blocks": MagicMock(return_value=test_all_transactions),
      "_extract_gas_used": MagicMock(return_value=test_gas_used),
      "_count_transaction_fees": MagicMock(return_value=test_transaction_fees)
    }, "extract_transaction_fees")

    process = Mock(
      iterate=self.transaction_fees._iterate_blocks,
      extract=self.transaction_fees._extract_transactions_for_blocks,
      extract_gas=self.transaction_fees._extract_gas_used,
      update_transactions=self.transaction_fees._update_transactions,
      count_fees=self.transaction_fees._count_transaction_fees,
      update_blocks=self.transaction_fees._update_blocks
    )

    self.transaction_fees.extract_transaction_fees()

    calls = [call.iterate()]
    calls += [call.extract([block["_source"]["number"] for block in test_all_blocks])]
    calls += [call.extract_gas([transaction["hash"] for transaction in test_all_transactions])]
    calls += [call.update_transactions(test_all_transactions)]
    calls += [call.count_fees(test_all_transactions, [t["_source"]["number"] for t in test_all_blocks])]
    calls += [call.update_blocks(test_transaction_fees)]

    for transaction in test_all_transactions:
      assert transaction["gasUsed"] == test_gas_used[transaction["hash"]]

    process.assert_has_calls(calls)

TEST_BLOCK_INDEX = 'test-block'
TEST_TRANSACTION_INDEX = 'test-transaction'