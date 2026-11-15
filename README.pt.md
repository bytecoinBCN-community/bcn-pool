# bcn-pool

[English](README.md) · [Українська](README.uk.md) · [Español](README.es.md) · **Português** · [Türkçe](README.tr.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md)

Um pool de mineração aberto de Bytecoin (BCN) com **0% de taxa** e pagamentos **PPLNS**. Roda em <https://pool.bytecoin.community> (stratum `pool.bytecoin.community:3333`).

É um projeto independente da comunidade, sem ligação com os fundadores do Bytecoin nem com a bcndev.

## Como funciona

- **Login:** o seu endereço BCN, opcionalmente `endereço.worker`. A senha pode ser `d=NNNN` para uma dificuldade de share fixa. Algoritmo `cn/0` (CryptoNight v0): funcionam XMRig, BCN Miner e ASICs CryptoNight.
- **Cada share é recalculado** com o CryptoNight do próprio bytecoin. O pool nunca confia no hash que o minerador informa. Shares lixo bloqueiam o IP por 10 minutos.
- **Vardiff:** cada conexão recebe uma dificuldade de share pensada para um share a cada 15 segundos, mais ou menos.
- **PPLNS:** a recompensa de um bloco é dividida pelo trabalho mais recente equivalente a 2 × a dificuldade da rede antes dele. É creditada quando o bloco tem 20 confirmações; um bloco que sai da cadeia principal não rende nada.
- **Pagamentos:** de hora em hora, para saldos a partir de 0,1 BCN, numa única transação para todos. O pool não fica com nada: a taxa de rede dessa transação é descontada dos pagamentos em proporção. Um endereço para o qual o walletd não consegue pagar é pulado e marcado; os demais recebem normalmente.
- **Proteção contra partição:** os blocos só são enviados enquanto um nó externo (por padrão node01/node02.bytecoin.org) tem o nosso bloco duas alturas abaixo do nosso topo, então um pool isolado não consegue construir uma cadeia privada. A mesma proteção está no [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum).

## Arquivos

| Arquivo | O que é |
| --- | --- |
| `pool.py` | O pool: servidor stratum, verificação de shares, vardiff, envio de blocos, maturação, PPLNS, pagamentos, estatísticas JSON |
| `bcnaddr.py` | Verificação de endereço sem nó: base58, prefixo (`2…` legacy, `bcnZ…` Amethyst) e soma Keccak |
| `bcnlib.py` | Wrapper ctypes de `libbcnhelper.so` (modelos de bloco, CryptoNight), compartilhado com o bcn-stratum |
| `test_pool.py` | Testes sem nó: PPLNS, divisão da taxa, vardiff, verificação de shares, login |
| `bcn-pool.service` | Unidade do systemd |
| `web/` | A página do pool; lê `api/stats.json` e `api/miners/<endereço>.json` |
| `deploy/nginx-pool.conf` | Site do nginx para a página e o JSON |

`libbcnhelper.so` é compilada a partir do código do bytecoin no [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) (`src/`); coloque-a ao lado do `pool.py`.

## Como rodar

É preciso um `bytecoind` sincronizado (RPC em `127.0.0.1:8081`) e um `walletd` para a carteira do pool com autorização RPC:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Depois:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` lista as configurações: portas, dificuldade, confirmações, janela PPLNS e pagamento mínimo.

A carteira do pool guarda a chave de gasto, então mantenha o walletd escutando só em localhost, o arquivo da carteira criptografado e a senha RPC legível apenas pelo root. Mantenha o saldo baixo: tudo acima dos saldos dos mineradores pode ir para uma carteira fria.

## Licença

LGPLv3, veja `LICENSE`.
