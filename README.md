# bcn-pool

**English** · [Українська](README.uk.md) · [Español](README.es.md) · [Português](README.pt.md) · [Türkçe](README.tr.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md)

An open Bytecoin (BCN) mining pool with a **0% fee** and **PPLNS** payouts. It runs at <https://pool.bytecoin.community> (stratum `pool.bytecoin.community:3333`).

This is an independent community project, not affiliated with the Bytecoin founders or bcndev.

## How it works

- **Login:** your BCN address, optionally `address.worker`. The password may be `d=NNNN` for a fixed share difficulty. Algorithm `cn/0` (CryptoNight v0): XMRig, BCN Miner and CryptoNight ASICs all work.
- **Every share is recomputed** with bytecoin's own CryptoNight. The miner's claimed hash is never trusted. Junk shares get the IP banned for 10 minutes.
- **Vardiff:** each connection gets a share difficulty that aims at one share about every 15 seconds.
- **PPLNS:** a block's reward is split over the newest 2 × network difficulty of share work before it. It is credited when the block is 20 deep; a block that leaves the main chain earns nothing.
- **Payouts:** hourly, for balances of at least 0.1 BCN, in one transaction to all of them. The pool keeps nothing: the network fee of that transaction is taken from the payouts in proportion. An address that walletd cannot pay to is skipped and marked, the others are still paid.
- **Partition guard:** blocks are submitted only while an outside node (node01/node02.bytecoin.org by default) has our block two heights below our top, so a cut-off pool cannot build a private chain. The same guard is in [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum).

## Files

| File | What it is |
| --- | --- |
| `pool.py` | The pool: stratum server, share checks, vardiff, block submission, maturing, PPLNS, payouts, JSON statistics |
| `bcnaddr.py` | Address check without the node: base58, prefix (`2…` legacy, `bcnZ…` Amethyst) and Keccak checksum |
| `bcnlib.py` | ctypes wrapper for `libbcnhelper.so` (block templates, CryptoNight), shared with bcn-stratum |
| `test_pool.py` | Tests without a node: PPLNS, fee split, vardiff, share checks, login |
| `bcn-pool.service` | systemd unit |
| `web/` | The pool page; it reads `api/stats.json` and `api/miners/<address>.json` |
| `deploy/nginx-pool.conf` | nginx site for the page and the JSON |

`libbcnhelper.so` is built from bytecoin's sources in [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) (`src/`); put it next to `pool.py`.

## Run it

You need a synced `bytecoind` (RPC on `127.0.0.1:8081`) and a `walletd` for the pool wallet with RPC authorization:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Then:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` lists the settings (ports, difficulty, confirmations, PPLNS window, minimum payout).

The pool wallet holds the spend key, so keep walletd bound to localhost, the wallet file encrypted and the RPC password readable by root only, and keep its balance small: everything above the miners' balances can be moved to a cold wallet.

## Licence

LGPLv3, see `LICENSE`.
