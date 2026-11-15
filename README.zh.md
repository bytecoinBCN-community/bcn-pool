# bcn-pool

[English](README.md) · [Українська](README.uk.md) · [Español](README.es.md) · [Português](README.pt.md) · [Türkçe](README.tr.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · **中文**

开放的 Bytecoin（BCN）矿池，**0% 手续费**，**PPLNS** 分配。运行于 <https://pool.bytecoin.community>（stratum `pool.bytecoin.community:3333`）。

这是社区的独立项目，与 Bytecoin 创始人及 bcndev 无关。

## 工作方式

- **用户名：**你的 BCN 地址，也可写成 `地址.worker`。密码可以是 `d=NNNN`，用于固定 share 难度。算法 `cn/0`（CryptoNight v0）：XMRig、BCN Miner 和 CryptoNight ASIC 都可使用。
- **每个 share 都会重新计算**，使用 bytecoin 自身代码中的 CryptoNight。矿池从不相信矿工声称的哈希。提交垃圾 share 的 IP 会被封禁 10 分钟。
- **Vardiff：**每个连接获得的 share 难度以大约每 15 秒一个 share 为目标。
- **PPLNS：**区块奖励按该区块之前最新的、相当于 2 × 网络难度的工作量分配。区块达到 20 个确认后记入余额；离开主链的区块没有收益。
- **支付：**每小时一次，余额达到 0.1 BCN 即支付，所有人合并在一笔交易中。矿池不留任何收入：这笔交易的网络手续费按比例从各笔支付中扣除。walletd 无法付款的地址会被跳过并标记，其他人照常收款。
- **分叉保护：**只有当外部节点（默认 node01/node02.bytecoin.org）拥有我们链顶以下两个高度的那个区块时，才会提交区块，因此与网络断开的矿池无法构建私有链。[bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) 中有同样的保护。

## 文件

| 文件 | 说明 |
| --- | --- |
| `pool.py` | 矿池本身：stratum 服务器、share 校验、vardiff、提交区块、等待成熟、PPLNS、支付、JSON 统计 |
| `bcnaddr.py` | 无需节点的地址检查：base58、前缀（`2…` legacy，`bcnZ…` Amethyst）和 Keccak 校验和 |
| `bcnlib.py` | `libbcnhelper.so` 的 ctypes 封装（区块模板、CryptoNight），与 bcn-stratum 共用 |
| `test_pool.py` | 无需节点的测试：PPLNS、手续费分摊、vardiff、share 校验、登录 |
| `bcn-pool.service` | systemd 单元 |
| `web/` | 矿池页面；读取 `api/stats.json` 和 `api/miners/<地址>.json` |
| `deploy/nginx-pool.conf` | 页面和 JSON 的 nginx 站点配置 |

`libbcnhelper.so` 由 [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) 中的 bytecoin 源码（`src/`）编译而成；请把它放在 `pool.py` 旁边。

## 运行

需要已同步的 `bytecoind`（RPC 在 `127.0.0.1:8081`）以及用于矿池钱包、启用 RPC 认证的 `walletd`：

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

然后：

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` 列出各项设置：端口、难度、确认数、PPLNS 窗口、最低支付额。

矿池钱包持有花费密钥，因此 walletd 只能监听 localhost，钱包文件必须加密，RPC 密码只能由 root 读取。请保持较小的余额：超出矿工余额的部分可以转入冷钱包。

## 许可证

LGPLv3，见 `LICENSE`。
