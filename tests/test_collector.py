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

    def test_model_time_and_average_first_token_latency_use_separate_valid_samples(self):
        stats = collector.summarize([
            request(started_at=1000, first_token_at=2000, completed_at=4000),
            request(started_at=10000, first_token_at=13000, completed_at=14000),
            request(started_at=20000, first_token_at=None, completed_at=21000),
            request(started_at=30000, first_token_at=29000, completed_at=28000),
            request(status='error', started_at=0, first_token_at=100, completed_at=99999),
        ])
        self.assertEqual(stats['modelMs'], 8000)
        self.assertEqual(stats['modelSamples'], 3)
        self.assertEqual(stats['ttftMs'], 4000)
        self.assertEqual(stats['ttftSamples'], 2)
        self.assertEqual(stats['ttftMs'] / stats['ttftSamples'], 2000)

    def test_token_breakdown_preserves_complete_partition_without_double_counting(self):
        stats = collector.summarize([
            request(input_tokens=100, output_tokens=20, cache_read_input_tokens=70,
                    cache_creation_input_tokens=10),
            request(input_tokens=900, output_tokens=30, cache_read_input_tokens=400,
                    cache_creation_input_tokens=100),
        ])
        self.assertEqual(stats['inputTokens'], 1000)
        self.assertEqual(stats['outputTokens'], 50)
        self.assertEqual(stats['cacheReadTokens'], 470)
        self.assertEqual(stats['cacheWriteTokens'], 110)
        self.assertEqual(stats['uncachedInputTokens'], 420)
        self.assertEqual(stats['nonCacheReadInputTokens'], 530)
        self.assertEqual(stats['uncachedInputTokens'] + stats['cacheReadTokens']
                         + stats['cacheWriteTokens'] + stats['outputTokens'], stats['tokens'])
        for key in ('inputSamples', 'outputSamples', 'cacheReadSamples',
                    'cacheWriteSamples', 'uncachedInputSamples', 'nonCacheReadInputSamples',
                    'breakdownSamples'):
            self.assertEqual(stats[key], 2)

    def test_unknown_cache_write_does_not_make_uncached_input_a_guess(self):
        stats = collector.summarize([request(raw_usage_json=json.dumps({
            'inputTokens': 100, 'outputTokens': 20, 'cacheReadTokens': 80}))])
        self.assertEqual(stats['inputTokens'], 100)
        self.assertEqual(stats['cacheReadTokens'], 80)
        self.assertEqual(stats['outputTokens'], 20)
        self.assertEqual(stats['nonCacheReadInputTokens'], 20)
        self.assertEqual(stats['nonCacheReadInputSamples'], 1)
        self.assertIsNone(stats['cacheWriteTokens'])
        self.assertIsNone(stats['uncachedInputTokens'])
        self.assertEqual(stats['cacheWriteSamples'], 0)
        self.assertEqual(stats['uncachedInputSamples'], 0)
        self.assertEqual(stats['breakdownSamples'], 0)

    def test_partial_breakdown_has_per_metric_coverage(self):
        stats = collector.summarize([
            request(),
            request(input_tokens=100, output_tokens=0,
                    raw_usage_json=json.dumps({'inputTokens': 100, 'cacheReadTokens': 80})),
        ])
        self.assertEqual(stats['inputTokens'], 200)
        self.assertEqual(stats['inputSamples'], 2)
        self.assertEqual(stats['outputTokens'], 20)
        self.assertEqual(stats['outputSamples'], 1)
        self.assertEqual(stats['cacheReadTokens'], 160)
        self.assertEqual(stats['cacheReadSamples'], 2)
        self.assertEqual(stats['nonCacheReadInputTokens'], 40)
        self.assertEqual(stats['nonCacheReadInputSamples'], 2)
        self.assertEqual(stats['uncachedInputTokens'], 20)
        self.assertEqual(stats['uncachedInputSamples'], 1)
        self.assertEqual(stats['breakdownSamples'], 1)

    def test_impossible_cache_partition_does_not_produce_negative_uncached_tokens(self):
        stats = collector.summarize([request(input_tokens=100, cache_read_input_tokens=80,
                                             cache_creation_input_tokens=40)])
        self.assertIsNone(stats['uncachedInputTokens'])
        self.assertEqual(stats['uncachedInputSamples'], 0)
        self.assertEqual(stats['breakdownSamples'], 0)

    def test_non_cache_read_input_requires_paired_valid_input_and_cache_read(self):
        for fields in (
            {'input_tokens': None},
            {'cache_read_input_tokens': 0, 'raw_usage_json': '{"inputTokens":100}'},
            {'cache_read_input_tokens': 120},
        ):
            with self.subTest(fields=fields):
                stats = collector.summarize([request(**fields)])
                self.assertIsNone(stats['nonCacheReadInputTokens'])
                self.assertEqual(stats['nonCacheReadInputSamples'], 0)
        measured_zero = collector.summarize([request(input_tokens=100, cache_read_input_tokens=100)])
        self.assertEqual(measured_zero['nonCacheReadInputTokens'], 0)
        self.assertEqual(measured_zero['nonCacheReadInputSamples'], 1)
        self.assertEqual(collector.summarize([])['nonCacheReadInputTokens'], 0)

    def test_missing_timing_is_unknown_but_zero_timing_is_measured(self):
        missing = collector.summarize([request(started_at=None, completed_at=None)])
        self.assertIsNone(missing['modelMs'])
        self.assertIsNone(missing['ttftMs'])
        self.assertEqual(missing['modelSamples'], 0)
        zero = collector.summarize([request(started_at=1000, first_token_at=1000, completed_at=1000)])
        self.assertEqual(zero['modelMs'], 0)
        self.assertEqual(zero['modelSamples'], 1)
        self.assertEqual(zero['ttftMs'], 0)
        self.assertEqual(zero['ttftSamples'], 1)
        self.assertIsNone(zero['tps'])


class ToolTimingTests(unittest.TestCase):
    def test_real_tool_intervals_sum_parallel_overlap_and_ignore_running_calls(self):
        stats = collector.summarize_tools([
            {'status': 'completed', 'started_at': 1000, 'completed_at': 4000},
            {'status': 'error', 'started_at': 2000, 'completed_at': 3000},
            {'status': 'cancelled', 'started_at': 5000, 'completed_at': 5500},
            {'status': 'running', 'started_at': 0, 'completed_at': 1000000},
        ])
        self.assertEqual(stats, {'toolMs': 4500, 'toolSamples': 3, 'toolCalls': 3})

    def test_tool_zero_unknown_and_missing_surface_remain_distinct(self):
        self.assertEqual(collector.summarize_tools(None),
                         {'toolMs': None, 'toolSamples': 0, 'toolCalls': None})
        self.assertEqual(collector.summarize_tools([]),
                         {'toolMs': 0, 'toolSamples': 0, 'toolCalls': 0})
        self.assertEqual(collector.summarize_tools([
            {'status': 'completed', 'started_at': 1000, 'completed_at': 1000}]),
            {'toolMs': 0, 'toolSamples': 1, 'toolCalls': 1})
        self.assertEqual(collector.summarize_tools([
            {'status': 'completed', 'started_at': 1000, 'completed_at': None},
            {'status': 'error', 'started_at': 2000, 'completed_at': 1000}]),
            {'toolMs': None, 'toolSamples': 0, 'toolCalls': 2})


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
                CREATE TABLE tool_usage (
                    id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT,
                    status TEXT, started_at INTEGER, completed_at INTEGER);
                INSERT INTO session VALUES ('session-a'), ('session-b'), ('empty');
            ''')
            columns = [key for key in request() if not key.endswith('_known')]
            sql = 'INSERT INTO model_usage (id,session_id,query_source,' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in range(3 + len(columns))) + ')'
            for key, sid, source, row in [
                ('a1', 'session-a', 'main_turn', request()),
                ('a-bg', 'session-a', 'background', request(turn_id='background-turn', output_tokens=99999)),
                ('b1', 'session-b', 'main_turn', request(output_tokens=40)),
                ('b-error', 'session-b', 'main_turn', request(status='error')),
            ]:
                con.execute(sql, (key, sid, source, *(row[k] for k in columns)))
            con.executemany('INSERT INTO tool_usage VALUES (?,?,?,?,?,?)', [
                ('tool-a1', 'session-a', 'turn-1', 'completed', 1500, 3500),
                ('tool-a2', 'session-a', 'turn-1', 'error', 2000, 2500),
                ('tool-a3', 'session-a', 'turn-1', 'completed', 3000, None),
                ('tool-running', 'session-a', 'turn-1', 'running', 3000, 99999),
                ('tool-background', 'session-a', 'background-turn', 'completed', 0, 99999),
                ('tool-unknown', 'session-a', None, 'completed', 0, 99999),
                ('tool-b', 'session-b', 'turn-1', 'completed', 0, 7000),
            ])

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
        self.assertEqual(actual['inputTokens'], 100)
        self.assertEqual(actual['uncachedInputTokens'], 20)
        self.assertEqual(actual['outputTokens'], 10)
        self.assertEqual(actual['breakdownSamples'], 1)

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

    def test_tools_filter_exact_session_and_retained_main_turn_ids(self):
        actual = collector.snapshot(self.db, ['session-a', 'session-b', 'empty'])
        self.assertEqual({key: actual['session-a'][key] for key in ('toolMs', 'toolSamples', 'toolCalls')},
                         {'toolMs': 2500, 'toolSamples': 2, 'toolCalls': 3})
        self.assertEqual(actual['session-b']['toolMs'], 7000)
        self.assertEqual(actual['session-b']['toolCalls'], 1)
        self.assertEqual(actual['empty']['toolMs'], 0)
        self.assertEqual(actual['empty']['toolCalls'], 0)

    def test_missing_tool_surface_does_not_break_model_or_token_statistics(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('DROP TABLE tool_usage')
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 120)
        self.assertEqual(actual['modelMs'], 2000)
        self.assertIsNone(actual['toolMs'])
        self.assertIsNone(actual['toolCalls'])
        self.assertEqual(actual['toolSamples'], 0)

    def test_missing_tool_timing_column_does_not_invent_tool_duration(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('ALTER TABLE tool_usage DROP COLUMN completed_at')
        actual = collector.snapshot(self.db, ['session-a'])['session-a']
        self.assertEqual(actual['tokens'], 120)
        self.assertIsNone(actual['toolMs'])

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
