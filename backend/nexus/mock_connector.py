"""Synthetic business system in a separate database. No public execution endpoint.
Only the worker imports invoke(). No real financial side effects are implemented.
"""
import json
import sqlite3
from pathlib import Path


class UncertainOutcome(Exception): pass


class MockBusiness:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS results (intent TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, intent TEXT NOT NULL)')

    def connect(self): return sqlite3.connect(self.path, timeout=30)

    def invoke(self, intent, envelope, simulation='normal'):
        if simulation == 'fail_before_commit': raise ValueError('Synthetic connector rejected request before commit')
        with self.connect() as db:
            existing = db.execute('SELECT payload FROM results WHERE intent=?', (intent,)).fetchone()
            if existing: return json.loads(existing[0])
            args = envelope['arguments']
            result = dict(args)
            result.update({'external_ref': ('PR-' if envelope['action'] == 'purchase:create' else 'SUP-') + intent[:8].upper(),
                           'state': 'created' if envelope['action'] == 'purchase:create' else 'found'})
            if simulation == 'mismatch': result['supplier_id'] = 'SUP-DEMO-999'
            db.execute('INSERT INTO results(intent,payload) VALUES (?,?)', (intent, json.dumps(result)))
            db.execute('INSERT INTO calls(intent) VALUES (?)', (intent,))
        if simulation == 'timeout_after_commit': raise UncertainOutcome('Synthetic timeout after commit')
        return result

    def lookup(self, intent, envelope=None):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM results WHERE intent=?', (intent,)).fetchone()
        return json.loads(row[0]) if row else None

    def count(self):
        with self.connect() as db: return db.execute('SELECT count(*) FROM calls').fetchone()[0]
