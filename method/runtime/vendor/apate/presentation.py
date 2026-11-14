"""English display summaries without changing executable or evidential identity.

The catalogue remains the source of truth. These helpers copy their arguments;
the session helper adds a sidecar rather than changing model-hashed labels or
source quotations. CPS prose is explicitly presented as a curated summary.
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import json
import re

DATA = Path(__file__).resolve().parents[1] / 'data' / 'pattern_english.json'
CJK = re.compile(r'[\u3400-\u9fff]')

PREDICATES = {
    'reciprocal_opportunity': 'The Actor can genuinely ask questions and respond.',
    'approved_equivalent_channels': 'Both reciprocal and independent channels are approved and equally sufficient.',
    'no_uninterruptible_high_duty': 'No uninterruptible high-duty activity prevents the exchange.',
    'resources_available': 'The current discretion, time, energy and relevant work resources permit this optional activity.',
    'negotiable_request': 'The proposed arrangement is genuinely negotiable.',
    'own_nonmandatory_preference': 'A previously established non-mandatory personal preference conflicts with the request.',
    'both_responses_authorized': 'Both expressing an alternative and accepting are lawful and feasible.',
    'self_expression_difference': 'One plan expresses the personal position; the other explicitly does not.',
    'active_and_static_modes_available': 'Both active on-site and static implementations already exist.',
    'current_energy_and_physical_capacity': 'Current energy and physical capacity permit the active mode.',
    'same_business_and_safety_standard': 'Both modes meet the same required business and safety standards.',
    'activity_not_mandatory_or_speed_forced': 'Neither mandatory activity nor a hard speed requirement determines the mode.',
    'specific_difficulty_known': 'The Actor perceives a specific independently established difficulty affecting an identified person.',
    'relief_effect_known': 'The actual relief effect is independently recorded.',
    'minimum_service_guaranteed': 'Both complete plans provide all required service.',
    'voluntary_extra_relief': 'Effective additional relief is discretionary and may lawfully be omitted.',
    'voluntary_cost_affordable': 'Voluntary cost is within current disposable resources.',
    'voluntary_shared_resource': 'An additional shared resource is genuinely discretionary.',
    'allocation_norm_known_and_accepted': 'The Actor understands and accepts the specific current allocation norm.',
    'norm_not_mandatory_entitlement': 'The compared norm is not a mandatory entitlement.',
    'both_allocations_legal': 'Considering the share and retaining the resource are both lawful and respect actual rights.',
    'other_share_difference_known': 'Complete allocations differ with respect to the same soft sharing norm.',
    'unfamiliar_partner': 'The cooperation partner is unfamiliar to the Actor.',
    'identity_and_permission_verified': 'Identity, permission and channel checks are independently complete.',
    'bounded_reversible_nonsensitive_cooperation': 'Cooperation is bounded, reversible and limited to non-sensitive information.',
    'negative_cues_checked_and_absent': 'Negative cues were checked and no unexplained counterevidence remains; unchecked is insufficient.',
    'independent_alternative_valid': 'The same business can also be completed lawfully and independently.',
    'cooperation_optional': 'Taking the cooperative opportunity is optional.',
    'visible_disorder': 'The Actor currently perceives relevant materials as disordered.',
    'actor_directory_standard': 'The Actor accepts a specific current directory or classification standard.',
    'minimum_retention_satisfied': 'Both filing implementations satisfy minimum complete retention.',
    'organization_difference_known': 'The complete outcomes independently establish the material-organization difference.',
    'current_work_started': 'The current work unit has started and its completion checkpoint is identifiable.',
    'current_work_meaningful_solvable': 'Remaining work is meaningful and currently solvable with available resources.',
    'diversion_deferrable': 'The alternative activity can lawfully be deferred and still executed later.',
    'no_hard_interruption': 'No hard requirement forces immediate interruption.',
    'both_activities_selected': 'Both compared complete plans actually include both activities.',
    'prior_voluntary_actor_promise': 'The Actor previously made a specific voluntary promise to an identified recipient.',
    'promise_active_same_episode': 'The promise remains active for the same recipient and episode.',
    'promised_activity_optional': 'The activity remains lawfully optional; omission preserves business feasibility.',
    'promise_resources_and_deadline_feasible': 'Current resources and any independently established deadline permit fulfilment.',
    'large_environmental_change': 'The Actor has perceived a marked change relevant to the current matter.',
    'specific_current_unknown_status': 'A specific current status is genuinely unresolved.',
    'noninstrumental_information': 'The information cannot change the outcome.',
    'status_information_available': 'New status information and an implementation waiting for the same feedback both exist.',
    'information_cost_feasible': 'Information cost, channel and required business permit access.',
    'outcome_fixed_uncontrollable': 'The result will be revealed at a fixed later time and cannot be changed by the Actor.',
    'uncertainty_unresolved': 'The Actor does not yet know the outcome.',
    'accurate_early_information_available': 'Accurate early information and its lead time are established.',
    'known_nonzero_small_cost_affordable': 'A known nonzero small cost is affordable within permitted resources.',
    'same_final_result_and_feedback': 'Both complete plans have the same final result and feedback.',
    'independent_current_low_reward_wanting': 'Current low anticipated reward wanting has independent evidence.',
    'adequate_standard_handling_available': 'Standard processing already suffices for the required business.',
    'extra_effort_for_uncertain_increment': 'Additional active effort offers an explicit but uncertain incremental reward.',
    'both_plans_within_capacity': 'Both plans fit ability and resources; physical limitations do not explain the difference.',
    'extra_effort_not_necessary_verification': 'Extra effort is not required verification or a mandatory duty.',
    'attributable_current_provocation': 'The Actor attributes a specific current provocation or unfair criticism to the other party.',
    'independent_current_anger': 'Current anger has independent evidence.',
    'blame_and_neutral_responses_legal': 'Both blame-focused and neutral replies meet mandatory communication rules.',
    'same_verification_processing_records': 'Both responses retain the same required verification, processing and records.',
    'reactive_blame_difference_known': 'The complete responses differ in reactive blame toward the identified party.',
    'specific_question_before_choice': 'A specific knowledge question exists before the choice.',
    'independent_current_learning_interest': 'Current learning interest is not inferred from the predicted activity.',
    'minimum_execution_knowledge_sufficient': 'Minimum execution knowledge is already sufficient.',
    'authorized_relevant_new_explanation': 'An authorized source can provide a relevant new explanation.',
    'new_explorable_material': 'The Actor encounters new explorable facts or concepts.',
    'basic_business_already_handleable': 'The basic business problem can already be handled.',
    'autonomous_questioning_allowed': 'The Role permits autonomous formulation and recording of extension questions.',
    'new_unanswered_question_effect': 'The activity forms new relevant unanswered questions.',
    'genuine_aesthetic_material': 'The object is genuine artistic, musical, literary or explicitly aesthetic material.',
    'independent_current_aesthetic_interest': 'Relevant aesthetic interest is independently recorded before the choice.',
    'additional_aesthetic_exposure': 'The complete plans genuinely differ in additional aesthetic exposure.',
    'presentation_access_and_resources_available': 'Presentation, accessibility and current resources permit participation.',
    'aesthetics_not_business_authenticity': 'Appearance is not used to establish identity, authenticity or operational reliability.',
    'open_problem_multiple_acceptable_answers': 'The current problem is open and admits multiple acceptable answers.',
    'extra_generation_optional': 'Additional concept generation is beyond minimum business requirements.',
    'baseline_candidate_already_validated': 'A qualified baseline and its required validation already exist.',
    'independent_review_in_model': 'M0 already includes independent review after generation.',
    'exploration_not_unverified_implementation': 'Additional exploration does not automatically mean adoption or implementation.'
}

SOURCE_LEVELS = {
    'SOTO2017': 'Original BFI-2 construction research: direct construct evidence, not direct validation of business behavior or execution order.',
    'BREIL2022': 'Direct BFI-2-S facets; a small sample and two-item facet reliability limit inference. Composite skill expression differs from action preference.',
    'BREIL2019': 'Sociability-adjacent behavior with domain Extraversion predictors, not a separately measured BFI-2 Sociability facet.',
    'AMES2007': 'Broader assertiveness, including confrontation, is related to but not identical with BFI-2 Assertiveness.',
    'MOTTUS2016': 'State and single-item NEO-inspired measures, not stable BFI-2 Energy Level; activity associations are adjacent evidence.',
    'FELDMANHALL2015': 'Related IRI empathy/other-oriented concern rather than BFI-2 Compassion; small-sample association, not trait manipulation.',
    'ZHAO2017': 'Related Politeness and Compassion constructs are not identical with the corresponding BFI-2 facets.',
    'KOSUGI1998': 'Related general-trust beliefs measured with another instrument; outcomes are trustworthiness judgments rather than authentication or cooperation.',
    'RR2004': 'Related ordering/symmetry concerns measured by SOAQ, not BFI-2 Organization or a basis for diagnosis.',
    'BATES2024': 'Domain-level Conscientiousness, using TIPI or a NEO PI-R total; the read results are not BFI-2 Productiveness effects.',
    'KSW2023': 'Field experiment on a general promise mechanism; BFI-2 Responsibility was not measured.',
    'BENNETT2021': 'Direct BFI-2 Organization, Anxiety and Emotional Volatility plus broader composites. Supplementary facet correlations and main-factor findings remain separate.',
    'CHARPENTIER2022': 'Related STAI trait anxiety and induced state anxiety, not BFI-2 Anxiety.',
    'RAPP2024': 'Related STAI trait anxiety, not BFI-2 Anxiety; diagnostic groups are not personality facets.',
    'BG2007': 'Related trait anxiety, not the BFI-2 facet; exact instrument and grouping details were not verified within the recorded reading scope.',
    'TREADWAY2009': 'Related trait anhedonia, primarily Chapman scales with other measures; not BFI-2 Depression.',
    'CASINI2023': 'Direct BFI-2 Anxiety, Depression and Emotional Volatility in evaluative learning, not requirements-task selection.',
    'RTK2020': 'Related trait anger with situational anger and aggressive intentions, not BFI-2 Emotional Volatility or actual execution speed.',
    'PWK2018': 'Domain Neuroticism and induced state anger, not the BFI-2 Emotional Volatility facet.'
}

CRITERIA = {
    'AP-SOC-R1': 'The Actor actually participates in relevant two-way exchange; merely receiving a notification is insufficient.',
    'AP-ASSERT-R1': 'The other party is told the Actor\'s limitation or goal and a discussable alternative; agreement is not required.',
    'AP-ENERGY-R1': 'The Actor actively participates in on-site physical activity within the established scope.',
    'AP-COMPASSION-R1': 'The identified obstacle for the identified person is relieved under the current verifiable criterion.',
    'AP-RESPECT-R1': 'Allocation considers the other party\'s share under the specific accepted contribution/need norm; equal division is not assumed.',
    'AP-TRUST-R1': 'Explicit bounded reversible cooperation is actually attempted; success or genuine partner reliability is not required.',
    'AP-RD-ORG-01': 'The complete implementation organizes the relevant existing materials by the explicit current directory standard.',
    'AP-RD-PRO-01': 'The current meaningful work unit reaches its completion checkpoint continuously, rather than minimizing global time or steps.',
    'AP-RD-RES-01': 'The promised activity is completed for its recipient and content before this episode ends.',
    'AP-RD-ANX-01': 'The currently unknown specific status becomes known, without presuming reduced anxiety or improved business outcome.',
    'AP-RD-PREVIEW-01': 'The outcome becomes known earlier; safety, performance and final reward need not improve.',
    'AP-RD-DEP-01': 'Additional active effort is avoided under the current effort-reward structure while all required business is retained.',
    'AP-RD-VOL-01': 'Reactive blame is expressed toward the attributed party, separately from immediate processing or acceptance of the request.',
    'AP-IC-REDESIGN-01': 'An acknowledged knowledge gap that the Actor wants to understand is reduced.',
    'AP-IC-REDESIGN-02': 'Further relevant unanswered questions extend understanding beyond the immediately required knowledge.',
    'AP-AS-REDESIGN-01': 'Additional aesthetic contact with the work\'s form, emotion or expression occurs.',
    'AP-CI-REDESIGN-01': 'Additional acceptable possibilities are explored without treating unverified novelty as an implementation decision.'
}


@lru_cache(maxsize=1)
def _content():
    return json.loads(DATA.read_text(encoding='utf-8'))


def _rule_summary(rule_id, facet=None):
    data = _content()
    rule = data['rules'].get(rule_id)
    if rule is None:
        return None
    label = facet or ('the applicable facet')
    conditions = [
        f'Independent material about the concrete Actor supports {label}; this is not inferred from the predicted choice.',
        'The Actor plays the applicable Role in this Context, has actual discretion, and the comparison uses the same business, object and model version.'
    ] + list(rule['IF']) + [
        'Both complete plans satisfy M0 mandatory requirements, decomposition and hard pre/npr. Every necessary gate is true and the complete effects are known.'
    ]
    return {'Context': rule['Context'], 'Problem': rule['Problem'],
            'Solution': {'IF': conditions, 'THEN': list(rule['THEN']) + [data['support']],
                         'OTHERWISE': data['otherwise']}}


@lru_cache(maxsize=1)
def _translations():
    """Exact known prose matches only; never infer translations of new evidence."""
    from .patterns import load_catalogue, rule_contracts
    catalogue, data = load_catalogue(), _content()
    known = {}
    for rule in catalogue.get('rules', []):
        rid = rule['id']
        view = data['rules'].get(rid)
        if not view:
            continue
        known[rule['name']] = view['name']
        known[rule.get('inference_boundary', '')] = view['boundary']
        for key in ('Context', 'Problem'):
            known[rule.get('CPS', {}).get(key, '')] = view[key]
        concern = rule.get('instantiation', {}).get('concern')
        original = concern.get('criterion') if isinstance(concern, dict) else concern
        if original:
            known[original] = CRITERIA[rid]
    for pid, rule in rule_contracts().items():
        for predicate, original in rule.get('predicate_descriptions', {}).items():
            if predicate in PREDICATES:
                known[original] = PREDICATES[predicate]
    for pattern in catalogue.get('patterns', []):
        p = data['patterns'].get(pattern['id'], {})
        known[pattern['name']] = p.get('name', pattern['id'])
        for branch in pattern.get('CPS', {}).get('Solution', {}).get('case_branches', []):
            b = data['case_branches'].get(branch['branch_id'], {})
            for key in ('name', 'Context', 'Problem', 'OTHERWISE', 'trait_connection'):
                if key in b:
                    known[branch.get(key, '')] = b[key]
    known.update({
        '当前结果需要重新校验。': 'Revalidate the result against the current input.',
        '旧支持未保留或其证据已改变。': 'Previous support was not retained or its evidence changed.',
        '补全结果与当前M0不一致，旧支持不计为当前应用。': 'The result does not match the current M0; previous support is not counted as applied.',
        '当前有预置或导入候选，尚未校验；候选不计为已使用的pattern。': 'Candidates are available but have not been validated; they do not count as applied patterns.',
        '当前示例没有pattern候选；原有quality/时序偏好来自结构化模型，可单独用于手动权重演示。': 'This example has no pattern candidates. Its base qualities and temporal preferences come from the structured model.',
        'SeerWare 多角色维护（227条有限见证）': 'SeerWare multi-role maintenance (227 finite witnesses)',
        '小型服务模型（可调用真实SHOP2）': 'Small service model (native SHOP2 execution)',
        '五步转换与手动权重时序演示': 'Temporal maintenance and preference evaluation',
        'Research Persona（研究构造）': 'Research Persona (constructed example)'
    })
    known['Paul的Sociability、Assertiveness、Organization、Trust、Compassion、Intellectual Curiosity、Responsibility、Productiveness、Creative Imagination九细面是同一个人的定性研究构造，无程度、数值priority、权重或概率；相反关注允许并存。'] = (
        'Research Persona is one constructed research persona combining Sociability, Assertiveness, Organization, Trust, Compassion, '
        'Intellectual Curiosity, Responsibility, Productiveness and Creative Imagination. These qualitative facets '
        'have no numerical degree, priority, weight or probability; competing concerns may coexist.'
    )
    known.pop('', None)
    return known


def english_text(value, fallback=None):
    """Translate known display text; retain unknown quotations unless requested.

    Callers may supply a generic English diagnostic fallback. Unknown source
    passages are never presented as if an invented translation were exact.
    """
    if not isinstance(value, str) or not CJK.search(value):
        return value
    known = _translations()
    if value in known:
        return known[value]
    prefix = '本研究参考情境独立给定：'
    if value.startswith(prefix):
        remainder = english_text(value[len(prefix):])
        if not CJK.search(remainder):
            return 'This reference scenario independently specifies: ' + remainder
    match = re.fullmatch(r'(\d+)项旧支持未通过当前输入复核，已从应用统计排除。', value)
    if match:
        return match.group(1) + ' previous supports failed revalidation and were excluded from application counts.'
    if value.startswith('当前候选无法重新核验，未将旧支持计为已使用：'):
        return 'Current candidates could not be revalidated; previous support was excluded from applied-pattern counts.'
    return fallback if fallback is not None else value


def _rule_view(original, facet=None):
    result = deepcopy(original)
    rid = result.get('rule_id', result.get('id'))
    entry = _content()['rules'].get(rid)
    if entry is None:
        return result
    result['name'] = entry['name']
    result['CPS'] = _rule_summary(rid, facet)
    result['inference_boundary'] = entry['boundary']
    result['presentation_kind'] = 'curated_english_summary'
    result['status_label'] = 'Literature-informed transfer candidate; specific business behavior requires validation.'
    if 'predicate_descriptions' in result:
        result['predicate_descriptions'] = {p: PREDICATES.get(p, english_text(text))
                                            for p, text in result['predicate_descriptions'].items()}
    return result


def _pattern_view(original):
    result = deepcopy(original)
    pid = result.get('id', result.get('pattern_id'))
    entry = _content()['patterns'].get(pid)
    if entry is None:
        return result
    facet = (result.get('facets') or [None])[0]
    f = _content()['facets'].get(facet, {})
    result.update(name=entry['name'], construct_boundary=f.get('boundary', ''),
                  inference_boundary=f.get('evidence', ''),
                  presentation_kind='curated_english_summary',
                  status_label='Literature-informed candidate with independently evaluated conditional branches.')
    cps = result.setdefault('CPS', {})
    rule_ids = result.get('rule_ids', [])
    first = _content()['rules'].get(rule_ids[0], {}) if rule_ids else {}
    for key in ('Context', 'Problem'):
        cps[key] = entry.get(key, first.get(key, english_text(cps.get(key, ''))))
    solution = cps.setdefault('Solution', {})
    for branch in solution.get('branches', []):
        rid = branch.get('rule_id')
        summary = _rule_summary(rid, branch.get('facet', facet))
        if summary:
            branch.update(Context=summary['Context'], Problem=summary['Problem'], **summary['Solution'])
            branch['presentation_kind'] = 'curated_english_summary'
    for branch in solution.get('case_branches', []):
        entry_b = _content()['case_branches'].get(branch.get('branch_id'))
        if entry_b:
            branch.update(deepcopy(entry_b))
            branch['evidence_boundary'] = 'Case locations supply behavior or context evidence. Persona facet support still requires independent material.'
            branch['presentation_kind'] = 'curated_english_summary'
    if 'case_scope_note' in solution:
        solution['case_scope_note'] = 'Owned case branches and cross-references organize descriptive behavior and context. They neither supply Actor facet evidence nor become executable rule support.'
    for ref in solution.get('case_branch_refs', []):
        if isinstance(ref, dict):
            entry_b = _content()['case_branches'].get(ref.get('branch_id'), {})
            if entry_b and 'name' in ref:
                ref['name'] = entry_b['name']
    if 'branches' in result:
        result['branches'] = [_rule_view(b, b.get('facet', facet)) for b in result['branches']]
    return result


def _sources_view(sources):
    values = sources.values() if isinstance(sources, dict) else sources
    for source in values:
        if not isinstance(source, dict):
            continue
        sid = source.get('id')
        if sid in SOURCE_LEVELS:
            source['construct_level'] = SOURCE_LEVELS[sid]
        elif isinstance(source.get('construct_level'), str):
            source['construct_level'] = english_text(source['construct_level'])


def english_catalogue(catalogue):
    """Return the latest catalogue with reviewable English CPS summaries."""
    result = deepcopy(catalogue)
    data = _content()
    result['presentation'] = {k: data[k] for k in ('language', 'canonical_version', 'presentation_kind', 'notice')}
    result['common_contract'] = deepcopy(data['common_contract'])
    result['search_scope'] = 'Targeted primary-source search and reading; not a systematic or exhaustive review.'
    for key, facet in result.get('facets', {}).items():
        entry = data['facets'].get(key)
        if entry:
            facet.update(label=key, label_en=key, domain=entry['domain'],
                         construct_boundary=entry['boundary'], evidence_status=entry['evidence'])
    result['patterns'] = [_pattern_view(p) for p in result.get('patterns', [])]
    result['rules'] = [_rule_view(r, ' or '.join(r.get('facets', []))) for r in result.get('rules', [])]
    if 'machine_contracts' in result:
        result['machine_contracts'] = {pid: _pattern_view(c) for pid, c in result['machine_contracts'].items()}
    if 'rule_contracts' in result:
        result['rule_contracts'] = {rid: _rule_view(c, ' or '.join(c.get('facets', []))) for rid, c in result['rule_contracts'].items()}
    _sources_view(result.get('sources', {}))
    return result


def english_usage(report):
    """Localize the derived usage view while preserving the source session."""
    result = deepcopy(report)
    result['presentation'] = {'language': 'en', 'presentation_kind': 'curated_english_summary'}
    result['warnings'] = [english_text(w) for w in result.get('warnings', [])]
    for pattern in result.get('patterns', []):
        pid = pattern.get('id')
        entry = _content()['patterns'].get(pid, {})
        pattern['name'] = entry.get('name', english_text(pattern.get('name', '')))
        if 'card' in pattern:
            pattern['card'] = _pattern_view(pattern['card'])
        if 'contract' in pattern:
            pattern['contract'] = _pattern_view(pattern['contract'])
        for candidate in pattern.get('candidates', []):
            candidate['reason'] = english_text(candidate.get('reason', ''))
        for application in pattern.get('applications', []):
            for field in ('name', 'role_label'):
                actor = application.get('actor', {})
                if field in actor:
                    actor[field] = english_text(actor[field])
            rid = application.get('rule_id')
            rule = _content()['rules'].get(rid, {})
            application['rule_name'] = rule.get('name', english_text(application.get('rule_name', '')))
            application['inference_boundary'] = rule.get('boundary', english_text(application.get('inference_boundary', '')))
            if isinstance(application.get('concern'), dict) and rid in CRITERIA:
                application['concern']['criterion'] = CRITERIA[rid]
            for fact in application.get('facts', []):
                fact['description'] = PREDICATES.get(fact.get('predicate'), english_text(fact.get('description', '')))
                for evidence in fact.get('evidence', []):
                    evidence['text_en'] = english_text(evidence.get('text', ''))
            for evidence in application.get('persona_evidence', []):
                evidence['text_en'] = english_text(evidence.get('text', ''))
            _sources_view(application.get('sources', []))
    return result




def english_session(session):
    """Add display labels without changing model hashes or original evidence."""
    result = deepcopy(session)
    model = session.get('model', {})
    role_labels = {}
    for rid, role in model.get('roles', {}).items():
        label = role.get('label', rid) if isinstance(role, dict) else role
        role_labels[rid] = english_text(label)
    label = session.get('name', model.get('label', model.get('name', model.get('id', 'Requirements model'))))
    result['presentation'] = {
        'language': 'en',
        'model_label': english_text(label),
        'persona_name': english_text(session.get('persona', {}).get('name', '')),
        'node_labels': {nid: english_text(node.get('label', nid)) for nid, node in model.get('nodes', {}).items()},
        'role_labels': role_labels,
        'note': 'Display labels only. Model data, evidence quotations, identities and hashes remain unchanged.'
    }
    return result
