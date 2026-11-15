#!/usr/bin/env python3
"""bcn-pool: open Bytecoin (BCN) mining pool with a 0% fee and PPLNS payouts.

Miners log in with their BCN address (optionally "address.worker"). Every share is recomputed with
CryptoNight here: nothing a miner claims is trusted. Share difficulty follows each miner (vardiff).
Found blocks pay the pool wallet; once a block is buried CONFIRMATIONS deep, its reward is split over
the last PPLNS_FACTOR x network-difficulty of share work, and walletd sends out balances above the
minimum payout. The pool keeps nothing: transaction fees are taken from the payouts in proportion.

Partition guard as in bcn-stratum: blocks are submitted only while an outside node has our chain.
"""
import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # run with python3 -I, which drops the script dir
import bcnaddr  # noqa: E402
import bcnlib  # noqa: E402

log = logging.getLogger("bcn-pool")
ATOMIC = 10 ** 8
JOBS_KEPT = 4
EXTERNAL_NODES = "https://node01.bytecoin.org:8091/json_rpc,https://node02.bytecoin.org:8091/json_rpc"
CONFIRM_DEPTH = 2


# ---------------------------------------------------------------- node / wallet RPC
class Rpc:
    def __init__(self, url, timeout=30, auth=None):
        self.url, self.timeout, self.auth = url, timeout, auth

    def call(self, method, params=None):
        body = json.dumps({"jsonrpc": "2.0", "id": "0", "method": method, "params": params or {}}).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "bcn-pool"}
        if self.auth:
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(self.auth.encode()).decode()
        with urllib.request.urlopen(urllib.request.Request(self.url, body, headers), timeout=self.timeout) as r:
            resp = json.loads(r.read().decode())
        if resp.get("error"):
            e = resp["error"]
            raise RpcError(e.get("code"), e.get("message", str(e)))
        return resp["result"]


class RpcError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s (%s)" % (message, code))
        self.code = code


def block_hash_at(node, height):
    h = node.call("getblockheaderbyheight", {"height": height + 1})["block_header"]  # legacy call counts from 1
    if h["height"] != height:
        raise RuntimeError("asked for block %d, got %d" % (height, h["height"]))
    return h["hash"]


def network_agrees(local, externals):
    """-> (True if an outside node has our block CONFIRM_DEPTH below our top, note)."""
    ref = local.call("get_status")["top_block_height"] - CONFIRM_DEPTH
    ours = block_hash_at(local, ref)
    notes = []
    for ext in externals:
        try:
            top = ext.call("get_status")["top_block_height"]
            if top < ref:
                same = block_hash_at(ext, top) == block_hash_at(local, top)
                notes.append("%s %s at %d" % (ext.url, "behind" if same else "ON ANOTHER CHAIN", top))
                continue
            if block_hash_at(ext, ref) == ours:
                return True, "%s has our block %d" % (ext.url, ref)
            notes.append("%s ON ANOTHER CHAIN at %d" % (ext.url, ref))
        except Exception as ex:
            notes.append("%s: %s" % (ext.url, type(ex).__name__))
    return False, "; ".join(notes) or "no outside nodes"


def target_hex(difficulty):
    return ((2 ** 32 - 1) // difficulty).to_bytes(4, "little").hex()


# ---------------------------------------------------------------- storage and payout maths
SCHEMA = """
CREATE TABLE IF NOT EXISTS shares (id INTEGER PRIMARY KEY, ts REAL, address TEXT, worker TEXT, diff INTEGER);
CREATE TABLE IF NOT EXISTS blocks (height INTEGER PRIMARY KEY, hash TEXT, reward INTEGER, ts REAL, share_id INTEGER,
    net_diff INTEGER, finder TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS credits (height INTEGER, address TEXT, amount INTEGER, PRIMARY KEY (height, address));
CREATE TABLE IF NOT EXISTS balances (address TEXT PRIMARY KEY, pending INTEGER DEFAULT 0, paid INTEGER DEFAULT 0,
    bad INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, ts REAL, tx TEXT, address TEXT, gross INTEGER,
    fee INTEGER);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def add_shares(self, rows):
        """rows: (ts, address, worker, diff). -> id of the last share."""
        with self.db:
            self.db.executemany("INSERT INTO shares (ts, address, worker, diff) VALUES (?,?,?,?)", rows)
        return self.db.execute("SELECT MAX(id) FROM shares").fetchone()[0] or 0

    def pplns(self, last_share_id, window):
        """-> {address: work} for the newest `window` of share work up to last_share_id."""
        work, total = defaultdict(int), 0
        for address, diff in self.db.execute(
                "SELECT address, diff FROM shares WHERE id <= ? ORDER BY id DESC", (last_share_id,)):
            take = min(diff, window - total)
            work[address] += take
            total += take
            if total >= window:
                break
        return dict(work)

    def credit_block(self, height, reward, work):
        """Splits `reward` by work; the rounding remainder goes to the largest contributor. Idempotent."""
        if not work:  # cannot happen (the finder sent a share), but never leave a block pending forever
            self.db.execute("UPDATE blocks SET status='confirmed' WHERE height=?", (height,))
            return {}
        total = sum(work.values())
        amounts = {a: reward * w // total for a, w in work.items()}
        top = max(work, key=work.get)
        amounts[top] += reward - sum(amounts.values())
        with self.db:
            for a, amt in amounts.items():
                if self.db.execute("INSERT OR IGNORE INTO credits VALUES (?,?,?)", (height, a, amt)).rowcount:
                    self.db.execute("INSERT INTO balances (address, pending) VALUES (?,?) ON CONFLICT(address) "
                                    "DO UPDATE SET pending = pending + excluded.pending", (a, amt))
            self.db.execute("UPDATE blocks SET status='confirmed' WHERE height=?", (height,))
        return amounts

    def trim_shares(self, keep_work):
        """Drops shares older than the newest `keep_work` of work (several PPLNS windows)."""
        total = 0
        for sid, diff in self.db.execute("SELECT id, diff FROM shares ORDER BY id DESC"):
            total += diff
            if total >= keep_work:
                self.db.execute("DELETE FROM shares WHERE id < ?", (sid,))
                return


def split_fee(gross, fee):
    """Takes `fee` from payouts in proportion. gross: {address: amount} -> {address: net}."""
    total = sum(gross.values())
    net = {a: g - fee * g // total for a, g in gross.items()}
    short = fee - (total - sum(net.values()))  # rounding: the largest payout covers the rest
    if short:
        top = max(net, key=net.get)
        net[top] -= short
    return net


# ---------------------------------------------------------------- stratum
class Job:
    __slots__ = ("job_id", "height", "net_diff", "template", "hashing", "toff", "hoff", "diff", "seen")

    def __init__(self, job_id, height, net_diff, template, hashing, toff, hoff, diff):
        self.job_id, self.height, self.net_diff, self.diff = job_id, height, net_diff, diff
        self.template, self.hashing, self.toff, self.hoff = template, hashing, toff, hoff
        self.seen = set()


class Session:
    def __init__(self, pool, reader, writer):
        self.p, self.reader, self.writer = pool, reader, writer
        self.ip = writer.get_extra_info("peername")[0]
        self.address = self.worker = None
        self.diff = pool.args.start_diff
        self.jobs = []
        self.share_times = deque(maxlen=30)
        self.last_retarget = time.time()
        self.good = self.bad = 0

    def send(self, obj):
        self.writer.write((json.dumps(obj) + "\n").encode())

    def job_params(self, job):
        return {"blob": job.hashing.hex(), "job_id": job.job_id, "target": target_hex(job.diff),
                "height": job.height, "algo": "cn/0"}

    async def push_job(self, clean=False):
        job = await self.p.new_job(self.diff)
        if clean:
            self.jobs.clear()
        self.jobs = (self.jobs + [job])[-JOBS_KEPT:]
        self.send({"jsonrpc": "2.0", "method": "job", "params": self.job_params(job)})

    def retarget(self):
        """Vardiff: aim at args.share_time seconds between shares, at most x2 / x0.5 per step."""
        now = time.time()
        if len(self.share_times) < 4 and now - self.last_retarget < 120:
            return False
        a = self.p.args
        if len(self.share_times) >= 2:
            interval = (self.share_times[-1] - self.share_times[0]) / (len(self.share_times) - 1)
        else:  # too few shares in 2 minutes: halve
            interval = a.share_time * 4
        new = int(self.diff * a.share_time / max(interval, 0.1))
        new = max(a.min_diff, min(a.max_diff, max(self.diff // 2, min(self.diff * 2, new))))
        self.last_retarget, changed = now, abs(new - self.diff) * 5 > self.diff
        if changed:
            self.diff = new
            self.share_times.clear()
        return changed

    async def on_login(self, rid, params):
        login = str(params.get("login", "")).strip()
        address, _, worker = login.partition(".")
        if not bcnaddr.check(address):
            return self.send({"id": rid, "jsonrpc": "2.0",
                              "error": {"code": -1, "message": "login must be your BCN address (address.worker)"}})
        if not self.p.can_mine:
            return self.send({"id": rid, "jsonrpc": "2.0", "error": {"code": -1, "message": "pool node not ready"}})
        self.address, self.worker = address, (worker or "default")[:32]
        for part in str(params.get("pass", "")).split(","):
            if part.startswith("d=") and part[2:].isdigit():
                self.diff = max(self.p.args.min_diff, min(self.p.args.max_diff, int(part[2:])))
        job = await self.p.new_job(self.diff)
        self.jobs = [job]
        log.info("login %s %s.%s agent=%s", self.ip, address[:12], self.worker, str(params.get("agent", ""))[:40])
        self.send({"id": rid, "jsonrpc": "2.0", "error": None,
                   "result": {"id": "%x" % id(self), "job": self.job_params(job), "status": "OK", "extensions": []}})

    async def on_submit(self, rid, params):
        def reply(err=None):
            if err:
                self.bad += 1
                self.send({"id": rid, "jsonrpc": "2.0", "error": {"code": -1, "message": err}})
            else:
                self.good += 1
                self.send({"id": rid, "jsonrpc": "2.0", "error": None, "result": {"status": "OK"}})

        job = next((j for j in self.jobs if j.job_id == params.get("job_id")), None)
        if job is None:
            return reply("unknown job")
        if job.height <= self.p.height:
            return reply("stale job")
        try:
            nonce = bytes.fromhex(params.get("nonce", ""))
        except ValueError:
            nonce = b""
        if len(nonce) != 4:
            return reply("bad nonce")
        if nonce in job.seen:
            return reply("duplicate share")
        job.seen.add(nonce)
        blob = job.hashing[:job.hoff] + nonce + job.hashing[job.hoff + 4:]
        h = await self.p.loop.run_in_executor(self.p.hash_pool, self.p.helper.cn_slow_hash, blob)
        claimed = str(params.get("result") or "")
        if claimed and claimed.lower() != h.hex():
            return reply("wrong hash")
        if not self.p.helper.check_hash(h, job.diff):
            return reply("low difficulty share")
        reply()
        self.share_times.append(time.time())
        self.p.record_share(self.address, self.worker, job.diff)
        if self.p.helper.check_hash(h, job.net_diff):
            await self.p.found_block(job, nonce, self)
        if self.retarget():
            await self.push_job(clean=False)

    async def run(self):
        p = self.p
        if p.per_ip[self.ip] >= p.args.max_per_ip or self.ip in p.banned and p.banned[self.ip] > time.time():
            self.writer.close()
            return
        p.per_ip[self.ip] += 1
        p.sessions.add(self)
        try:
            while True:
                line = await asyncio.wait_for(self.reader.readline(), timeout=p.args.idle_timeout)
                if not line:
                    break
                try:
                    msg = json.loads(line.decode())
                    rid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
                except (ValueError, AttributeError, UnicodeDecodeError):
                    break
                if method == "login" and self.address is None:
                    await self.on_login(rid, params)
                elif method == "submit" and self.address:
                    await self.on_submit(rid, params)
                elif method == "getjob" and self.address:
                    self.send({"id": rid, "jsonrpc": "2.0", "error": None, "result": self.job_params(self.jobs[-1])})
                elif method == "keepalived":
                    self.send({"id": rid, "jsonrpc": "2.0", "error": None, "result": {"status": "KEEPALIVED"}})
                else:
                    self.send({"id": rid, "jsonrpc": "2.0", "error": {"code": -1, "message": "unsupported"}})
                await self.writer.drain()
                if self.bad > 20 and self.bad > self.good:  # junk or a broken miner
                    p.banned[self.ip] = time.time() + 600
                    log.warning("banned %s for 10 min: %d bad, %d good shares", self.ip, self.bad, self.good)
                    break
        except (asyncio.TimeoutError, ConnectionError, asyncio.LimitOverrunError, ValueError):
            pass
        except Exception:
            log.exception("session %s crashed", self.ip)
        finally:
            p.sessions.discard(self)
            p.per_ip[self.ip] -= 1
            self.writer.close()


# ---------------------------------------------------------------- the pool
class Pool:
    def __init__(self, args):
        self.args = args
        self.node = Rpc(args.bytecoind)
        self.wallet = Rpc(args.walletd, timeout=120, auth=os.environ.get("WALLETD_AUTH"))
        self.externals = [Rpc(u, timeout=10) for u in filter(None, args.external_nodes.split(","))]
        self.helper = bcnlib.Helper(args.helper)
        self.store = Store(args.db)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.rpc_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.hash_pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.hash_threads)
        self.sessions, self.per_ip, self.banned = set(), defaultdict(int), {}
        self.currency_id = self.top_hash = None
        self.height = self.net_diff = 0
        self.synced, self.network_ok = False, not self.externals
        self.pending_shares, self.last_share_id = [], 0
        self.recent = deque()  # (ts, address, worker, diff) for hashrate, last hour
        self.job_seq = 0
        self.address = args.pool_address

    @property
    def can_mine(self):
        return self.synced and self.network_ok and self.currency_id is not None

    async def call(self, rpc, method, params=None):
        return await self.loop.run_in_executor(self.rpc_pool, rpc.call, method, params)

    async def new_job(self, diff):
        r = await self.call(self.node, "get_block_template", {"wallet_address": self.address, "reserve_size": 0})
        tmpl, hashing, toff, hoff = self.helper.prepare_template(bytes.fromhex(r["blocktemplate_blob"]),
                                                                 self.currency_id)
        self.job_seq += 1
        self.net_diff = r["difficulty"]
        return Job("%x" % self.job_seq, r["height"], r["difficulty"], tmpl, hashing, toff, hoff, diff)

    def record_share(self, address, worker, diff):
        row = (time.time(), address, worker, diff)
        self.pending_shares.append(row)
        self.recent.append(row)

    def flush_shares(self):
        if self.pending_shares:
            rows, self.pending_shares = self.pending_shares, []
            self.last_share_id = self.store.add_shares(rows)
        return self.last_share_id

    async def found_block(self, job, nonce, session):
        if not self.can_mine:
            log.warning("block candidate at height %d NOT submitted: node not synced or network does not "
                        "confirm our chain", job.height)
            return
        share_id = self.flush_shares()
        tmpl = job.template[:job.toff] + nonce + job.template[job.toff + 4:]
        try:
            r = await self.call(self.node, "submit_block", {"blocktemplate_blob": tmpl.hex()})
        except Exception as ex:
            log.error("block REJECTED at height %d: %s", job.height, ex)
            return
        hdr = r.get("block_header", {})
        self.store.db.execute("INSERT OR REPLACE INTO blocks (height, hash, reward, ts, share_id, net_diff, finder) "
                              "VALUES (?,?,?,?,?,?,?)", (hdr.get("height", job.height), hdr.get("hash"),
                                                         hdr.get("reward", 0), time.time(), share_id, job.net_diff,
                                                         session.address))
        log.info("BLOCK FOUND height=%s hash=%s reward=%s by %s.%s", hdr.get("height"), hdr.get("hash"),
                 hdr.get("reward"), session.address[:12], session.worker)
        self.top_hash = None

    # ---- background tasks
    async def watch_node(self):
        last_refresh = 0.0
        while True:
            try:
                if self.currency_id is None:
                    self.currency_id = bytes.fromhex((await self.call(self.node, "get_currency_id"))["currency_id_blob"])
                if not self.address:
                    self.address = (await self.call(self.wallet, "get_addresses"))["addresses"][0]
                    log.info("pool wallet address %s", self.address)
                st = await self.call(self.node, "get_status")
                synced = st["top_block_height"] + 1 >= st["top_known_block_height"] and st["outgoing_peer_count"] > 0
                if synced != self.synced:
                    log.info("node %s (height %d / %d)", "synced" if synced else "NOT synced",
                             st["top_block_height"], st["top_known_block_height"])
                    self.synced = synced
                changed = st["top_block_hash"] != self.top_hash
                if changed:
                    self.top_hash, self.height = st["top_block_hash"], st["top_block_height"]
                if self.can_mine and (changed or time.time() - last_refresh >= self.args.refresh):
                    last_refresh = time.time()
                    for s in list(self.sessions):
                        if s.address:
                            await s.push_job(clean=changed)
            except Exception as ex:
                log.error("node poll failed: %s", ex)
                await asyncio.sleep(5)
            await asyncio.sleep(self.args.poll)

    async def watch_network(self):
        first = True
        while self.externals:
            try:
                ok, note = await self.loop.run_in_executor(self.rpc_pool, network_agrees, self.node, self.externals)
            except Exception as ex:
                ok, note = False, "local node: %s" % type(ex).__name__
            if ok != self.network_ok or first:
                log.log(logging.INFO if ok else logging.WARNING, "network %s (%s)",
                        "confirms our chain" if ok else "DOES NOT CONFIRM OUR CHAIN, blocks not submitted", note)
                self.network_ok, first = ok, False
            await asyncio.sleep(self.args.network_check)

    async def mature_blocks(self):
        """Credits blocks once they are CONFIRMATIONS deep, marks replaced ones orphaned."""
        while True:
            try:
                self.flush_shares()
                top = self.height
                rows = self.store.db.execute("SELECT height, hash, reward, share_id, net_diff FROM blocks "
                                             "WHERE status='pending' AND height <= ?",
                                             (top - self.args.confirmations,)).fetchall()
                for height, bhash, reward, share_id, net_diff in rows:
                    main = await self.loop.run_in_executor(self.rpc_pool, block_hash_at, self.node, height)
                    if main != bhash:
                        self.store.db.execute("UPDATE blocks SET status='orphaned' WHERE height=?", (height,))
                        log.warning("block %d orphaned", height)
                        continue
                    work = self.store.pplns(share_id, self.args.pplns_factor * net_diff)
                    amounts = self.store.credit_block(height, reward, work)
                    log.info("block %d confirmed: %.8f BCN to %d addresses", height, reward / ATOMIC, len(amounts))
                if self.net_diff:
                    self.store.trim_shares(5 * self.args.pplns_factor * self.net_diff)
            except Exception as ex:
                log.error("maturing failed: %s", ex)
            await asyncio.sleep(60)

    async def payouts(self):
        await asyncio.sleep(120)
        while True:
            try:
                await self.pay_once()
            except Exception as ex:
                log.error("payout failed: %s", ex)
            await asyncio.sleep(self.args.payout_interval)

    async def pay_once(self):
        a = self.args
        due = dict(self.store.db.execute("SELECT address, pending FROM balances WHERE pending >= ? AND bad = 0 "
                                         "ORDER BY pending DESC LIMIT ?", (a.min_payout, a.max_outputs)).fetchall())
        if not due:
            return
        bal = await self.call(self.wallet, "get_balance", {})
        spendable = int(bal["spendable"])
        while due and sum(due.values()) > spendable:  # never promise more than the wallet can spend now
            due.pop(min(due, key=due.get))
        if not due:
            log.info("payout waits: %.8f BCN spendable", spendable / ATOMIC)
            return

        def build(amounts):
            return self.wallet.call("create_transaction", {
                "transaction": {"anonymity": a.anonymity,
                                "transfers": [{"address": ad, "amount": am} for ad, am in amounts.items()]},
                "any_spend_address": True, "change_address": self.address})

        try:
            draft = await self.loop.run_in_executor(self.rpc_pool, build, due)
        except RpcError as ex:
            bad = await self.find_bad_address(build, due) if "address" in str(ex).lower() else None
            if bad:
                self.store.db.execute("UPDATE balances SET bad = 1 WHERE address = ?", (bad,))
                log.error("payout skips invalid address %s: %s", bad[:12], ex)
                return
            raise
        fee = int(draft["transaction"]["fee"])
        net = split_fee(due, fee)
        tx = await self.loop.run_in_executor(self.rpc_pool, build, net)
        fee2 = int(tx["transaction"]["fee"])
        if fee2 > fee:  # smaller amounts never cost more, but check
            log.error("payout aborted: fee grew from %d to %d", fee, fee2)
            return
        await self.call(self.wallet, "send_transaction", {"binary_transaction": tx["binary_transaction"]})
        txh = tx["transaction"]["hash"]
        now = time.time()
        with self.store.db:
            for ad, gross in due.items():
                self.store.db.execute("UPDATE balances SET pending = pending - ?, paid = paid + ? WHERE address = ?",
                                      (gross, net[ad], ad))
                self.store.db.execute("INSERT INTO payments (ts, tx, address, gross, fee) VALUES (?,?,?,?,?)",
                                      (now, txh, ad, gross, gross - net[ad]))
        log.info("PAID %d addresses %.8f BCN, fee %.8f, tx %s", len(due), sum(net.values()) / ATOMIC,
                 fee2 / ATOMIC, txh)

    async def find_bad_address(self, build, due):
        for ad in due:
            try:
                await self.loop.run_in_executor(self.rpc_pool, build, {ad: due[ad]})
            except RpcError as ex:
                if "address" in str(ex).lower():
                    return ad
        return None

    async def stats(self):
        os.makedirs(os.path.join(self.args.stats_dir, "miners"), exist_ok=True)
        while True:
            try:
                self.write_stats()
            except Exception as ex:
                log.error("stats failed: %s", ex)
            await asyncio.sleep(30)

    def write_stats(self):
        now = time.time()
        while self.recent and self.recent[0][0] < now - 3600:
            self.recent.popleft()
        win = 600
        per_addr, workers = defaultdict(int), defaultdict(set)
        for ts, ad, wk, diff in self.recent:
            if ts >= now - win:
                per_addr[ad] += diff
                workers[ad].add(wk)
        db = self.store.db
        blocks = [dict(zip(("height", "hash", "reward", "ts", "status"), r)) for r in db.execute(
            "SELECT height, hash, reward, ts, status FROM blocks ORDER BY height DESC LIMIT 50")]
        pays = [dict(zip(("ts", "tx", "addresses", "amount"), r)) for r in db.execute(
            "SELECT ts, tx, COUNT(*), SUM(gross - fee) FROM payments GROUP BY tx ORDER BY ts DESC LIMIT 50")]
        out = {"updated": int(now), "fee_percent": 0, "min_payout": self.args.min_payout,
               "confirmations": self.args.confirmations, "pplns_factor": self.args.pplns_factor,
               "pool": {"hashrate": int(sum(per_addr.values()) / win), "miners": len(per_addr),
                        "workers": sum(len(w) for w in workers.values()),
                        "blocks_found": db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0],
                        "total_paid": db.execute("SELECT COALESCE(SUM(gross - fee),0) FROM payments").fetchone()[0]},
               "network": {"height": self.height, "difficulty": self.net_diff,
                           "hashrate": int(self.net_diff / 120) if self.net_diff else 0},
               "node_ok": self.can_mine, "blocks": blocks, "payments": pays}
        self._write(os.path.join(self.args.stats_dir, "stats.json"), out)
        for ad, pending, paid in db.execute("SELECT address, pending, paid FROM balances"):
            mine = [dict(zip(("ts", "tx", "amount"), r)) for r in db.execute(
                "SELECT ts, tx, gross - fee FROM payments WHERE address = ? ORDER BY ts DESC LIMIT 20", (ad,))]
            self._write(os.path.join(self.args.stats_dir, "miners", ad + ".json"),
                        {"updated": int(now), "hashrate": int(per_addr.get(ad, 0) / win),
                         "workers": sorted(workers.get(ad, ())), "pending": pending, "paid": paid, "payments": mine})
        for ad in per_addr:  # miners with no balance yet
            path = os.path.join(self.args.stats_dir, "miners", ad + ".json")
            if not db.execute("SELECT 1 FROM balances WHERE address = ?", (ad,)).fetchone():
                self._write(path, {"updated": int(now), "hashrate": int(per_addr[ad] / win),
                                   "workers": sorted(workers[ad]), "pending": 0, "paid": 0, "payments": []})

    @staticmethod
    def _write(path, obj):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bytecoind", default="http://127.0.0.1:8081/json_rpc")
    p.add_argument("--walletd", default="http://127.0.0.1:18070/json_rpc")
    p.add_argument("--pool-address", default=os.environ.get("POOL_ADDRESS"), help="default: first walletd address")
    p.add_argument("--listen", default="0.0.0.0:3333")
    p.add_argument("--db", default="/var/lib/bcn-pool/pool.db")
    p.add_argument("--stats-dir", default="/var/lib/bcn-pool/api")
    p.add_argument("--helper", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "libbcnhelper.so"))
    p.add_argument("--external-nodes", default=os.environ.get("BCN_EXTERNAL_NODES", EXTERNAL_NODES))
    p.add_argument("--start-diff", type=int, default=5000)
    p.add_argument("--min-diff", type=int, default=1000)
    p.add_argument("--max-diff", type=int, default=50000000)
    p.add_argument("--share-time", type=float, default=15, help="seconds between shares that vardiff aims at")
    p.add_argument("--confirmations", type=int, default=20, help="mined coins unlock after 10; 20 also covers reorgs")
    p.add_argument("--pplns-factor", type=int, default=2, help="PPLNS window = factor x network difficulty")
    p.add_argument("--min-payout", type=int, default=10000000, help="atomic units (1 BCN = 1e8)")
    p.add_argument("--max-outputs", type=int, default=50)
    p.add_argument("--anonymity", type=int, default=3)
    p.add_argument("--payout-interval", type=float, default=3600)
    p.add_argument("--refresh", type=float, default=30)
    p.add_argument("--poll", type=float, default=1)
    p.add_argument("--network-check", type=float, default=20)
    p.add_argument("--hash-threads", type=int, default=2)
    p.add_argument("--max-per-ip", type=int, default=32)
    p.add_argument("--idle-timeout", type=float, default=600)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pool = Pool(args)
    host, port = args.listen.rsplit(":", 1)
    loop = pool.loop
    server = loop.run_until_complete(asyncio.start_server(lambda r, w: Session(pool, r, w).run(), host, int(port),
                                                          limit=8192))
    log.info("pool listening on %s, fee 0%%, PPLNS %dx, min payout %.8f BCN", args.listen, args.pplns_factor,
             args.min_payout / ATOMIC)
    for task in (pool.watch_node(), pool.watch_network(), pool.mature_blocks(), pool.payouts(), pool.stats()):
        loop.create_task(task)
    try:
        loop.run_forever()
    finally:
        server.close()


if __name__ == "__main__":
    main()
