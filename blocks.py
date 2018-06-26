from config import INDICES, PARITY_HOSTS
from custom_elastic_search import CustomElasticSearch
import requests
import json

class Blocks:
  def __init__(self,
               indices=INDICES,
               elasticsearch_host="http://localhost:9200",
               parity_host=PARITY_HOSTS[0][-1]
               ):
    self.indices = indices
    self.client = CustomElasticSearch(elasticsearch_host)
    self.parity_host = parity_host

  def _get_max_parity_block(self):
    response = requests.get(self.parity_host, data=json.dumps({
      "id": 1,
      "jsonrpc": "2.0",
      "method": "eth_blockNumber",
      "params": []
    }), headers={
      "Content-Type": "application/json"
    }).json()
    return int(response["result"], 0)

  def _get_max_elasticsearch_block(self):
    aggregation = {
      "size": 0,
      "aggs": {
        "max_block": {
          "max": {
            "field": "number"
          }
        }
      }
    }
    result = self.client.send_request("GET", [self.indices["block"], "_search"], aggregation, {})
    return int(result["aggregations"]["max_block"]["value"])

  def _create_blocks(self, start, end):
    docs = [{"number": i, 'id': i} for i in range(start, end + 1)]
    if docs:
      self.client.bulk_index(docs=docs, index=self.indices["block"], doc_type="b", refresh=True)

  def create_blocks(self):
    max_parity_block = self._get_max_parity_block()
    max_elasticsearch_block = self._get_max_elasticsearch_block()
    self._create_blocks(max_elasticsearch_block + 1, max_parity_block)
