"""Return numeric telemetry only. Never write to ZCode's database or select chat text."""
import json
import math
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def known(row, field, flag):
    """Storage historically coerces absent usage to zero; only explicit raw zero is known."""
    value = row[field]
    return number(value) and (value > 0 or bool(row[flag]))


def input_side(row):
    """Match ZCode's inputSideTokensFromStoredUsage, retaining missing-input coverage."""
    raw_input = row['input_tokens']
    read = row['cache_read_input_tokens']
    write = row['cache_creation_input_tokens']
    cached = (read if number(read) else 0) + (write if number(write) else 0)
    if not number(raw_input):
        return None
    if raw_input <= 0:
        # Older providers sometimes report cached input without an input total.
        if cached > 0:
            return cached
        return 0 if known(row, 'input_tokens', 'input_known') else None
    if cached <= 0:
        return raw_input
    total = row['provider_total_tokens']
    if total is None:
        total = row['computed_total_tokens']
    output = row['output_tokens']
    if number(total) and total > 0 and number(output):
        inclusive_distance = abs(total - (raw_input + output))
        exclusive_distance = abs(total - (raw_input + cached + output))
        if exclusive_distance < inclusive_distance:
            return raw_input + cached
    return raw_input


def summarize(rows):
    good = [r for r in rows if r['status'] == 'completed']
    paired, totals, cache = [], [], []
    model_times, ttft_times = [], []
    inputs, outputs, cache_reads, cache_writes, uncached, non_cache_reads = [], [], [], [], [], []
    breakdown_samples = 0
    for r in good:
        normalized_input = input_side(r)
        output_known = known(r, 'output_tokens', 'output_known')
        read_known = known(r, 'cache_read_input_tokens', 'cache_read_known')
        write_known = known(r, 'cache_creation_input_tokens', 'cache_write_known')
        read, write = r['cache_read_input_tokens'], r['cache_creation_input_tokens']
        if normalized_input is not None:
            inputs.append(normalized_input)
        if output_known:
            outputs.append(r['output_tokens'])
        # Each total keeps its own coverage. Missing cache write is not evidence of zero.
        if read_known and (normalized_input is None or read <= normalized_input):
            cache_reads.append(read)
        if write_known and (normalized_input is None or write <= normalized_input):
            cache_writes.append(write)
        if normalized_input is not None and read_known and write_known and read + write <= normalized_input:
            uncached.append(normalized_input - read - write)
            if output_known:
                breakdown_samples += 1
        if normalized_input is not None and output_known:
            totals.append(normalized_input + r['output_tokens'])
        if normalized_input is not None and read_known and read <= normalized_input:
            cache.append((normalized_input, read))
            non_cache_reads.append(normalized_input - read)
        start, first, end, out = (r[k] for k in ('started_at', 'first_token_at', 'completed_at', 'output_tokens'))
        if number(start) and number(end) and start <= end:
            model_times.append(end - start)
            if number(first) and start <= first <= end:
                ttft_times.append(first - start)
        if output_known and all(number(v) for v in (start, first, end, out)) and start <= first < end:
            paired.append((out, end - first))
    duration = sum(p[1] for p in paired)
    cache_input = sum(p[0] for p in cache)
    def total(values):
        return sum(values) if values else (0 if not good else None)
    return {
        'turns': len({r['turn_id'] for r in good if isinstance(r['turn_id'], str) and r['turn_id'].strip()}),
        'steps': len(good),
        'tokens': sum(totals) if totals else (0 if not good else None),
        'tokenSamples': len(totals),
        'tps': sum(p[0] for p in paired) * 1000 / duration if duration else None,
        'speedSamples': len(paired),
        'decodeMs': duration,
        'cacheHit': sum(p[1] for p in cache) / cache_input if cache_input else None,
        'cacheSamples': len(cache),
        'errors': sum(r['status'] == 'error' for r in rows),
        'modelMs': total(model_times),
        'modelSamples': len(model_times),
        # Summed latency; the UI divides by ttftSamples for the per-request average.
        'ttftMs': total(ttft_times),
        'ttftSamples': len(ttft_times),
        'inputTokens': total(inputs),
        'inputSamples': len(inputs),
        'outputTokens': total(outputs),
        'outputSamples': len(outputs),
        'cacheReadTokens': total(cache_reads),
        'cacheReadSamples': len(cache_reads),
        'cacheWriteTokens': total(cache_writes),
        'cacheWriteSamples': len(cache_writes),
        'uncachedInputTokens': total(uncached),
        'uncachedInputSamples': len(uncached),
        # Includes cache writes when present; does not assume unknown writes are zero.
        'nonCacheReadInputTokens': total(non_cache_reads),
        'nonCacheReadInputSamples': len(non_cache_reads),
        'breakdownSamples': breakdown_samples,
    }


def summarize_tools(rows):
    """Sum observed dispatch-to-terminal tool intervals, including parallel overlap.

    No model or turn elapsed time is used as a substitute for tool measurements.
    None means the database does not expose the required tool-usage surface.
    """
    if rows is None:
        return {'toolMs': None, 'toolSamples': 0, 'toolCalls': None}
    terminal = [r for r in rows if r['status'] in ('completed', 'error', 'cancelled')]
    timings = [r['completed_at'] - r['started_at'] for r in terminal
               if number(r['started_at']) and number(r['completed_at'])
               and r['started_at'] <= r['completed_at']]
    return {'toolMs': sum(timings) if timings else (0 if not terminal else None),
            'toolSamples': len(timings), 'toolCalls': len(terminal)}


def snapshot(db, sessions):
    result = {}
    # The connection context manager commits/rolls back but does not close the handle.
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        tool_columns = {r['name'] for r in con.execute('PRAGMA table_info(tool_usage)')}
        has_tools = {'session_id', 'turn_id', 'status', 'started_at', 'completed_at'} <= tool_columns
        for sid in dict.fromkeys(sessions[:8]):
            if not isinstance(sid, str) or not 1 <= len(sid) <= 160:
                continue
            if not con.execute('SELECT 1 FROM session WHERE id=?', (sid,)).fetchone():
                result[sid] = {'error': 'session-unavailable'}
                continue
            rows = con.execute('''SELECT turn_id,status,started_at,first_token_at,completed_at,
                input_tokens,output_tokens,cache_read_input_tokens,cache_creation_input_tokens,
                provider_total_tokens,computed_total_tokens,
                CASE WHEN json_valid(raw_usage_json) THEN
                    json_type(raw_usage_json,'$.inputTokens') IN ('integer','real')
                    AND json_extract(raw_usage_json,'$.inputTokens') >= 0 ELSE 0 END AS input_known,
                CASE WHEN json_valid(raw_usage_json) THEN
                    json_type(raw_usage_json,'$.outputTokens') IN ('integer','real')
                    AND json_extract(raw_usage_json,'$.outputTokens') >= 0 ELSE 0 END AS output_known,
                CASE WHEN json_valid(raw_usage_json) THEN
                    json_type(raw_usage_json,'$.cacheReadTokens') IN ('integer','real')
                    AND json_extract(raw_usage_json,'$.cacheReadTokens') >= 0 ELSE 0 END AS cache_read_known,
                CASE WHEN json_valid(raw_usage_json) THEN
                    json_type(raw_usage_json,'$.cacheWriteTokens') IN ('integer','real')
                    AND json_extract(raw_usage_json,'$.cacheWriteTokens') >= 0 ELSE 0 END AS cache_write_known
                FROM model_usage
                WHERE session_id=? AND query_source='main_turn' ORDER BY started_at''', (sid,)).fetchall()
            tools = None
            if has_tools:
                # tool_usage has no query_source; restrict to this session's retained
                # main-turn IDs rather than accidentally including another session.
                tools = con.execute('''SELECT status,started_at,completed_at FROM tool_usage AS t
                    WHERE t.session_id=? AND EXISTS (
                        SELECT 1 FROM model_usage AS m WHERE m.session_id=t.session_id
                        AND m.turn_id=t.turn_id AND m.query_source='main_turn')''', (sid,)).fetchall()
            result[sid] = {**summarize(rows), **summarize_tools(tools)}
    return result


if __name__ == '__main__':
    try:
        sessions = json.load(sys.stdin)
        if not isinstance(sessions, list):
            raise ValueError('Expected a session list')
        print(json.dumps({'sessions': snapshot(sys.argv[1], sessions)}, allow_nan=False))
    except (sqlite3.Error, OSError, ValueError, IndexError):
        print(json.dumps({'sessions': {}, 'error': 'data-unavailable'}))
        sys.exit(1)
