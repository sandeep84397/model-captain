"""Independent, offline executable oracles for the harder text tasks.

Only trusted Python below executes. Suite/model text is never evaluated.
"""
from collections import OrderedDict, Counter
from heapq import heappush, heappop
from importlib.resources import files
from itertools import combinations
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from model_guide.evaluation import validate_suite, grade, suite_hash


def cache_trace(strict):
    cache = OrderedDict()
    def purge(now):
        for key, (_, end) in list(cache.items()):
            if end <= now if strict else end < now:
                del cache[key]
    def put(now, key, value, ttl):
        purge(now)
        cache.pop(key, None)
        cache[key] = (value, now + ttl)
        while len(cache) > 2:
            cache.popitem(last=False)
    def get(now, key):
        purge(now)
        if key not in cache:
            return None
        cache.move_to_end(key)
        return cache[key][0]
    put(0, 'A', 'a', 3)
    put(1, 'B', 'b', 5)
    out = [get(3, 'A')]
    put(3, 'C', 'c', 2)
    out += [get(4, 'B'), get(5, 'C')]
    put(6, 'D', 'd', 4)
    out += [get(6, 'B')]
    return {'reads': out, 'keys_lru_to_mru': list(cache)}


def transactions():
    values = {'x': 10, 'y': 20, 'z': 30}
    versions = dict.fromkeys(values, 0)
    snapshots = {t: versions.copy() for t in ('T1', 'T2', 'T3')}
    writes = {'T1': {'x': 11, 'y': 19}, 'T2': {'y': 25, 'z': 25}, 'T3': {'x': 12, 'z': 28}}
    committed, aborted = [], []
    def commit(t):
        if any(versions[k] != snapshots[t][k] for k in writes[t]):
            aborted.append(t)
        else:
            for k, value in writes[t].items():
                values[k] = value
                versions[k] += 1
            committed.append(t)
    for t in ('T2', 'T1', 'T3'):
        commit(t)
    snapshots['T1-retry'] = versions.copy()
    writes['T1-retry'] = {'x': values['x'] + 1, 'y': values['y'] - 1}
    commit('T1-retry')
    return {'committed': committed, 'aborted': aborted, 'values': values, 'versions': versions}


def delivery(atomic):
    balance, seen = 10, set()
    for ident, op, number, crash in [('a','add',5,False),('b','mul',2,True),('b','mul',2,False),('c','add',-4,False),('a','add',5,False),('d','mul',3,False)]:
        if ident in seen:
            continue
        balance = balance + number if op == 'add' else balance * number
        if atomic or not crash:
            seen.add(ident)
    return {'balance': balance, 'seen': sorted(seen)}


GRAPH = {'A': [('B',9),('C',2)], 'B': [('D',2),('F',9)],
         'C': [('B',1),('D',8),('E',3)], 'D': [('F',2)],
         'E': [('D',1),('F',9)], 'F': []}

def paths():
    heap, visited = [(0,'A')], {'A'}
    actual = None
    while heap:
        cost, node = heappop(heap)
        if node == 'F':
            actual = cost
            break
        for target, weight in GRAPH[node]:
            if target not in visited:
                visited.add(target)
                heappush(heap, (cost + weight, target))
    options = []
    def walk(node, cost, path):
        if node == 'F':
            options.append((cost, path))
        for nxt, weight in GRAPH[node]:
            if nxt not in path:
                walk(nxt, cost + weight, path + [nxt])
    walk('A', 0, ['A'])
    best = min(options)
    return {'actual_cost': actual, 'optimal_cost': best[0], 'optimal_path': best[1]}


def mutation_answer(cases, reference, mutants):
    killed = {name: sorted(m for m, fn in mutants.items() if fn(*args) != reference(*args))
              for name, args in cases.items()}
    selected = None
    for size in range(len(cases) + 1):
        covers = [list(group) for group in combinations(sorted(cases), size)
                  if set().union(*(set(killed[c]) for c in group)) == set(mutants)]
        if covers:
            selected = min(covers)
            break
    if selected is None:
        raise AssertionError('candidate tests cannot kill all mutants')
    return {'killed': killed, 'minimum_tests': selected}


def overlap():
    cases = {'A':(0,2,2,4),'B':(0,4,1,3),'C':(0,3,2,5),'D':(3,0,1,2),'E':(0,2,0,2),'F':(1,1,0,2)}
    def ref(a,b,c,d): return a < b and c < d and max(a,c) < min(b,d)
    return mutation_answer(cases, ref, {
        'M1':lambda a,b,c,d: a < b and c < d and max(a,c) <= min(b,d),
        'M2':lambda a,b,c,d: max(min(a,b),min(c,d)) < min(max(a,b),max(c,d)),
        'M3':lambda a,b,c,d: a < b and c < d and ((a <= c and d <= b) or (c <= a and b <= d)),
        'M4':lambda a,b,c,d: ref(a,b,c,d) and (a,b) != (c,d),
    })


def backoff():
    cases = {'A':(1,0,8),'B':(1,1,8),'C':(1,2,8),'D':(3,2,8),'E':(9,0,8),'F':(2,3,8)}
    return mutation_answer(cases, lambda b,n,c:min(c,b*2**n), {
        'M1':lambda b,n,c:min(c,b*2**(n+1)),
        'M2':lambda b,n,c:min(c,b*(n+1)),
        'M3':lambda b,n,c:min(c,b)*2**n,
        'M4':lambda b,n,c:c,
    })


ROWS = [(1,'b'),(2,'a'),(1,'a'),(3,'a'),(2,'c')]

def pagination():
    cases = {'A':(None,2),'B':((1,'a'),2),'C':((1,'b'),2),'D':((2,'a'),1),'E':((3,'a'),2)}
    def ref(cursor, limit): return [r for r in sorted(ROWS) if cursor is None or r > cursor][:limit]
    return mutation_answer(cases, ref, {
        'M1':lambda c,n:[r for r in sorted(ROWS) if c is None or r[0]>c[0]][:n],
        'M2':lambda c,n:[r for r in sorted(ROWS) if c is None or r>=c][:n],
        'M3':lambda c,n:[r for r in sorted(ROWS)[:n] if c is None or r>c],
        'M4':lambda c,n:[r for r in sorted(ROWS,key=lambda r:(r[1],r[0])) if c is None or r>c][:n],
    })


def dedup():
    cases = {'A':([2,1,2],),'B':([1,1,2],),'C':([3,2,1],),'D':([2,1,1,2],),'E':([],),'F':([1,2,1,3,2],)}
    def ref(xs): return list(dict.fromkeys(xs))
    return mutation_answer(cases, ref, {
        'M1':lambda xs:sorted(set(xs)),
        'M2':lambda xs:list(reversed(list(dict.fromkeys(reversed(xs))))),
        'M3':lambda xs:[x for x in xs if Counter(xs)[x]==1],
        'M4':lambda xs:[x for i,x in enumerate(xs) if i==0 or x!=xs[i-1]],
    })


def answers():
    return {'hard-debug-1': {'buggy':cache_trace(False),'fixed':cache_trace(True)},
            'hard-debug-2': transactions(),
            'hard-debug-3': {'buggy':delivery(False),'atomic':delivery(True)},
            'hard-debug-4': paths(),
            'hard-test-1':overlap(), 'hard-test-2':backoff(),
            'hard-test-3':pagination(), 'hard-test-4':dedup()}


class HardSuiteTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads(files('model_guide.data').joinpath('programming-hard.json').read_text())

    def test_suite_contract_balance_and_strict_grading(self):
        validate_suite(self.suite)
        self.assertEqual(Counter(t['category'] for t in self.suite['tasks']),
                         {'debugging':4,'code-review':4,'testing':4})
        self.assertEqual(len(suite_hash(self.suite)), 64)
        for task in self.suite['tasks']:
            with self.subTest(task=task['id']):
                self.assertEqual(task['grader'], 'exact')
                self.assertTrue(grade(json.dumps(task['expected']), 'exact', task['expected']))
                self.assertFalse(grade('{}', 'exact', task['expected']))
                self.assertFalse(grade(json.dumps({**task['expected'],'extra':1}), 'exact', task['expected']))

    def test_answer_keys_match_executable_oracles(self):
        tasks = {t['id']:t for t in self.suite['tasks']}
        for ident, expected in answers().items():
            with self.subTest(task=ident):
                self.assertEqual(tasks[ident]['expected'], expected)

    def test_task_order_and_content_are_not_old_suite(self):
        old = json.loads(files('model_guide.data').joinpath('programming.json').read_text())
        self.assertFalse({t['id'] for t in old['tasks']} & {t['id'] for t in self.suite['tasks']})
        self.assertNotEqual(suite_hash(old), suite_hash(self.suite))

    def test_native_pipeline_sends_only_prompts_and_records_hard_suite_hash(self):
        from model_guide.cli import main
        from model_guide.native import NativeResult, NATIVE_PROFILE
        tasks = {t['prompt']: t for t in self.suite['tasks']}
        candidate = {'id':'candidate','provider':'codex-cli','model':'example','effort':'medium'}
        with tempfile.TemporaryDirectory() as tmp:
            config, suite, report = (Path(tmp, name) for name in ('config.json','suite.json','report.json'))
            config.write_text(json.dumps({'version':1,'candidates':[candidate]}))
            suite.write_text(json.dumps(self.suite))
            with patch('model_guide.native_evaluation.NativeClient') as factory:
                client = factory.return_value
                client.preflight.return_value = {'cli_version':'test-1','auth_method':'chatgpt','profile':NATIVE_PROFILE}
                def respond(received_candidate, prompt):
                    self.assertEqual(received_candidate['model'], 'example')
                    self.assertIn(prompt, tasks)  # Not a serialized task or answer-key object.
                    return NativeResult(json.dumps(tasks[prompt]['expected']), None, 1, 1)
                client.evaluate.side_effect = respond
                self.assertEqual(main(['evaluate-native','--provider','codex-cli','--config',str(config),
                    '--suite',str(suite),'--output',str(report),'--live','--max-requests','12']), 0)
                self.assertEqual(client.evaluate.call_count, 12)
            result = json.loads(report.read_text())
            self.assertEqual(result['suite_hash'], suite_hash(self.suite))
            self.assertEqual(len(result['attempts']), 12)
            self.assertTrue(all(a['passed'] for a in result['attempts']))
            self.assertTrue(all(a['returned_model'] is None for a in result['attempts']))
