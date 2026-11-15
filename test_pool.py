#!/usr/bin/env python3
"""bcn-pool tests without a node: PPLNS, fee split, vardiff, share checks and the block gate."""
import asyncio
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.modules.setdefault("bcnlib", types.ModuleType("bcnlib"))
import pool as P  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print("%-62s %s" % (name, "ok" if cond else "FAIL"))


A, B, C = "addrA", "addrB", "addrC"
db = tempfile.mktemp(suffix=".db")
st = P.Store(db)

# ---- PPLNS
st.add_shares([(1, A, "w", 100), (2, B, "w", 300)])
last = st.add_shares([(3, A, "w", 100), (4, C, "w", 500)])
check("window covers the newest work only", st.pplns(last, 600) == {C: 500, A: 100})
check("a share at the window edge counts in part", st.pplns(last, 800) == {C: 500, A: 100, B: 200})
check("small history: all of it", st.pplns(last, 10 ** 9) == {C: 500, A: 200, B: 300})
st.db.execute("INSERT INTO blocks (height, hash, reward, ts, share_id, net_diff, finder) VALUES (10,'h',1001,0,?,0,?)",
              (last, C))
amounts = st.credit_block(10, 1001, {A: 200, B: 300, C: 500})
check("reward split by work, remainder to the largest", amounts == {A: 200, B: 300, C: 501})
check("credit is idempotent", st.credit_block(10, 1001, {A: 200, B: 300, C: 500}) and
      dict(st.db.execute("SELECT address, pending FROM balances")) == {A: 200, B: 300, C: 501})
check("block marked confirmed", st.db.execute("SELECT status FROM blocks WHERE height=10").fetchone()[0] == "confirmed")
st.trim_shares(600)
check("old shares trimmed, newest kept", [r[0] for r in st.db.execute("SELECT diff FROM shares ORDER BY id")]
      == [100, 500])
os.unlink(db)

# ---- fee split
net = P.split_fee({A: 1000, B: 3000}, 101)
check("fee taken in proportion and exactly", sum(net.values()) == 4000 - 101 and net[A] < 1000 and net[B] < 3000)
check("fee split rounding never pays more than due", all(net[k] <= v for k, v in {A: 1000, B: 3000}.items()))


# ---- fakes for sessions
class Helper:
    def __init__(self):
        self.hash = bytes(32)

    def cn_slow_hash(self, blob):
        return self.hash

    def check_hash(self, h, diff):
        return diff <= self.max_diff

    max_diff = 10 ** 6


class FakePool:
    def __init__(self):
        self.args = types.SimpleNamespace(start_diff=5000, min_diff=1000, max_diff=10 ** 7, share_time=15,
                                          max_per_ip=4, idle_timeout=5)
        self.helper, self.height, self.can_mine = Helper(), 0, True
        self.loop = asyncio.new_event_loop()
        self.hash_pool = None
        self.shares, self.blocks = [], []

    def record_share(self, a, w, d):
        self.shares.append((a, w, d))

    async def found_block(self, job, nonce, s):
        self.blocks.append(job.height)

    async def new_job(self, diff):
        return P.Job("j", 5, 10 ** 9, b"t" * 80, b"h" * 80, 39, 39, diff)


fp = FakePool()


async def run_in(_pool, fn, *args):
    return fn(*args)
fp.loop.run_in_executor = run_in


def session():
    s = P.Session.__new__(P.Session)
    s.p, s.ip, s.address, s.worker = fp, "1.2.3.4", A, "w"
    s.diff, s.jobs, s.share_times = 5000, [P.Job("j", 5, 10 ** 9, b"t" * 80, b"h" * 80, 39, 39, 5000)], P.deque(maxlen=30)
    s.last_retarget, s.good, s.bad, s.sent = 0, 0, 0, []
    s.send = s.sent.append
    return s


s = session()
fp.loop.run_until_complete(s.on_submit(1, {"job_id": "j", "nonce": "01020304", "result": "00" * 32}))
check("valid share accepted and recorded", s.good == 1 and fp.shares == [(A, "w", 5000)])
fp.loop.run_until_complete(s.on_submit(2, {"job_id": "j", "nonce": "01020304", "result": "00" * 32}))
check("duplicate nonce rejected", s.bad == 1 and "duplicate" in s.sent[-1]["error"]["message"])
fp.loop.run_until_complete(s.on_submit(3, {"job_id": "j", "nonce": "05060708", "result": "11" * 32}))
check("claimed hash that does not match is rejected", s.bad == 2 and "wrong hash" in s.sent[-1]["error"]["message"])
fp.helper.max_diff = 100
fp.loop.run_until_complete(s.on_submit(4, {"job_id": "j", "nonce": "090a0b0c", "result": "00" * 32}))
check("share below the job difficulty is rejected", s.bad == 3 and "low difficulty" in s.sent[-1]["error"]["message"])
fp.loop.run_until_complete(s.on_submit(5, {"job_id": "x", "nonce": "0d0e0f10"}))
check("unknown job rejected", "unknown job" in s.sent[-1]["error"]["message"])
fp.height = 5
fp.helper.max_diff = 10 ** 6
fp.loop.run_until_complete(s.on_submit(6, {"job_id": "j", "nonce": "11121314"}))
check("stale job rejected", "stale" in s.sent[-1]["error"]["message"])
fp.height = 0
fp.helper.max_diff = 10 ** 10
fp.loop.run_until_complete(s.on_submit(7, {"job_id": "j", "nonce": "15161718"}))
check("share meeting network difficulty becomes a block candidate", fp.blocks == [5])

# ---- vardiff
s = session()
s.share_times.extend([0, 3, 6, 9, 12])  # one share every 3 s, aim is 15 s
check("fast miner: difficulty up, at most x2", s.retarget() and s.diff == 10000)
s = session()
s.share_times.extend([0, 60, 120, 180])  # one share a minute
check("slow miner: difficulty down, at most /2", s.retarget() and s.diff == 2500)
s = session()
s.share_times.extend([0, 15, 30, 45])
check("on target: unchanged", not s.retarget() and s.diff == 5000)

# ---- login
s = session()
s.address = None
fp.loop.run_until_complete(s.on_login(1, {"login": "not-an-address"}))
check("login with a junk address refused", s.address is None and "BCN address" in s.sent[-1]["error"]["message"])
P.bcnaddr.check = lambda a: "legacy" if a.startswith("2") else None
fp.can_mine = False
fp.loop.run_until_complete(s.on_login(2, {"login": "2good.rig1"}))
check("login refused while the pool node is not ready", s.address is None)
fp.can_mine = True
fp.loop.run_until_complete(s.on_login(3, {"login": "2good.rig1", "pass": "d=20000"}))
check("login with address.worker and d= accepted", s.address == "2good" and s.worker == "rig1" and s.diff == 20000)

print("POOL TEST", "PASSED" if ok else "FAILED")
raise SystemExit(0 if ok else 1)
