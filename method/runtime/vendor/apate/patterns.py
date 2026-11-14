"""Facet patterns and independently checked conditional rule contracts.

The contracts expose facts to bind and check; they do not infer a fact from a
facet label, task label, generated choice, or an unavailable source passage.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGED_CATALOGUE = Path(__file__).resolve().parents[1] / 'data' / 'pattern_catalogue_v4.json'
CATALOGUE = PACKAGED_CATALOGUE if PACKAGED_CATALOGUE.exists() else ROOT / 'output' / 'APATE_Facet_Redesign_20261027' / 'pattern_catalogue_v4.json'


def _unique_object(pairs):
    """Reject duplicate JSON keys before a repeated facet ID can be lost."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Pattern catalogue contains duplicate JSON key: {key!r}.')
        result[key] = value
    return result


def _identifier_list(value, location, *, nonempty=False):
    if not isinstance(value, list) or nonempty and not value:
        raise ValueError(f'Pattern catalogue {location} must be a list' + (' with at least one ID.' if nonempty else '.'))
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise ValueError(f'Pattern catalogue {location} contains an invalid ID.')
    if len(set(value)) != len(value):
        raise ValueError(f'Pattern catalogue {location} contains duplicate IDs.')
    return value


def _catalogue_overview(catalogue):
    """Audit facet patterns, conditional branches and reusable source rules."""
    if not isinstance(catalogue, dict):
        raise ValueError('Pattern catalogue must be an object.')
    facets, patterns = catalogue.get('facets'), catalogue.get('patterns')
    if not isinstance(facets, dict) or not facets:
        raise ValueError('Pattern catalogue facets must be a nonempty object keyed by facet ID.')
    if not isinstance(patterns, list):
        raise ValueError('Pattern catalogue patterns must be a list.')

    facet_rows, declared_links = [], set()
    for fid, facet in facets.items():
        if not isinstance(fid, str) or not fid.strip() or not isinstance(facet, dict):
            raise ValueError(f'Pattern catalogue contains an invalid facet: {fid!r}.')
        for field in ('label_zh', 'domain'):
            if not isinstance(facet.get(field), str) or not facet[field].strip():
                raise ValueError(f'Pattern catalogue facet {fid!r} requires {field}.')
        ids = _identifier_list(facet.get('patterns'), f'facet {fid!r} patterns')
        facet_rows.append({'id': fid, 'label_zh': facet['label_zh'], 'domain': facet['domain'],
                           'pattern_ids': list(ids)})
        declared_links.update((fid, pid) for pid in ids)

    cards, actual_links, shared = {}, set(), []
    for card in patterns:
        if not isinstance(card, dict) or not isinstance(card.get('id'), str) or not card['id'].strip():
            raise ValueError('Pattern catalogue contains an invalid pattern ID.')
        pid = card['id']
        if pid in cards:
            raise ValueError(f'Pattern catalogue contains duplicate pattern ID: {pid!r}.')
        if not isinstance(card.get('name'), str) or not card['name'].strip():
            raise ValueError(f'Pattern catalogue pattern {pid!r} requires name.')
        ids = _identifier_list(card.get('facets'), f'pattern {pid!r} facets', nonempty=True)
        for fid in ids:
            if fid not in facets:
                raise ValueError(f'Pattern catalogue pattern {pid!r} references unknown facet: {fid!r}.')
        cards[pid] = card
        actual_links.update((fid, pid) for fid in ids)
        if len(ids) > 1:
            shared.append({'id': pid, 'name': card['name'], 'facets': list(ids)})

    for fid, pid in declared_links:
        if pid not in cards:
            raise ValueError(f'Pattern catalogue facet {fid!r} references unknown pattern: {pid!r}.')
    if declared_links != actual_links:
        missing_on_facets = sorted(actual_links - declared_links)
        missing_on_patterns = sorted(declared_links - actual_links)
        raise ValueError('Pattern catalogue bidirectional mapping mismatch: '
                         f'missing facet-to-pattern links={missing_on_facets}; '
                         f'missing pattern-to-facet links={missing_on_patterns}.')

    rules = catalogue.get('rules')
    rule_map, branch_links, shared_rules = {}, set(), []
    if rules is not None:
        if not isinstance(rules, list):
            raise ValueError('Pattern catalogue rules must be a list.')
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get('id'), str) or not rule['id'].strip():
                raise ValueError('Pattern catalogue contains an invalid rule ID.')
            rid = rule['id']
            if rid in rule_map:
                raise ValueError(f'Pattern catalogue contains duplicate rule ID: {rid!r}.')
            if not isinstance(rule.get('name'), str) or not rule['name'].strip():
                raise ValueError(f'Pattern catalogue rule {rid!r} requires name.')
            if not isinstance(rule.get('CPS'), dict) or not isinstance(rule['CPS'].get('Solution'), dict):
                raise ValueError(f'Pattern catalogue rule {rid!r} requires a CPS Solution object.')
            if rule.get('rule_id') != rid:
                raise ValueError(f'Pattern catalogue rule_id does not match rule ID {rid!r}.')
            rf = _identifier_list(rule.get('facets'), f'rule {rid!r} facets', nonempty=True)
            if any(fid not in facets for fid in rf):
                raise ValueError(f'Pattern catalogue rule {rid!r} references an unknown facet.')
            rule_map[rid] = rule
        for pid, card in cards.items():
            if len(card['facets']) != 1:
                raise ValueError(f'Pattern catalogue pattern {pid!r} must represent exactly one facet.')
            fid = card['facets'][0]
            ids = _identifier_list(card.get('rule_ids'), f'pattern {pid!r} rule_ids', nonempty=True)
            if not isinstance(card.get('CPS'), dict) or not isinstance(card['CPS'].get('Solution'), dict):
                raise ValueError(f'Pattern catalogue pattern {pid!r} requires a CPS Solution object.')
            branches = card['CPS']['Solution'].get('branches')
            if not isinstance(branches, list) or [b.get('rule_id') for b in branches if isinstance(b, dict)] != ids:
                raise ValueError(f'Pattern catalogue pattern {pid!r} branches must match rule_ids in order.')
            for branch in branches:
                rid = branch['rule_id']
                if rid not in rule_map:
                    raise ValueError(f'Pattern catalogue pattern {pid!r} references unknown rule: {rid!r}.')
                rule = rule_map[rid]
                if branch.get('facet') != fid or fid not in rule['facets']:
                    raise ValueError(f'Pattern catalogue branch {pid!r}/{rid!r} has an invalid facet scope.')
                for field in ('Context', 'Problem'):
                    if branch.get(field) != rule.get('CPS', {}).get(field):
                        raise ValueError(f'Pattern catalogue branch {pid!r}/{rid!r} does not preserve rule {field}.')
                for field in ('IF', 'THEN', 'OTHERWISE'):
                    if field not in branch or branch[field] != rule.get('CPS', {}).get('Solution', {}).get(field):
                        raise ValueError(f'Pattern catalogue branch {pid!r}/{rid!r} does not preserve rule {field}.')
                branch_links.add((pid, rid))
        for row in facet_rows:
            if len(row['pattern_ids']) != 1:
                raise ValueError(f'Pattern catalogue facet {row["id"]!r} must have exactly one pattern.')
            expected = cards[row['pattern_ids'][0]]['rule_ids']
            declared = _identifier_list(facets[row['id']].get('rule_ids'), f'facet {row["id"]!r} rule_ids', nonempty=True)
            if declared != expected:
                raise ValueError(f'Pattern catalogue facet {row["id"]!r} rule mapping mismatch.')
            row['rule_ids'] = list(expected)
        for rid, rule in rule_map.items():
            parents = [pid for pid in cards if (pid, rid) in branch_links]
            if not parents:
                raise ValueError(f'Pattern catalogue rule {rid!r} has no parent pattern.')
            declared = _identifier_list(rule.get('pattern_ids'), f'rule {rid!r} pattern_ids', nonempty=True)
            if set(declared) != set(parents):
                raise ValueError(f'Pattern catalogue rule {rid!r} parent mapping mismatch.')
            if set(rule['facets']) != {cards[pid]['facets'][0] for pid in parents}:
                raise ValueError(f'Pattern catalogue rule {rid!r} facet mapping mismatch.')
            if len(parents) > 1:
                shared_rules.append({'id': rid, 'rule_id': rid, 'name': rule['name'],
                                     'pattern_ids': parents, 'facets': list(rule['facets'])})

    counts = {'facet_count': len(facets), 'pattern_count': len(cards), 'association_count': len(actual_links),
              'rule_count': len(rule_map), 'branch_count': len(branch_links)}
    metadata = {'facet_count': counts['facet_count'], 'unique_patterns': counts['pattern_count'],
                'facet_pattern_links': counts['association_count'], 'pattern_count': counts['pattern_count'],
                'association_count': counts['association_count']}
    if rules is not None:
        metadata.update(unique_rules=counts['rule_count'], pattern_rule_links=counts['branch_count'])
    if 'primary_sources' in catalogue:
        sources = catalogue.get('sources')
        if not isinstance(sources, (dict, list)):
            raise ValueError('Pattern catalogue primary_sources requires a sources collection.')
        metadata['primary_sources'] = len(sources)
    for field, expected in metadata.items():
        if field in catalogue and (type(catalogue[field]) is not int or catalogue[field] != expected):
            raise ValueError(f'Pattern catalogue metadata {field}={catalogue[field]!r} '
                             f'does not match computed count {expected}.')

    return {**counts, 'facets': facet_rows, 'shared_patterns': shared, 'shared_rules': shared_rules,
            'multi_rule_patterns': [{'id': p['id'], 'name': p['name'], 'facets': list(p['facets']),
                                     'rule_ids': list(p['rule_ids'])} for p in patterns if len(p.get('rule_ids', [])) > 1],
            'multi_pattern_facets': [{'id': row['id'], 'label_zh': row['label_zh'],
                                      'pattern_ids': list(row['pattern_ids'])}
                                     for row in facet_rows if len(row['pattern_ids']) > 1]}


@lru_cache(maxsize=1)
def _catalogue():
    result = json.loads(CATALOGUE.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    _catalogue_overview(result)
    return result


def load_catalogue():
    return deepcopy(_catalogue())


def catalogue_overview(catalogue=None):
    """Return independently audited pattern, rule and branch inventory counts."""
    return _catalogue_overview(_catalogue() if catalogue is None else catalogue)


def rule_contracts():
    """Return each source rule's explicit, evidence-bound minimum fact contract.

    Required predicates are positive propositions: false means inapplicable;
    null/missing evidence means unknown. No default is supplied by this module.
    Effects and feasibility are evaluated independently by contextualize.py.
    """
    definitions = {
        'AP-SOC-R1': (['choice'], {
            'reciprocal_opportunity': '本人确有提问和回应机会。',
            'approved_equivalent_channels': '双向与独立渠道均获准且同等足够。',
            'no_uninterruptible_high_duty': '不存在不可中断的高职责事项。',
            'resources_available': '双方时段、当前精力及工作资源允许交流。'}),
        'AP-ASSERT-R1': (['choice'], {
            'negotiable_request': '对方提出真正可协商的安排。',
            'own_nonmandatory_preference': '本人先前明确的非mandatory偏好与安排有分歧。',
            'both_responses_authorized': '表达替代与接受安排均合法、可行。',
            'self_expression_difference': '一方案表达本人立场，另一方案明确不表达。'}),
        'AP-ENERGY-R1': (['choice'], {
            'active_and_static_modes_available': '已有现场身体活动与静态办理两种实现。',
            'current_energy_and_physical_capacity': '本人当下精力与身体能力允许活动。',
            'same_business_and_safety_standard': '两种方式满足相同必要业务和安全标准。',
            'activity_not_mandatory_or_speed_forced': '活动方式不是mandatory或硬速度要求指定。',
            'resources_available': '场地、时段与其他资源允许活动。'}),
        'AP-COMPASSION-R1': (['choice', 'optional_participation'], {
            'specific_difficulty_known': '本人感知到独立核实的具体对象困难。',
            'relief_effect_known': '帮助的具体减轻效果独立登记。',
            'minimum_service_guaranteed': '两种完整方案均保证必要服务。',
            'voluntary_extra_relief': '额外实质协助有裁量、可合法省略。',
            'voluntary_cost_affordable': '自愿成本在本人当前可支配资源内。'}),
        'AP-RESPECT-R1': (['choice'], {
            'voluntary_shared_resource': '双方涉及可自由安排的额外资源。',
            'allocation_norm_known_and_accepted': '当前具体分配规范已明确并获本人理解认可。',
            'norm_not_mandatory_entitlement': '所比较规范不是mandatory权利保障。',
            'both_allocations_legal': '顾及份额与自留都合法且不侵害真实权利。',
            'other_share_difference_known': '完整分配结果对同一软规范的差异明确。'}),
        'AP-TRUST-R1': (['choice'], {
            'unfamiliar_partner': '当前合作对象对本人不熟悉。',
            'identity_and_permission_verified': '身份、权限与渠道已经独立核验。',
            'bounded_reversible_nonsensitive_cooperation': '互惠限于非敏感信息且范围小、可撤回。',
            'negative_cues_checked_and_absent': '已检查负线索且无未解释反证；不是尚未检查。',
            'independent_alternative_valid': '同一业务也能合法独立完成。',
            'cooperation_optional': '采用该合作机会不属mandatory。'}),
        'AP-RD-ORG-01': (['choice'], {
            'visible_disorder': '本人当前可感知相关材料散乱。',
            'actor_directory_standard': '本人认可当前具体目录或分类软标准。',
            'minimum_retention_satisfied': '两种归存方式均满足最低完整保存要求。',
            'organization_difference_known': '完整结果的组织标准差异独立登记。'}),
        'AP-RD-PRO-01': (['temporal'], {
            'current_work_started': '当前工作单元已经开展，完成检查点可定位。',
            'current_work_meaningful_solvable': '剩余工作仍有意义且当前能力资源允许完成。',
            'diversion_deferrable': '另一活动可合法延后且后续仍能执行。',
            'no_hard_interruption': '不存在必须立即中断的硬要求。',
            'both_activities_selected': '比较的是两活动共同参与的合法顺序。'}),
        'AP-RD-RES-01': (['optional_participation'], {
            'prior_voluntary_actor_promise': '本人事先自愿向明确对象作出具体承诺。',
            'promise_active_same_episode': '承诺仍有效且对应同一对象与episode。',
            'promised_activity_optional': '活动仍为合法optional，省略不使业务不可行。',
            'promise_resources_and_deadline_feasible': '当前资源及独立承诺期限允许履行。'}),
        'AP-RD-ANX-01': (['optional_participation'], {
            'large_environmental_change': '本人已感知事项相关的明显环境变化。',
            'specific_current_unknown_status': '当前确有具体尚未知的状态。',
            'noninstrumental_information': '信息不能改变该结果。',
            'status_information_available': '当前有新状态信息及等待同样反馈的实现。',
            'information_cost_feasible': '信息成本、渠道与必要业务均允许。'}),
        'AP-RD-PREVIEW-01': (['choice'], {
            'outcome_fixed_uncontrollable': '结果在固定后续时点揭晓且行为不能改变。',
            'uncertainty_unresolved': '本人目前尚未知晓结果。',
            'accurate_early_information_available': '提前量与准确信息均有依据。',
            'known_nonzero_small_cost_affordable': '明确的非零小成本在允许资源内。',
            'same_final_result_and_feedback': '两方案最终结果与反馈相同。'}),
        'AP-RD-DEP-01': (['choice'], {
            'independent_current_low_reward_wanting': '当前低预期回报动机独立取证。',
            'adequate_standard_handling_available': '标准处理已足够完成必要业务。',
            'extra_effort_for_uncertain_increment': '额外主动投入对应明确但不确定的增量奖励。',
            'both_plans_within_capacity': '两方案均在能力资源范围内，差异不是身体限制。',
            'extra_effort_not_necessary_verification': '额外投入不是必要验证或硬职责。'}),
        'AP-RD-VOL-01': (['choice'], {
            'attributable_current_provocation': '本人把具体挑衅或不公批评归责于对方。',
            'independent_current_anger': '当前愤怒有独立材料。',
            'blame_and_neutral_responses_legal': '责备与中性回应均不违mandatory沟通规范。',
            'same_verification_processing_records': '两路保留相同必要核验、处理及归档。',
            'reactive_blame_difference_known': '两路对该对象的反应性责备差异明确。'}),
        'AP-IC-REDESIGN-01': (['optional_participation'], {
            'specific_question_before_choice': '选择前已有具体知识问题。',
            'independent_current_learning_interest': '当前学习兴趣不是从所选活动反推。',
            'minimum_execution_knowledge_sufficient': '最低执行知识已经足够。',
            'authorized_relevant_new_explanation': '获准来源能提供相关新解释。',
            'resources_available': '可选解释参与的时间与工作资源允许。'}),
        'AP-IC-REDESIGN-02': (['optional_participation'], {
            'new_explorable_material': '本人接触可探索的新事实或概念。',
            'basic_business_already_handleable': '基本业务已可处理。',
            'autonomous_questioning_allowed': 'Role允许自主提出并记录扩展问题。',
            'new_unanswered_question_effect': '形成与材料相关而尚未回答的新问题。',
            'resources_available': '当前时间资源允许额外提问。'}),
        'AP-AS-REDESIGN-01': (['optional_participation', 'choice'], {
            'genuine_aesthetic_material': '对象确为艺术、音乐、文学或明确审美材料。',
            'independent_current_aesthetic_interest': '选择前独立记录本人审美兴趣。',
            'additional_aesthetic_exposure': '存在真实额外审美接触效果差异。',
            'presentation_access_and_resources_available': '作品呈现、可访问性与资源允许。',
            'aesthetics_not_business_authenticity': '不从外观推断身份、真实性或业务可靠性。'}),
        'AP-CI-REDESIGN-01': (['optional_participation', 'choice'], {
            'open_problem_multiple_acceptable_answers': '当前问题开放且有多种合格可能。',
            'extra_generation_optional': '额外构想不属最低业务要求。',
            'baseline_candidate_already_validated': '合格基线与必要验证已经存在。',
            'independent_review_in_model': 'M0已有生成后的独立评审环节。',
            'exploration_not_unverified_implementation': '额外探索不自动等于采纳或实施。',
            'resources_available': '当前确有额外创造裁量和资源。'})}
    cards = {p['id']: p for p in _catalogue()['rules']}
    if set(definitions) != set(cards):
        raise ValueError('Every current conditional rule needs a machine contract.')
    output = {}
    for key, (kinds, predicates) in definitions.items():
        card = cards[key]
        output[key] = {
            'rule_id': key, 'pattern_ids': deepcopy(card['pattern_ids']),
            'name': card['name'], 'facets': deepcopy(card['facets']),
            'facet_match': 'any_with_separate_support', 'allowed_kinds': kinds,
            'required_predicates': list(predicates), 'predicate_descriptions': predicates,
            'requires_optional': kinds == ['optional_participation'],
            'requires_current_work': key == 'AP-RD-PRO-01',
            'requires_review_node': key == 'AP-CI-REDESIGN-01',
            'allowed_formulas': ['precedes'] if key == 'AP-RD-PRO-01' else ['sometime'],
            'pattern_version': _catalogue()['version'], 'sources': deepcopy(card['sources']),
            'inference_boundary': card['inference_boundary'], 'status': card['status'],
            'CPS': deepcopy(card['CPS'])}
    return output


def machine_contracts():
    """Return one parent contract per facet, with independent branch contracts.

    Predicates are never unioned across branches: selecting one rule does not
    require the facts of its sibling rules or another facet's shared branch.
    """
    rules = rule_contracts()
    output = {}
    for card in _catalogue()['patterns']:
        branches = []
        for rid in card['rule_ids']:
            branch = deepcopy(rules[rid])
            branch.update(pattern_id=card['id'], facet=card['facets'][0], facets=list(card['facets']))
            branches.append(branch)
        output[card['id']] = {'pattern_id': card['id'], 'name': card['name'],
            'facets': deepcopy(card['facets']), 'rule_ids': list(card['rule_ids']),
            'branches': branches, 'branch_match': 'independent_conditions',
            'CPS': deepcopy(card['CPS']), 'sources': deepcopy(card['sources']),
            'pattern_version': _catalogue()['version'], 'inference_boundary': card['inference_boundary']}
    return output


class CandidateBindingError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def resolve_candidate_binding(candidate, *, parents=None, rules=None):
    """Resolve a parent pattern and one rule, including stable legacy IDs.

    A legacy rule shared by multiple parents requires an explicit facet.
    Existing parent IDs that are also old rule IDs retain that old rule's
    meaning when rule_id is omitted; no sibling is chosen from its facts.
    """
    if parents is None:
        parents = {card['id']: card for card in _catalogue()['patterns']}
    if rules is None:
        rules = rule_contracts()
    pid, rid, facet = candidate.get('pattern_id'), candidate.get('rule_id'), candidate.get('facet')
    if not isinstance(pid, str) or not pid:
        raise CandidateBindingError('unknown_pattern', 'A valid pattern_id is required.')
    if rid is not None and (not isinstance(rid, str) or not rid):
        raise CandidateBindingError('unknown_rule', 'A valid rule_id is required.')
    if pid in parents:
        parent = parents[pid]
        if rid is None:
            if pid in parent['rule_ids']:
                rid = pid
            elif len(parent['rule_ids']) == 1:
                rid = parent['rule_ids'][0]
            else:
                raise CandidateBindingError('rule_required', 'Select an explicit rule_id for this pattern branch.')
    elif pid in rules:
        if rid is not None and rid != pid:
            raise CandidateBindingError('rule_not_in_pattern', 'Legacy rule alias and rule_id disagree.')
        rid = pid
        possible = [p for p in parents.values() if rid in p['rule_ids'] and (facet is None or facet in p['facets'])]
        if len(possible) != 1:
            raise CandidateBindingError('ambiguous_rule_parent', 'A shared legacy rule requires an explicit facet to select its parent pattern.')
        parent = possible[0]
        pid = parent.get('pattern_id', parent.get('id'))
    else:
        raise CandidateBindingError('unknown_pattern', 'Pattern ID is not in the current facet-pattern catalogue.')
    if rid not in rules:
        raise CandidateBindingError('unknown_rule', 'Rule ID is not in the current conditional-rule catalogue.')
    if rid not in parent['rule_ids']:
        raise CandidateBindingError('rule_not_in_pattern', 'The selected rule is not a branch of this pattern.')
    if facet is not None and facet not in parent['facets']:
        raise CandidateBindingError('facet_not_in_pattern', 'The supplied facet does not belong to the parent pattern.')
    return {'pattern_id': pid, 'rule_id': rid, 'facets': list(parent['facets']), 'contract': deepcopy(rules[rid])}
