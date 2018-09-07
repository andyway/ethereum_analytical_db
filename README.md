# cyber•Drop core

## Installation

To build contents of this repo, use command:

```bash
./install.sh
```

Make sure you are done with everything correctly:
```bash
nosetests .
```

## Configuration

Configuration is located in config.py file. Please check this list before installation:
- INDICES - Dictionary of index names in ElasticSearch
- PARITY_HOSTS - URLs of parity APIs. You can specify block range for each URL to use different nodes for each request
- NUMBER_OF_JOBS - Size of pages received from ElasticSearch
- PROCESSED_CONTRACTS - List of contract addresses to process in several operations. All other contracts will be skipped

## Usage

### History synchronization process
To start synchronization process at first time without starting point dump, use:

```bash
python3 ./extractor.py --operation prepare-indices
python3 ./extractor.py --operation prepare-blocks
python3 ./extractor.py --operation extract-traces
python3 ./extractor.py --operation detect-contracts
python3 ./extractor.py --operation detect-contract-transactions
python3 ./extractor.py --operation extract-contracts-abi
python3 ./extractor.py --operation search-methods
python3 ./extractor.py --operation extract-prices
python3 ./extractor.py --operation parse-inputs
python3 ./extractor.py --operation extract-token-transactions
python3 ./extractor.py --operation extract-token-transactions-prices-usd
python3 ./extractor.py --operation extract-token-transactions-prices-eth
```

### Dump installation
To start from existed database dump, use:
```bash
TODO
```

### Real-time synchronization
To start real-time synchronization loop, use:

```bash
python3 ./extractor.py --operation run-loop
```

### Operations
Operation type can be selected from list below:

- prepare-indices

Prepare indices in ElasticSearch

- prepare-blocks (blocks.py)

Extract blocks with timestamps to ElasticSearch

- extract-traces (internal_transactions.py)

Starts extraction of internal ethereum transactions

- detect-contracts (contract_transactions.py)

Extract contract info (address, bytecode, author, etc) from transactions

```mermaid
graph TD
A[Begin] --> B(For transactions chunk with 'created' field)
B --> C(For transaction in chunk)
C --> D{Transaction contains 'error' field}
D --> |no|E[Extract contract with bytecode, owner, bytecode, block number, parent transaction]
E -.-> C
D -.-> |yes|C
C --> |no more transactions|F[Save extracted contracts to database]
F --> G[Save contract_created flag for transactions chunk]
G -.-> B
B --> |no more transactions|End
```

- detect-contract-transactions (contract_transactions.py)

Highlight all transactions to contracts with to_contract flag

```mermaid
graph TD
A[Begin] --> B[Get current max block from ElasticSearch]
B --> C(For contract chunk in contracts with itx_transactions_detected_block < current max block)
C --> D(For contract in chunk)
D --> E[Add contract address and itx_transactions_detected_block to request]
E --> D
D --> |no more contracts| F[Set to_contract flag to transactions by generated request before current max block]
F --> G[Save itx_transactions_detected_block = current max block for contracts]
G --> C
C --> |no more contracts|H[End]
```

- extract-contracts-abi (contracts.py)

Extract ABI description from etherscan.io for specified contracts

```mermaid
graph TD
A[Begin] 
A --> B(For contract chunk in contracts without abi_extracted flag)
B --> C(For contract in chunk)
C --> D{contract ABI in cache}
D --> |yes|F[Get ABI from cache]
D --> |no|E[Get ABI from etherscan.io]
E --> G[Save ABI to cache]
G --> H[Extract ABI]
F --> H
H --> C
C --> |no more contracts| I[Save extracted ABIs and abi_extracted flag for contracts]
I --> J[End]
```

- parse-inputs (contracts.py)

Starts input parsing. Each transaction will get a field 'decoded_input' with name of method and arguments description

```mermaid
graph TD
A[Begin] 
A --> B[Get current max block from ElasticSearch]
B --> C(For contract chunk in contracts with ABI and itx_inputs_decoded_block < current max block)
C --> D(For contract in chunk)
D --> E[Add contract address and itx_transactions_detected_block to request]
E --> D
D --> |no more contracts| F(For transactions chunk in transactions by generated request)
F --> G(For transaction in chunk)
G --> H[Extract name and params for transaction input according to ABI]
H --> G
G --> |no more transactions|I[Save extracted names and params to decoded_input field]
I --> F
F --> |no more transactions|J[Save itx_transactions_detected_block = current max block fro contracts]
J --> C
C --> |no more contracts|K[End]
```

- search-methods (contract_methods.py)

Checks if contracts contain signatures of standards-specific methods. The list of standards stored in 'standards' field.
It also saves ERC20 token names, symbols, total supply and etc.

- extract-token-transactions (token_holders.py)

Downloads list of tokens from coinmarketcap API and tries to find contracts with corresponding names in ES and then saves matching contracts into separate index. After finishing this process finds all transactions that have 'to' field equal to token contract address and also saves these transaction to separate index.

- extract-prices (token_prices.py)

Download token capitalization, ETH, BTC and USD prices from cryptocompare and coinmarketcap

- extract-token-transactions-prices-* (token_transactions_prices.py)

Set USD and ETH prices for transactions. Also set an "overflow" field - a probability that transaction value is corrupted,
i.e. is greater than market capitalization