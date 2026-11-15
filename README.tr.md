# bcn-pool

[English](README.md) · [Українська](README.uk.md) · [Español](README.es.md) · [Português](README.pt.md) · **Türkçe** · [Bahasa Indonesia](README.id.md) · [Tiếng Việt](README.vi.md) · [中文](README.zh.md)

**%0 ücretli** ve **PPLNS** ödemeli açık bir Bytecoin (BCN) madencilik havuzu. <https://pool.bytecoin.community> adresinde çalışır (stratum `pool.bytecoin.community:3333`).

Bu, topluluğun bağımsız bir projesidir; Bytecoin kurucuları ve bcndev ile bağlantısı yoktur.

## Nasıl çalışır

- **Kullanıcı adı:** BCN adresiniz, isteğe bağlı olarak `adres.worker`. Parola sabit bir share zorluğu için `d=NNNN` olabilir. Algoritma `cn/0` (CryptoNight v0): XMRig, BCN Miner ve CryptoNight ASIC'leri çalışır.
- **Her share yeniden hesaplanır**, bytecoin'in kendi CryptoNight'ıyla. Madencinin bildirdiği hash'e asla güvenilmez. Çöp share gönderen IP 10 dakika engellenir.
- **Vardiff:** her bağlantı, yaklaşık 15 saniyede bir share gelecek şekilde bir share zorluğu alır.
- **PPLNS:** bir bloğun ödülü, ondan önceki 2 × ağ zorluğu kadar en yeni share işine bölünür. Blok 20 onaya ulaşınca hesaplara yazılır; ana zincirden çıkan blok hiçbir şey kazandırmaz.
- **Ödemeler:** her saat, en az 0,1 BCN olan bakiyeler için, herkese tek bir işlemle. Havuz hiçbir şey almaz: bu işlemin ağ ücreti ödemelerden orantılı olarak düşülür. walletd'nin ödeme yapamadığı bir adres atlanır ve işaretlenir, diğerleri yine ödemesini alır.
- **Bölünme koruması:** bloklar yalnızca dış bir düğüm (varsayılan olarak node01/node02.bytecoin.org) tepemizin iki altındaki bloğumuza sahipken gönderilir; böylece ağdan kopmuş bir havuz özel bir zincir kuramaz. Aynı koruma [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) içinde de var.

## Dosyalar

| Dosya | Ne işe yarar |
| --- | --- |
| `pool.py` | Havuzun kendisi: stratum sunucusu, share kontrolü, vardiff, blok gönderme, olgunlaşma, PPLNS, ödemeler, JSON istatistikleri |
| `bcnaddr.py` | Düğümsüz adres kontrolü: base58, önek (`2…` legacy, `bcnZ…` Amethyst) ve Keccak sağlama toplamı |
| `bcnlib.py` | `libbcnhelper.so` için ctypes sarmalayıcı (blok şablonları, CryptoNight), bcn-stratum ile ortak |
| `test_pool.py` | Düğümsüz testler: PPLNS, ücret paylaşımı, vardiff, share kontrolü, giriş |
| `bcn-pool.service` | systemd birimi |
| `web/` | Havuz sayfası; `api/stats.json` ve `api/miners/<adres>.json` dosyalarını okur |
| `deploy/nginx-pool.conf` | Sayfa ve JSON için nginx sitesi |

`libbcnhelper.so`, [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) içindeki bytecoin kaynaklarından (`src/`) derlenir; onu `pool.py`'nin yanına koyun.

## Çalıştırma

Eşitlenmiş bir `bytecoind` (RPC `127.0.0.1:8081` üzerinde) ve RPC yetkilendirmeli bir havuz cüzdanı `walletd`'si gerekir:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Sonra:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` ayarları listeler: portlar, zorluk, onay sayısı, PPLNS penceresi, en düşük ödeme.

Havuz cüzdanı harcama anahtarını tutar; bu yüzden walletd yalnızca localhost'u dinlemeli, cüzdan dosyası şifreli olmalı ve RPC parolasını yalnızca root okuyabilmelidir. Bakiyeyi küçük tutun: madencilerin bakiyelerini aşan her şey soğuk bir cüzdana aktarılabilir.

## Lisans

LGPLv3, bkz. `LICENSE`.
