# bcn-pool

[English](README.md) · [Українська](README.uk.md) · [Español](README.es.md) · [Português](README.pt.md) · [Türkçe](README.tr.md) · **Bahasa Indonesia** · [Tiếng Việt](README.vi.md) · [中文](README.zh.md)

Pool penambangan Bytecoin (BCN) terbuka dengan **biaya 0%** dan pembayaran **PPLNS**. Berjalan di <https://pool.bytecoin.community> (stratum `pool.bytecoin.community:3333`).

Ini adalah proyek independen komunitas, tidak berafiliasi dengan para pendiri Bytecoin maupun bcndev.

## Cara kerja

- **Login:** alamat BCN Anda, opsional `alamat.worker`. Kata sandi bisa `d=NNNN` untuk tingkat kesulitan share yang tetap. Algoritma `cn/0` (CryptoNight v0): XMRig, BCN Miner, dan ASIC CryptoNight semuanya bisa dipakai.
- **Setiap share dihitung ulang** dengan CryptoNight dari kode bytecoin sendiri. Hash yang diklaim penambang tidak pernah dipercaya. Share sampah membuat IP diblokir selama 10 menit.
- **Vardiff:** setiap koneksi mendapat tingkat kesulitan share yang menargetkan sekitar satu share tiap 15 detik.
- **PPLNS:** hadiah sebuah blok dibagi atas pekerjaan terbaru sebesar 2 × kesulitan jaringan sebelum blok itu. Hadiah dikreditkan saat blok sudah sedalam 20 blok; blok yang keluar dari rantai utama tidak menghasilkan apa-apa.
- **Pembayaran:** tiap jam untuk saldo minimal 0,1 BCN, dalam satu transaksi untuk semuanya. Pool tidak mengambil apa pun: biaya jaringan transaksi itu diambil dari pembayaran secara proporsional. Alamat yang tidak bisa dibayar oleh walletd dilewati dan ditandai, yang lain tetap dibayar.
- **Pelindung partisi:** blok hanya dikirim selama node luar (bawaan node01/node02.bytecoin.org) memiliki blok kami dua ketinggian di bawah puncak kami, sehingga pool yang terputus tidak bisa membangun rantai pribadi. Pelindung yang sama ada di [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum).

## File

| File | Isinya |
| --- | --- |
| `pool.py` | Pool-nya: server stratum, pemeriksaan share, vardiff, pengiriman blok, pematangan, PPLNS, pembayaran, statistik JSON |
| `bcnaddr.py` | Pemeriksaan alamat tanpa node: base58, prefiks (`2…` legacy, `bcnZ…` Amethyst), dan checksum Keccak |
| `bcnlib.py` | Pembungkus ctypes untuk `libbcnhelper.so` (templat blok, CryptoNight), dipakai bersama bcn-stratum |
| `test_pool.py` | Tes tanpa node: PPLNS, pembagian biaya, vardiff, pemeriksaan share, login |
| `bcn-pool.service` | Unit systemd |
| `web/` | Halaman pool; membaca `api/stats.json` dan `api/miners/<alamat>.json` |
| `deploy/nginx-pool.conf` | Situs nginx untuk halaman dan JSON |

`libbcnhelper.so` dibangun dari kode sumber bytecoin di [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) (`src/`); taruh di samping `pool.py`.

## Menjalankan

Anda perlu `bytecoind` yang sudah sinkron (RPC di `127.0.0.1:8081`) dan `walletd` untuk dompet pool dengan otorisasi RPC:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Lalu:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` menampilkan pengaturan: port, kesulitan, jumlah konfirmasi, jendela PPLNS, pembayaran minimum.

Dompet pool menyimpan kunci pengeluaran, jadi biarkan walletd hanya mendengarkan di localhost, file dompet terenkripsi, dan kata sandi RPC hanya bisa dibaca root. Jaga saldonya tetap kecil: semua yang melebihi saldo para penambang bisa dipindahkan ke dompet dingin.

## Lisensi

LGPLv3, lihat `LICENSE`.
