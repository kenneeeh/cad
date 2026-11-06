"""Small JSONL history of measured TwoStage designs."""
import json
from pathlib import Path
from uuid import uuid4


def apply_changes(parameters, changes):
    if not changes:
        raise ValueError('changes must contain at least one absolute parameter value')
    unknown = set(changes) - set(parameters)
    if unknown:
        raise ValueError(f'Unknown changed parameters: {sorted(unknown)}')
    candidate = {**parameters, **changes}
    actual = {name: {'from': parameters[name], 'to': value} for name, value in changes.items()
              if value != parameters[name]}
    if not actual:
        raise ValueError('changes do not change the base design')
    return candidate, actual


class CandidateArchive:
    def __init__(self, path, problem_id):
        self.path = Path(path)
        self.problem_id = problem_id

    def records(self, include_incompatible=False):
        if not self.path.exists():
            return []
        with self.path.open(encoding='utf-8') as source:
            records = [json.loads(line) for line in source if line.strip()]
        return records if include_incompatible else [r for r in records if r['problem_id'] == self.problem_id]

    def get(self, design_id):
        for record in self.records():
            if record['design_id'] == design_id:
                return record  # JSON loading already gives the caller a fresh dictionary.
        raise ValueError('Unknown design ID in the current setup')

    def add(self, parameters, assessment, source, run_id, metadata, parent_id=None, hypothesis='', design_id=None):
        # Callers validate measured data before storing it. Imports retain their original ID.
        record = {'design_id': design_id or 'design_' + uuid4().hex, 'problem_id': self.problem_id,
                  'source': source, 'run_id': str(run_id), 'parameters': dict(parameters),
                  **assessment, 'metadata': metadata, 'parent_id': parent_id, 'hypothesis': hypothesis}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, allow_nan=False) + '\n')
        return record

    def best(self, k=5):
        distinct, result = set(), []
        for record in sorted(self.records(), key=lambda r: (-r['reward'], r['design_id'])):
            key = tuple(sorted(record['parameters'].items()))
            if key not in distinct:
                distinct.add(key)
                result.append(record)
                if len(result) == k:
                    break
        return result


def compact(record, include_parameters=False):
    if include_parameters:
        return record
    result = {name: record[name] for name in ('design_id', 'source', 'run_id', 'reward', 'hard_satisfied',
                                             'violated_constraints', 'specs', 'parent_id')}
    result['fixture'] = bool(record['metadata'].get('fixture', False))
    if 'phase' in record['metadata']:
        result['phase'] = record['metadata']['phase']
    return result
