# bcn-pool

[English](README.md) · [Українська](README.uk.md) · **Español** · [Português](README.pt.md) · [Türkçe](README.tr.md) · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md)

Un pool de minería abierto de Bytecoin (BCN) con **0% de comisión** y pagos **PPLNS**. Funciona en <https://pool.bytecoin.community> (stratum `pool.bytecoin.community:3333`).

Es un proyecto independiente de la comunidad, sin relación con los fundadores de Bytecoin ni con bcndev.

## Cómo funciona

- **Usuario:** su dirección BCN, opcionalmente `dirección.worker`. La contraseña puede ser `d=NNNN` para una dificultad de share fija. Algoritmo `cn/0` (CryptoNight v0): funcionan XMRig, BCN Miner y los ASIC de CryptoNight.
- **Cada share se vuelve a calcular** con el CryptoNight del propio bytecoin. El pool nunca se fía del hash que declara el minero. Los shares basura bloquean la IP durante 10 minutos.
- **Vardiff:** cada conexión recibe una dificultad de share pensada para un share cada 15 segundos aproximadamente.
- **PPLNS:** la recompensa de un bloque se reparte entre el trabajo más reciente equivalente a 2 × la dificultad de la red antes del bloque. Se acredita cuando el bloque tiene 20 confirmaciones; un bloque que sale de la cadena principal no gana nada.
- **Pagos:** cada hora, para saldos de al menos 0,1 BCN, en una sola transacción para todos. El pool no se queda nada: la comisión de red de esa transacción se descuenta de los pagos de forma proporcional. Una dirección a la que walletd no puede pagar se omite y se marca; los demás cobran igual.
- **Protección contra particiones:** los bloques se envían solo mientras un nodo externo (por defecto node01/node02.bytecoin.org) tiene nuestro bloque dos alturas por debajo de nuestra cima, así que un pool aislado no puede construir una cadena privada. La misma protección está en [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum).

## Archivos

| Archivo | Qué es |
| --- | --- |
| `pool.py` | El pool: servidor stratum, comprobación de shares, vardiff, envío de bloques, maduración, PPLNS, pagos, estadísticas JSON |
| `bcnaddr.py` | Comprobación de direcciones sin nodo: base58, prefijo (`2…` legacy, `bcnZ…` Amethyst) y suma Keccak |
| `bcnlib.py` | Envoltorio ctypes de `libbcnhelper.so` (plantillas de bloque, CryptoNight), compartido con bcn-stratum |
| `test_pool.py` | Pruebas sin nodo: PPLNS, reparto de comisión, vardiff, comprobación de shares, inicio de sesión |
| `bcn-pool.service` | Unidad de systemd |
| `web/` | La página del pool; lee `api/stats.json` y `api/miners/<dirección>.json` |
| `deploy/nginx-pool.conf` | Sitio de nginx para la página y el JSON |

`libbcnhelper.so` se compila a partir del código de bytecoin en [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) (`src/`); póngala junto a `pool.py`.

## Ejecución

Necesita un `bytecoind` sincronizado (RPC en `127.0.0.1:8081`) y un `walletd` para el monedero del pool con autorización RPC:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Después:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` muestra los ajustes: puertos, dificultad, confirmaciones, ventana PPLNS y pago mínimo.

El monedero del pool guarda la clave de gasto, así que mantenga walletd escuchando solo en localhost, el archivo del monedero cifrado y la contraseña RPC legible solo por root. Mantenga el saldo bajo: todo lo que supere los saldos de los mineros puede pasarse a un monedero en frío.

## Licencia

LGPLv3, véase `LICENSE`.
