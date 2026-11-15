"""Cek cepat jumlah satelit GPS dari query dan warna lampu G: python test_gps_metric.py"""
import sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, ".")
import gps_metric as g

COLS = ["OID", "Nama Truck", "Satellites", "Waktu"]
T = lambda m: datetime(2026, 11, 6, 4, m)                      # menit ke-m
ROWS = [(101, "CT7261", 18, T(1)), (101, "CT7261", 14, T(2)),     # baris terakhir (14) yang dipakai
        (102, "CT7262", 12, T(2)), (102, "CT7262", None, T(3)),   # NULL terbaru -> merah, walau menit sebelumnya ada nilai
        (103, "KT8001", None, T(2)),                              # NULL -> merah
        (104, "KT8002", 15, T(3)), (104, "KT8002", 13, T(1)),     # urutan baris terbalik: tetap pakai waktu terbaru (15)
        (105, "KT8003", 13, T(3))]
seen = []
class Cur:
    def __init__(self, c, r): self.description, self._r = [(x,) for x in c], r
    def execute(self, sql): seen.append(sql)
    def fetchall(self): return self._r
    def close(self): pass
class Conn:
    def __init__(self, c, r): self._c, self._r = c, r
    def cursor(self): return Cur(self._c, self._r)
    def close(self): pass
fake = lambda c=COLS, r=ROWS: (lambda: Conn(c, r))
tmp = Path(tempfile.mkdtemp())
q = tmp / "q.sql"; q.write_text("SELECT OID, [Nama Truck], Satellites, Waktu FROM x WHERE a >= '__START_WITA__' AND a < '__END_WITA__'", encoding="utf-8")
now = datetime(2026, 11, 6, 4, 0, tzinfo=timezone.utc)           # 12:00 WITA

# aturan warna: NULL atau <12 merah, 12-13 kuning (batas atas inklusif), 13.1 ke atas hijau
S = lambda v: g.gps_state(v, True, 12, 13)
for value, state in ((None, "crit"), (0, "crit"), (11, "crit"), (11.99, "crit"), (12, "warn"), (12.5, "warn"), (13, "warn"),
                     (13.1, "ok"), (13.5, "ok"), (14, "ok"), (14.1, "ok"), (15, "ok"), (24, "ok")):
    assert S(value) == state, (value, state, S(value))
assert g.gps_state(None, False) is None                           # unit tidak ada di hasil query: tidak dinilai

# query: token WITA diisi, nilai terbaru per unit (per OID dan per nama), NULL tetap tercatat sebagai None
by_oid, by_name = g.fetch_gps_values(fake(), q, now=now, column="Satellites")
assert "'2026-11-06 11:55:00'" in seen[0] and "'2026-11-06 12:00:00'" in seen[0] and "__" not in seen[0], seen[0]      # jendela bawaan 5 menit (WITA)
assert "'2026-11-06 11:00:00'" in (seen.clear() or g._run_query(fake(), q, window_minutes=60, now=now) and seen[0])           # jendela bisa diatur
assert by_oid == {101: 14.0, 102: None, 103: None, 104: 15.0, 105: 13.0}, by_oid
assert by_name["CT7261"] == 14.0 and by_name["CT7262"] is None and by_name["KT8002"] == 15.0
assert g.fetch_gps_values(fake(), q, now=now, column="satellites", aggregate="min")[0][101] == 14.0    # nama kolom tak peka huruf besar-kecil
assert g.fetch_gps_values(fake(), q, now=now, aggregate="max")[0][101] == 18.0 and g.fetch_gps_values(fake(), q, now=now, aggregate="avg")[0][101] == 16.0
assert g.fetch_gps_values(fake(), q, now=now, aggregate="max")[0][102] == 12.0                           # NULL dilewati pada agregat angka

# tanpa kolom OID: cocokkan per nama; tanpa kolom waktu: baris terakhir
o, n = g.fetch_gps_values(fake(["Truck", "Satellite"], [("CT1", 16), ("CT1", 9)]), q, now=now)
assert o == {} and n == {"CT1": 9.0}, (o, n)
for bad in ({"column": ""}, {"column": "Akurasi"}, {"aggregate": "median"}):
    try:
        g.fetch_gps_values(fake(), q, now=now, **bad); raise AssertionError(bad)
    except ValueError:
        pass

# query kosong (hanya komentar): tidak dijalankan, tidak error
empty = tmp / "e.sql"; empty.write_text("/* tempel query di sini */\n-- komentar", encoding="utf-8")
assert g.GpsCache(connect=fake(), column="Satellites", query_file=empty).enabled is False
assert g.satellite_mode("Satellites", q) is True and g.satellite_mode("Satellites", empty) is False and g.satellite_mode("", q) is False
try:
    g.fetch_gps_values(fake(), empty, now=now); raise AssertionError("query kosong")
except ValueError as exc:
    assert "belum berisi query" in str(exc)

# GPS normal = hijau; GPS error = tidak normal (kuning atau merah), tidak pernah keduanya; tanpa data satelit memakai ping
N = lambda v: g.gps_normal(True, v, False, None)
E = lambda v: g.gps_error(True, v, False, None)
for v, normal, error in ((None, False, True), (11, False, True), (12, False, True), (13, False, True), (13.1, True, False), (14, True, False), (14.1, True, False), (20, True, False)):
    assert (N(v), E(v)) == (normal, error), (v, N(v), E(v))
assert g.gps_normal(True, 20, True, "Red") is True and g.gps_normal(True, 12, True, "Green") is False   # data satelit menang atas ping
assert g.gps_normal(False, None, True, "Green") is True and g.gps_normal(False, None, True, "Yellow") is False   # ping: hanya Green = normal
assert g.gps_normal(False, None, True, "Orange") is False and g.gps_normal(False, None, False, None) is None
assert g.gps_error(False, None, True, "Red") is True and g.gps_error(False, None, True, "Orange") is True and g.gps_error(False, None, True, "Yellow") is True
assert g.gps_error(False, None, True, "Green") is False
assert g.gps_error(False, None, True, "N/A") is None and g.gps_error(False, None, False, None) is None

# query_gps.sql asli (revisi user): token terisi, kolom MACHINE_OID/TRUCK/SATELLITES terbaca, unit tanpa data = NULL = merah
REAL_COLS = ["MACHINE_OID", "TRUCK", "CLASS_ID", "EVENTSOURCE", "TIMESTAMP_WITA", "LOCATION_X", "LOCATION_Y", "LOCATION_Z", "SATELLITES", "NEW_STATE_DESCRIPTION", "GPS_DATA_STATUS"]
row = lambda oid, name, sat, ts: (oid, name, "PositionReport" if ts else None, name if ts else None, ts, 1.0, 2.0, 3.0, sat, None, "GPS DATA AVAILABLE" if ts else "NO GPS DATA")
REAL = [row(201, "CT7001", 17, T(3)), row(202, "CT7002", 14, T(3)), row(203, "CT7003", 12, T(3)), row(206, "CT7006", 9, T(3)),
        row(204, "CB6001", None, T(3)),            # ada laporan posisi, satelit NULL
        row(205, "KT8100", None, None)]            # tanpa PositionReport di jendela (LEFT JOIN): semua kolom G NULL
seen.clear()
by_oid, by_name = g.fetch_gps_values(fake(REAL_COLS, REAL), Path("query_gps.sql"), now=now)
assert "__START_WITA__" not in seen[0] and "__END_WITA__" not in seen[0] and "'2026-11-06 11:55:00'" in seen[0] and "'2026-11-06 12:00:00'" in seen[0]
assert by_oid == {201: 17.0, 202: 14.0, 203: 12.0, 206: 9.0, 204: None, 205: None}, by_oid
assert by_name["CB6001"] is None and by_name["KT8100"] is None
assert [S(by_oid[o]) for o in (201, 202, 203, 206, 204, 205)] == ["ok", "ok", "warn", "crit", "crit", "crit"]
assert g.GpsCache(connect=fake(REAL_COLS, REAL), column="Satellites", query_file=Path("query_gps.sql")).enabled is True

# cache: lookup per OID lalu nama; gagal tidak merusak; hanya aktif bila ada query dan kolom; callback dipanggil setelah data baru
called = []
cache = g.GpsCache(connect=fake(), column="Satellites", query_file=q, on_update=lambda c: called.append(c.get(101, "x"))); assert cache.enabled; cache._run()
assert cache.ok is True and cache.get(101, "x") == (True, 14.0) and cache.get(None, "ct7262") == (True, None) and cache.get(999, "ZZ") == (False, None)
assert called == [(True, 14.0)], called
def boom(): raise OSError("SQL Server tidak terjangkau")
bad = g.GpsCache(connect=boom, column="Satellites", query_file=q); bad._run()
assert bad.ok is False and bad.by_oid == {} and bad.get(101, None) == (False, None)
assert g.GpsCache(connect=fake(), column="", query_file=q).enabled is False

# data basi: setelah max_age tanpa refresh berhasil, unit dianggap tanpa data (kembali ke ping); kadensi tetap dari awal query
import time as _t
stale = g.GpsCache(connect=fake(), column="Satellites", query_file=q); stale._run()
assert stale.get(101, None) == (True, 14.0)
stale.fetched_at = _t.time() - stale.max_age - 1
assert stale.get(101, None) == (False, None) and stale.max_age >= 180
fresh = g.GpsCache(connect=fake(), column="Satellites", query_file=q); t0 = _t.monotonic(); fresh._run()
assert abs((fresh._next - t0) - g.GPS_QUERY_REFRESH_MINUTES * 60) <= 1, fresh._next - t0   # kadensi 5 menit (bawaan)
print("OK: satelit GPS dari query (<12 merah, 12-13 kuning, 13.1+ hijau; normal = hijau)")
