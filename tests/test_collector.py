"""Accounting and read-only contract tests against a small real SQLite fixture."""
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / 'runtime' / 'collector.py'
spec = importlib.util.spec_from_file_location('collector', MODULE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def request(**overrides):
    row = dict(turn_id='turn-1', status='completed', started_at=1000,
               first_token_at=2000, completed_at=3000, input_tokens=100,
               output_tokens=20, cache_read_input_tokens=80,
               cache_creation_input_tokens=0)
    row.update(overrides)
    total = (row['input_tokens'] + row['output_tokens']
             if collector.number(row['input_tokens']) and collector.number(row['output_tokens']) else 0)
    row.setdefault('provider_total_tokens', total)
    row.setdefault('computed_total_tokens', total)
    row.setdefault('raw_usage_json', json.dumps({
        'inputTokens': row['input_tokens'], 'outputTokens': row['output_tokens'],
        'cacheReadTokens': row['cache_read_input_tokens'],
        'cacheWriteTokens': row['cache_creation_input_tokens'],
    }))
    try:
        raw = json.loads(row['raw_usage_json'])
    except (ValueError, TypeError):
        raw = {}
    for flag, key in [('input_known', 'inputTokens'), ('output_known', 'outputTokens'),
                      ('cache_read_known', 'cacheReadTokens'), ('cache_write_known', 'cacheWriteTokens')]:
        row[flag] = isinstance(raw, dict) and collector.number(raw.get(key))
    return row


class AccountingTests(unittest.TestCase):
    def test_decode_speed_weights_duration_and_excludes_first_token_wait(self):
        stats = collector.summarize([
            request(output_tokens=100, first_token_at=2000, completed_at=3000),
            request(turn_id='turn-2', started_at=5000, first_token_at=15000,
                    completed_at=24000, output_tokens=90),
        ])
        self.assertEqual(stats['tps'], 19)  # 190 / 10 seconds, not (100 + 10) / 2.
        self.assertEqual(stats['decodeMs'], 10000)
        self.assertEqual(stats['speedSamples'], 2)

    def test_cached_input_is_not_added_twice_and_hit_rate_is_weighted(self):
        stats = collector.summarize([
            request(input_tokens=100, output_tokens=20, cache_read_input_tokens=80),
            request(input_tokens=900, output_tokens=30, cache_read_input_tokens=450),
        ])
        self.assertEqual(stats['tokens'], 1050)
        self.assertEqual(stats['cacheHit'], 0.53)
        self.assertEqual(stats['tokenSamples'], 2)

    def test_missing_usage_is_unknown_not_zero(self):
        stats = collector.summarize([request(input_tokens=None, output_tokens=None,
                                             cache_read_input_tokens=None)])
        self.assertIsNone(stats['tokens'])
        self.assertIsNone(stats['tps'])
        self.assertIsNone(stats['cacheHit'])
        self.assertEqual(stats['steps'], 1)
        self.assertEqual(stats['tokenSamples'], 0)

    def test_partial_samples_never_pair_another_requests_tokens_and_duration(self):
        stats = collector.summarize([
            request(output_tokens=1000, first_token_at=None),
            request(output_tokens=None, input_tokens=None),
            request(output_tokens=30),
        ])
        self.assertEqual(stats['tps'], 30)
        self.assertEqual(stats['speedSamples'], 1)
        self.assertEqual(stats['tokenSamples'], 2)
        self.assertEqual(stats['steps'], 3)

    def test_zero_output_is_measured_zero_and_empty_session_has_no_speed(self):
        zero = collector.summarize([request(input_tokens=0, output_tokens=0,
                                            cache_read_input_tokens=0)])
        self.assertEqual(zero['tokens'], 0)
        self.assertEqual(zero['tps'], 0)
        self.assertEqual(zero['speedSamples'], 1)
        self.assertIsNone(zero['cacheHit'])
        empty = collector.summarize([])
        self.assertEqual(empty['tokens'], 0)
        self.assertIsNone(empty['tps'])
        self.assertEqual(empty['steps'], 0)

    def test_invalid_timestamps_and_usage_do_not_become_rates(self):
        for fields in (
            {'first_token_at': None}, {'first_token_at': 500},
            {'completed_at': 2000}, {'completed_at': 1500},
            {'output_tokens': -1}, {'output_tokens': float('nan')},
            {'output_tokens': True}, {'output_tokens': '20'},
        ):
            with self.subTest(fields=fields):
                stats = collector.summarize([request(**fields)])
                self.assertIsNone(stats['tps'])
                self.assertEqual(stats['speedSamples'], 0)

    def test_failed_cancelled_and_running_requests_do_not_inflate_completed_usage(self):
        rows = [request(), request(status='error', output_tokens=10000),
                request(status='running', output_tokens=10000),
                request(status='cancelled', output_tokens=10000)]
        stats = collector.summarize(rows)
        self.assertEqual(stats['steps'], 1)
        self.assertEqual(stats['tokens'], 120)
        self.assertEqual(stats['tps'], 20)
        self.assertEqual(stats['errors'], 1)

    def test_repeated_requests_count_steps_but_not_extra_turns(self):
        stats = collector.summarize([request(), request(), request(turn_id='turn-2'),
                                     request(turn_id=''), request(turn_id='  '),
                                     request(turn_id=None)])
        self.assertEqual(stats['steps'], 6)
        self.assertEqual(stats['turns'], 2)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / 'usage.sqlite'
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript('''
                CREATE TABLE session (id TEXT PRIMARY KEY);
                CREATE TABLE model_usage (
                    id TEXT PRIMARY KEY, session_id TEXT, query_source TEXT,
                    turn_id TEXT, status TEXT, started_at INTEGER,
                    first_token_at INTEGER, completed_at INTEGER,
                    input_tokens INTEGER, output_tokens INTEGER,
                    cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER,
                    provider_total_tokens INTEGER, computed_total_tokens INTEGER,
                    raw_usage_json TEXT);
                CREATE INDEX model_usage_session_turn_idx
                    ON model_usage(session_id,turn_id);
                INSERT INTO session VALUES ('session-a'), ('session-b'), ('empty');
            ''')
            columns = [key for key in request() if not key.endswith('_known')]
            sql = 'INSERT INTO model_usage (id,session_id,query_source,' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in range(3 + len(columns))) + ')'
            for key, sid, source, row in [
                ('a1', 'session-a', 'main_turn', request()),
                ('a-bg', 'session-a', 'background', request(output_tokens=99999)),
                ('b1', 'session-b', 'main_turn', request(output_tokens=40)),
                ('b-error', 'session-b', 'main_turn', request(status='error')),
            ]:
                con.execute(sql, (key, sid, source, *(row[k] for k in columns)))

    def update_request(self, **values):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('UPDATE model_usage SET ' + ','.join(key + '=?' for key in values)
                        + " WHERE id='a1'", tuple(values.values()))

    def test_historical_input_excludes_cache_is_normalized_to_full_input(self):
        self.update_request(input_tokens=20, output_tokens=10, cache_read_input_tokens=80,
                            provider_total_tokens=110, computed_total_tokens=110,
                            raw_usage_json=json.dumps({'inputTokens': 20, 'outputTokens': 10,
                                                       'cacheReadTokens': 80, 'cacheWriteTokens': 0}))
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 110)
        self.assertEqual(actual['cacheHit'], 0.8)

    def test_historical_cache_write_included_and_computed_total_is_fallback(self):
        self.update_request(input_tokens=20, output_tokens=10, cache_read_input_tokens=60,
                            cache_creation_input_tokens=20, provider_total_tokens=None,
                            computed_total_tokens=110,
                            raw_usage_json=json.dumps({'inputTokens': 20, 'outputTokens': 10,
                                                       'cacheReadTokens': 60, 'cacheWriteTokens': 20}))
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 110)
        self.assertEqual(actual['cacheHit'], 0.6)

    def test_provider_total_takes_precedence_over_computed_legacy_guess(self):
        self.update_request(input_tokens=100, output_tokens=10, cache_read_input_tokens=80,
                            provider_total_tokens=110, computed_total_tokens=190,
                            raw_usage_json=json.dumps({'inputTokens': 100, 'outputTokens': 10,
                                                       'cacheReadTokens': 80, 'cacheWriteTokens': 0}))
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 110)
        self.assertEqual(actual['cacheHit'], 0.8)

    def test_storage_default_zero_without_usage_evidence_stays_unknown(self):
        for raw in (None, '{}', '{invalid', '{"outputTokens":"0"}', '{"outputTokens":true}'):
            with self.subTest(raw=raw):
                self.update_request(input_tokens=0, output_tokens=0, cache_read_input_tokens=0,
                                    cache_creation_input_tokens=0, provider_total_tokens=None,
                                    computed_total_tokens=0, raw_usage_json=raw)
                actual = collector.snapshot(self.db, ['session-a'])['session-a']
                self.assertIsNone(actual['tokens'])
                self.assertIsNone(actual['tps'])
                self.assertEqual(actual['speedSamples'], 0)
                self.assertEqual(actual['tokenSamples'], 0)
                self.assertEqual(actual['cacheSamples'], 0)

    def test_explicit_raw_zero_is_a_measured_zero(self):
        self.update_request(input_tokens=0, output_tokens=0, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, computed_total_tokens=0,
                            provider_total_tokens=0,
                            raw_usage_json=json.dumps({'inputTokens': 0, 'outputTokens': 0,
                                                       'cacheReadTokens': 0, 'cacheWriteTokens': 0}))
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 0)
        self.assertEqual(actual['tps'], 0)
        self.assertEqual(actual['speedSamples'], 1)
        self.assertEqual(actual['tokenSamples'], 1)

    def test_legacy_nonzero_usage_without_raw_json_remains_usable(self):
        self.update_request(raw_usage_json=None)
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 120)
        self.assertEqual(actual['tps'], 20)
        self.assertEqual(actual['cacheHit'], 0.8)

    def test_missing_cache_usage_does_not_claim_zero_cache_hit(self):
        self.update_request(cache_read_input_tokens=0,
                            raw_usage_json=json.dumps({'inputTokens': 100, 'outputTokens': 20}))
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertIsNone(actual['cacheHit'])
        self.assertEqual(actual['cacheSamples'], 0)
        self.assertEqual(actual['tokens'], 120)

    def test_exact_session_and_main_turn_filter(self):
        actual = collector.snapshot(self.db, ['session-a', 'session-b'])
        self.assertEqual(actual['session-a']['tokens'], 120)
        self.assertEqual(actual['session-a']['steps'], 1)
        self.assertEqual(actual['session-b']['tokens'], 140)
        self.assertEqual(actual['session-b']['tps'], 40)
        self.assertEqual(actual['session-b']['errors'], 1)

    def test_unknown_session_does_not_fall_back_to_last_session(self):
        result = collector.snapshot(self.db, ['unknown', 'empty'])
        self.assertEqual(result['unknown'], {'error': 'session-unavailable'})
        self.assertEqual(result['empty']['steps'], 0)
        self.assertIsNone(result['empty']['tps'])

    def test_session_id_is_bound_parameter(self):
        sid = "' OR 1=1 --"
        self.assertEqual(collector.snapshot(self.db, [sid])[sid],
                         {'error': 'session-unavailable'})

    def test_snapshot_leaves_database_bytes_schema_and_directory_unchanged(self):
        def digest():
            return hashlib.sha256(self.db.read_bytes()).hexdigest()
        def schema():
            with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as con:
                return con.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        before_hash, before_schema = digest(), schema()
        before_names = sorted(p.name for p in self.db.parent.iterdir())
        for _ in range(3):
            collector.snapshot(self.db, ['session-a', 'session-b', 'unknown'])
        self.assertEqual(digest(), before_hash)
        self.assertEqual(schema(), before_schema)
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), before_names)

    def test_missing_database_is_not_created(self):
        missing = self.db.parent / 'does-not-exist.sqlite'
        with self.assertRaises(sqlite3.OperationalError):
            collector.snapshot(missing, ['session-a'])
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
