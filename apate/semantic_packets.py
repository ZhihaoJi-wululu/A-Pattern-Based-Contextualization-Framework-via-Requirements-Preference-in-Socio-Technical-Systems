"""Compact internal proofs without changing the original modeling inputs."""
from copy import deepcopy
import hashlib
import json
import re


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _pointer(part):
    return str(part).replace('~', '~0').replace('/', '~1')


def compact_semantic_bindings(bindings):
    """Keep proposals intact and reference repeated original evidence once.

    Every implementation, outcome state, predicate status and quality effect is
    retained. Complete certificates remain in artifacts and are independently
    recomputed at acceptance. This summary proves neither plan feasibility nor
    an original global quality; the original three input objects stay complete.
    """
    output = []
    for index, binding in enumerate(bindings):
        row = deepcopy({k: v for k, v in binding.items() if k != 'certified_witness_pair'})
        original = binding.get('semantic_contract')
        if not isinstance(original, dict):
            output.append(row)
            continue
        evidence, evidence_ids = [], {}
        qualities, quality_ids = [], {}

        def evidence_refs(items):
            refs = []
            for item in items:
                if 'node_id' in item and 'field' in item:
                    ref = {'model_path': '/nodes/' + _pointer(item['node_id']) + '/' + _pointer(item['field']),
                           'purpose': item.get('purpose')}
                elif (match := re.fullmatch(r'dependencies\[(\d+)\]\.dependum\.label', item.get('field', ''))):
                    ref = {'model_path': '/dependencies/' + match.group(1) + '/dependum/label',
                           'dependency_id': item.get('dependency_id'), 'purpose': item.get('purpose')}
                else:
                    ref = {'unrecognized_evidence_preserved': deepcopy(item)}
                key = _canonical(ref)
                if key not in evidence_ids:
                    evidence_ids[key] = len(evidence)
                    evidence.append(ref)
                refs.append(evidence_ids[key])
            return refs

        def predicates(items):
            return [{**deepcopy({k: v for k, v in item.items() if k != 'evidence'}),
                     'evidence_refs': evidence_refs(item.get('evidence', []))} for item in items]

        def quality_refs(items):
            refs = []
            for item in items:
                key = _canonical(item)
                if key not in quality_ids:
                    quality_ids[key] = len(qualities)
                    qualities.append(deepcopy(item))
                refs.append(quality_ids[key])
            return refs

        summary = deepcopy({k: v for k, v in original.items()
                            if k not in ('evidence', 'predicates', 'quality_certificates', 'implementations')})
        summary['predicates'] = predicates(original.get('predicates', []))
        summary['evidence_refs'] = evidence_refs(original.get('evidence', []))
        summary['quality_refs'] = quality_refs(original.get('quality_certificates', []))
        if 'implementations' in original:
            summary['implementations'] = []
            for implementation in original['implementations']:
                item = deepcopy({k: v for k, v in implementation.items()
                                 if k not in ('evidence', 'predicates', 'quality_certificates')})
                item['predicates'] = predicates(implementation.get('predicates', []))
                item['evidence_refs'] = evidence_refs(implementation.get('evidence', []))
                item['quality_refs'] = quality_refs(implementation.get('quality_certificates', []))
                summary['implementations'].append(item)
        summary.update(original_evidence=evidence, local_quality_certificates=qualities,
            full_certificate_sha256=hashlib.sha256(_canonical(original).encode('utf-8')).hexdigest(),
            full_artifact_path=f'/artifacts/canonical_pattern_bindings/{index}/semantic_contract',
            summary_boundary='Original semantic evidence only; independently review the complete original inputs. '
                'Python separately checks authority, persona counterevidence and full execution witnesses. '
                'Local quality effects do not assert original global satisfaction.')
        row['semantic_contract'] = summary
        output.append(row)
    return output
