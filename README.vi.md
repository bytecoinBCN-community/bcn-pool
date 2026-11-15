# bcn-pool

[English](README.md) · [Українська](README.uk.md) · [Español](README.es.md) · [Português](README.pt.md) · [Türkçe](README.tr.md) · [Bahasa Indonesia](README.id.md) · **Tiếng Việt** · [中文](README.zh.md)

Pool đào Bytecoin (BCN) mở với **phí 0%** và trả thưởng **PPLNS**. Đang chạy tại <https://pool.bytecoin.community> (stratum `pool.bytecoin.community:3333`).

Đây là dự án độc lập của cộng đồng, không liên quan đến những người sáng lập Bytecoin hay bcndev.

## Cách hoạt động

- **Đăng nhập:** địa chỉ BCN của bạn, có thể dạng `địa_chỉ.worker`. Mật khẩu có thể là `d=NNNN` để đặt độ khó share cố định. Thuật toán `cn/0` (CryptoNight v0): XMRig, BCN Miner và ASIC CryptoNight đều dùng được.
- **Mọi share đều được tính lại** bằng CryptoNight từ chính mã nguồn bytecoin. Pool không bao giờ tin hash do thợ đào gửi lên. Gửi share rác sẽ bị chặn IP trong 10 phút.
- **Vardiff:** mỗi kết nối nhận một độ khó share sao cho khoảng 15 giây có một share.
- **PPLNS:** phần thưởng của một khối được chia theo khối lượng công việc mới nhất bằng 2 × độ khó mạng trước khối đó. Phần thưởng được ghi có khi khối đã sâu 20 khối; khối rời khỏi chuỗi chính không được trả gì.
- **Trả thưởng:** mỗi giờ cho số dư từ 0,1 BCN trở lên, bằng một giao dịch cho tất cả. Pool không giữ lại gì: phí mạng của giao dịch đó được trừ vào các khoản trả theo tỷ lệ. Địa chỉ mà walletd không thể trả được sẽ bị bỏ qua và đánh dấu, những người khác vẫn được trả.
- **Bảo vệ chống phân tách:** khối chỉ được gửi khi một nút bên ngoài (mặc định node01/node02.bytecoin.org) có khối của chúng tôi ở hai độ cao dưới đỉnh, nên pool bị cô lập không thể dựng chuỗi riêng. Cơ chế bảo vệ tương tự có trong [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum). Việc đào cũng tạm dừng khi một nút bên ngoài trên chuỗi của chúng tôi đi trước nút của chúng tôi từ hai khối trở lên, để pool không đào trên đỉnh cũ.

## Tệp

| Tệp | Nội dung |
| --- | --- |
| `pool.py` | Pool: máy chủ stratum, kiểm tra share, vardiff, gửi khối, chờ khối chín, PPLNS, trả thưởng, thống kê JSON |
| `bcnaddr.py` | Kiểm tra địa chỉ không cần nút: base58, tiền tố (`2…` legacy, `bcnZ…` Amethyst) và tổng kiểm tra Keccak |
| `bcnlib.py` | Lớp bọc ctypes cho `libbcnhelper.so` (mẫu khối, CryptoNight), dùng chung với bcn-stratum |
| `test_pool.py` | Kiểm thử không cần nút: PPLNS, chia phí, vardiff, kiểm tra share, đăng nhập |
| `bcn-pool.service` | Unit systemd |
| `web/` | Trang của pool; đọc `api/stats.json` và `api/miners/<địa_chỉ>.json` |
| `deploy/nginx-pool.conf` | Trang nginx cho trang web và JSON |

`libbcnhelper.so` được biên dịch từ mã nguồn bytecoin trong [bcn-stratum](https://github.com/bytecoinBCN-community/bcn-stratum) (`src/`); hãy đặt nó cạnh `pool.py`.

## Chạy

Cần một `bytecoind` đã đồng bộ (RPC ở `127.0.0.1:8081`) và một `walletd` cho ví của pool có xác thực RPC:

```
walletd --wallet-file=pool.wallet --bytecoind-remote-address=127.0.0.1:8081 --walletd-bind-address=127.0.0.1:18071
```

Sau đó:

```
WALLETD_AUTH=user:password python3 -I pool.py --walletd http://127.0.0.1:18071/json_rpc
python3 test_pool.py
```

`python3 pool.py --help` liệt kê các thiết lập: cổng, độ khó, số xác nhận, cửa sổ PPLNS, mức trả tối thiểu.

Ví của pool giữ khóa chi tiêu, vì vậy hãy để walletd chỉ lắng nghe trên localhost, tệp ví được mã hóa và mật khẩu RPC chỉ root đọc được. Giữ số dư nhỏ: mọi khoản vượt quá số dư của thợ đào có thể chuyển sang ví lạnh.

## Giấy phép

LGPLv3, xem `LICENSE`.
