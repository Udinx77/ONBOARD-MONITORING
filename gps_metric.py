"""Jumlah satelit GPS per unit dari query SQL (query_gps.sql) dan aturan warna lampu G.

Aturan: Satellites NULL atau < 12 merah, 12-13 kuning, 13.1 ke atas hijau. Hijau = GPS normal; kuning dan merah = GPS error. Data diambil tiap GPS_QUERY_REFRESH_MINUTES (bawaan 5 menit).
Aturan GPS bisa berubah lagi: ubah query_gps.sql (sumber), GPS_METRIC_COLUMN (kolom nilai), atau ambang (GPS_RED_BELOW, GPS_YELLOW_MAX) di .env.
Cek isi query dari terminal: python gps_metric.py
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from config import (
    GPS_METRIC_AGGREGATE,
    GPS_METRIC_COLUMN,
    GPS_QUERY_FILE,
    GPS_QUERY_REFRESH_MINUTES,
    GPS_QUERY_WINDOW_MINUTES,
    GPS_RED_BELOW,
    GPS_YELLOW_MAX,
)

LOGGER = logging.getLogger("gps_metric")
WITA = timezone(timedelta(hours=8))
_FMT = "%Y-%m-%d %H:%M:%S"
_OID_COLUMNS = ("oid", "machine_oid", "machineoid", "machine oid", "parentoid")
_UNIT_COLUMNS = ("nama truck", "nama_truck", "truck", "unit", "sn unit", "name", "primarymachinename", "machine", "machinename")
_METRIC_FALLBACKS = ("satellites", "satellite", "satelit", "jumlah satelit", "num_satellites", "sat")
_TIME_HINTS = ("time", "waktu", "tanggal", "date", "minute", "menit")
_AGGREGATES = ("last", "avg", "min", "max", "sum")


def _has_sql(text: str) -> bool:
    """True bila file berisi pernyataan SQL selain komentar dan spasi."""
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    stripped = re.sub(r"--[^\n]*", "", stripped)
    return bool(stripped.strip())


def _run_query(connect=None, query_file=None, window_minutes: float | None = None, now: datetime | None = None):
    """Jalankan query GPS; return (nama kolom, baris)."""
    minutes = GPS_QUERY_WINDOW_MINUTES if window_minutes is None else window_minutes
    end = (now or datetime.now(timezone.utc)).astimezone(WITA)
    start = end - timedelta(minutes=minutes)
    sql = (query_file or GPS_QUERY_FILE).read_text(encoding="utf-8-sig")
    if not _has_sql(sql):
        raise ValueError("query_gps.sql belum berisi query")
    sql = sql.replace("__START_WITA__", start.strftime(_FMT)).replace("__END_WITA__", end.strftime(_FMT))
    if connect is None:
        from sql_server import connect
    conn = connect()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return [str(c[0]) for c in cursor.description], cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()


def _number(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def fetch_gps_values(connect=None, query_file=None, window_minutes: float | None = None, now: datetime | None = None,
                     column: str | None = None, aggregate: str | None = None):
    """(per OID, per NAMA_HURUF_BESAR) -> jumlah satelit (float) atau None bila datanya NULL.

    Unit yang muncul dengan nilai NULL tetap dikembalikan sebagai None (lampu merah); unit yang tidak muncul tidak ada di hasil.
    Beberapa baris per unit digabung dengan `aggregate`; 'last' memakai baris dengan waktu terbaru (kolom waktu bila ada, selain itu baris terakhir).
    """
    column = GPS_METRIC_COLUMN if column is None else column
    aggregate = GPS_METRIC_AGGREGATE if aggregate is None else aggregate
    if not column:
        raise ValueError("GPS_METRIC_COLUMN belum diisi di .env")
    if aggregate not in _AGGREGATES:
        raise ValueError(f"GPS_METRIC_AGGREGATE harus salah satu dari {_AGGREGATES}")
    columns, rows = _run_query(connect, query_file, window_minutes, now)
    lowered = {c.lower(): i for i, c in enumerate(columns)}
    find = lambda names: next((lowered[n] for n in names if n in lowered), None)
    value_idx = find((column.lower(),) + (_METRIC_FALLBACKS if column.lower() in _METRIC_FALLBACKS else ()))
    oid_idx, unit_idx = find(_OID_COLUMNS), find(_UNIT_COLUMNS)
    time_idx = next((i for c, i in lowered.items() if any(h in c for h in _TIME_HINTS) and i not in (value_idx, oid_idx, unit_idx)), None)
    if value_idx is None or (oid_idx is None and unit_idx is None):
        raise ValueError(f"Kolom tidak ditemukan. Dibutuhkan kolom '{column}' dan OID atau nama unit; kolom hasil query: {columns}")

    groups: dict[object, dict] = {}
    for n, raw in enumerate(rows):
        try:
            oid = int(float(raw[oid_idx])) if oid_idx is not None and raw[oid_idx] is not None else None
        except (TypeError, ValueError):
            oid = None
        name = str(raw[unit_idx] or "").strip().upper() if unit_idx is not None else ""
        key = oid if oid is not None else name
        if key in (None, ""):
            continue
        g = groups.setdefault(key, {"oid": oid, "name": name, "rows": []})
        g["name"] = g["name"] or name
        g["rows"].append((raw[time_idx] if time_idx is not None else None, n, _number(raw[value_idx])))

    def pick(items):
        if aggregate == "last":
            try:
                return max(items, key=lambda r: (r[0] is not None, r[0], r[1]))[2]
            except TypeError:                      # tipe waktu bercampur: pakai urutan baris
                return max(items, key=lambda r: r[1])[2]
        values = [r[2] for r in items if r[2] is not None]
        if not values:
            return None
        return {"avg": sum(values) / len(values), "min": min(values), "max": max(values), "sum": sum(values)}[aggregate]

    by_oid: dict[int, float | None] = {}
    by_name: dict[str, float | None] = {}
    for g in groups.values():
        value = pick(g["rows"])
        if g["oid"] is not None:
            by_oid[g["oid"]] = value
        if g["name"]:
            by_name[g["name"]] = value
    return by_oid, by_name


def gps_state(value: float | None, found: bool = True, red_below: float | None = None, yellow_max: float | None = None) -> str | None:
    """Warna lampu G dari jumlah satelit: 'crit' merah (NULL atau < red_below, di bawah 12), 'warn' kuning (sampai yellow_max, 12-13),
    'ok' hijau (di atasnya, 13.1 ke atas). None bila unit tidak ada datanya."""
    if not found:
        return None
    if value is None:
        return "crit"
    red = GPS_RED_BELOW if red_below is None else red_below
    yellow = GPS_YELLOW_MAX if yellow_max is None else yellow_max
    return "crit" if value < red else "warn" if value <= yellow else "ok"


def gps_normal(found: bool, value: float | None, has_ip: bool, ping_status: str | None) -> bool | None:
    """GPS normal untuk filter dashboard = lampu G hijau. Ada data satelit: satelit 13.1 ke atas. Tanpa data satelit: ping GPS Green. None = tidak bisa dinilai."""
    state = gps_state(value, found)
    if state is not None:
        return state == "ok"
    if has_ip and ping_status in ("Green", "Yellow", "Orange", "Red"):
        return ping_status == "Green"
    return None


def gps_error(found: bool, value: float | None, has_ip: bool, ping_status: str | None) -> bool | None:
    """GPS error = tidak normal: lampu G kuning atau merah. Tanpa data satelit: ping GPS Yellow, Orange, atau Red. None = tidak bisa dinilai."""
    normal = gps_normal(found, value, has_ip, ping_status)
    return None if normal is None else not normal


def satellite_mode(column: str | None = None, query_file=None) -> bool:
    """True bila GPS dinilai dari satelit: GPS_METRIC_COLUMN terisi dan query_gps.sql berisi query. Dipakai dashboard dan collector."""
    col = GPS_METRIC_COLUMN if column is None else column
    path = query_file or GPS_QUERY_FILE
    try:
        return bool(col) and _has_sql(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return False


class GpsCache:
    """Menyimpan data satelit terakhir; diperbarui di thread terpisah supaya dashboard tidak menunggu query."""

    def __init__(self, connect=None, column: str | None = None, query_file=None, on_update=None):
        self._connect = connect
        self._on_update = on_update
        self._query_file = query_file
        self.column = GPS_METRIC_COLUMN if column is None else column
        self.by_oid: dict[int, float | None] = {}
        self.by_name: dict[str, float | None] = {}
        self.fetched_at = 0.0
        self.max_age = max(3 * GPS_QUERY_REFRESH_MINUTES * 60, 180.0)  # data satelit lebih tua dari ini tidak dipakai (hindari warna basi)
        self.ok: bool | None = None
        self._busy = False
        self._next = 0.0
        self._lock = threading.Lock()
        self.enabled = satellite_mode(self.column, query_file)
        if self.column and not self.enabled:
            LOGGER.info("query_gps.sql belum berisi query; lampu G memakai ping GPS.")

    def get(self, oid: int | None, name: str | None) -> tuple[bool, float | None]:
        """(ada di hasil query, nilai). Data yang basi (query gagal berulang) dianggap tidak ada: lampu G kembali memakai ping."""
        if self.fetched_at and time.time() - self.fetched_at > self.max_age:
            return False, None
        if oid is not None and oid in self.by_oid:
            return True, self.by_oid[oid]
        key = str(name or "").strip().upper()
        if key in self.by_name:
            return True, self.by_name[key]
        return False, None

    def refresh_async(self) -> None:
        if not self.enabled or self._busy or time.monotonic() < self._next:
            return
        with self._lock:
            if self._busy:
                return
            self._busy = True
        threading.Thread(target=self._run, name="gps-metric", daemon=True).start()

    def _run(self) -> None:
        started = time.monotonic()
        try:
            self.by_oid, self.by_name = fetch_gps_values(self._connect, self._query_file, column=self.column)
            self.fetched_at = time.time()
            if self.ok is not True:
                LOGGER.info("Data satelit GPS dimuat: %s unit (kolom '%s').", len(self.by_name) or len(self.by_oid), self.column)
            self.ok = True
            if self._on_update is not None:
                try:
                    self._on_update(self)  # mis. mencatat sampel availability GPS
                except Exception:
                    LOGGER.exception("Callback data GPS gagal.")
            self._next = started + GPS_QUERY_REFRESH_MINUTES * 60  # kadensi tetap dari awal query: jendela 1 menit tidak punya celah
        except Exception as exc:
            if self.ok is not False:
                LOGGER.warning("Data satelit GPS gagal dimuat (%s). Lampu G memakai ping GPS.", exc)
            self.ok = False
            self._next = time.monotonic() + min(GPS_QUERY_REFRESH_MINUTES, 2) * 60
        finally:
            self._busy = False


if __name__ == "__main__":  # python gps_metric.py : lihat kolom, contoh isi, dan warna lampu hasil query
    cols, rows = _run_query()
    print("Kolom hasil query:", cols)
    for row in rows[:8]:
        print("  ", list(row))
    print(f"({len(rows)} baris)")
    by_oid, by_name = fetch_gps_values()
    states = {}
    for name, value in by_name.items():
        states[gps_state(value)] = states.get(gps_state(value), 0) + 1
    print(f"Unit terbaca: {len(by_oid) or len(by_name)} | kolom '{GPS_METRIC_COLUMN}' ({GPS_METRIC_AGGREGATE}) | warna: {states}")
    for name, value in sorted(by_name.items())[:8]:
        print(f"   {name}: {value} -> {gps_state(value)}")
