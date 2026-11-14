"""Finite original-label evidence for the existing reciprocal-contact outcome.

This module produces evidence, never preferences. Unrecognized contact remains
UNKNOWN; canonical callers still check roles, scope, same-outcome differences,
original quality counterevidence and complete feasible witness pairs.
"""
import re

_ARTIFACT = r'\b(manuals?|documentation|documents?|guides?|handbooks?|faqs?|references?|files?|records?|recordings?|transcripts?|scripts?|notes?|schedules?|summar(?:y|ies))\b'
_PASSIVE_EVENT = r'\b(prerecorded|pre-recorded|recorded|recording|transcript|broadcast|one-way|planning|training|course|skills?|committee|membership)\b'
_HUMAN = r'\b(advis[eo]rs?|colleagues?|peers?|clients?|customers?|persons?|people|staff|teams?|partners?|patrons?|participants?|interlocutors?|reviewers?)\b'
_DENIED = (r'\b(no|not|never|without|avoid\w*|if|unless|when|pending|provided|conditional\w*|may|might|'
           r'lack\w*|absen\w*|unavailable|prevent\w*|failed|failure)\b|\b(don.t|can.t|cannot|subject to|only after|after approval|before approval)\b')
_NONHUMAN_PARTNER = r'\bwith\s+(?:(?:a|an|the)\s+)?(?:chatbot|bot|robot|automated\s+system|database|api)\b'
_CONTACT_EXCLUSION = (r'\bwithout\s+(?:(?:any|reciprocal|two-way|live|interpersonal)\s+)*'
                      r'(?:conversation|dialogue|discussion|interaction|contact)s?\b'
                      r'(?=\s*(?:$|[.;,]|\b(?:and|or|but|then|with|before|after|unless|if|when|while|during|without|not|no|never)\b))')


def _text(label):
    value = str(label).lower().translate(str.maketrans({'–': '-', '—': '-', '‑': '-', '’': "'", '“': '"', '”': '"'}))
    value = re.sub(r'\bquestions?-and-answers?\b', 'q&a', value)
    value = re.sub(r'\bq\s*&\s*a\b', 'q&a', value)
    # Quoted action names are object mentions, not performed clauses.
    value = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', ' ', value)
    return ' '.join(value.split())


def _term(text, value):
    if _text(value) == 'q&a':
        return bool(re.search(r'\b(?:q&a|questions?\s+and\s+answers?)\b', text))
    pattern = re.escape(_text(value)).replace(r'\-', '[- ]').replace(r'\ ', r'\s+')
    return bool(pattern and re.search(r'(?<!\w)' + pattern + r'(?!\w)', text))


def _denied(text):
    return '--' in text or bool(re.search(_DENIED, text))


def _event_subject(text):
    # Discussion about a manual is contact; a manual about discussion is not.
    return re.split(r'\b(?:about|regarding|concerning|on|of)\b', text, maxsplit=1)[0]


def _interaction(text, guard):
    return any(_term(text, noun) for noun in guard.get('interaction_nouns',
        ['consultation', 'discussion', 'conversation', 'q&a']))


def _reciprocal(text, guard):
    return any(_term(text, modifier) for modifier in guard.get('quality_modifiers',
        ['reciprocal', 'two-way', 'bidirectional']))


def contact_quality_matches(label, guard):
    text = _text(label)
    if _denied(text): return False
    subject = _event_subject(text)
    if re.search(_ARTIFACT + '|' + _PASSIVE_EVENT + '|' + _NONHUMAN_PARTNER, subject): return False
    # Consultation is already an authorized interaction event, not a new
    # outcome invented because a particular model happened to use this noun.
    nouns = list(guard.get('quality_nouns', ['communication', 'contact', 'conversation', 'discussion', 'participation']))
    nouns += list(guard.get('interaction_nouns', ['consultation', 'discussion', 'conversation', 'q&a']))
    return _reciprocal(subject, guard) and any(_term(subject, noun) for noun in nouns)


def _contact_binding(text, guard, role_labels):
    if not text or _denied(text): return None
    if re.search(r'^(?:read|review|study|record|index|summari[sz]e)\b.*\b(?:how to|steps? to|instructions? for|guide to)\b', text):
        return None
    heads = set(guard.get('task_action_heads', ['discuss', 'converse', 'consult']))
    participation = set(guard.get('task_participation_heads', ['join', 'participate', 'attend']))
    hosting = set(guard.get('task_hosting_heads', ['hold', 'conduct', 'host']))
    action_heads = '|'.join(re.escape(head) for head in sorted(heads | participation | hosting | {'ask'}))
    for clause in re.split(r'\s*;\s*|\s+and\s+(?=(?:' + action_heads + r')\b)', text):
        first = re.match(r'^([a-z]+)\b\s*(.*)$', clause)
        if not first: continue
        head, tail = first.groups()
        if re.search(_NONHUMAN_PARTNER, tail):
            continue
        if head in heads:
            if head != 'consult': return {'grammar': 'interpersonal_action_head'}
            counterpart = _event_subject(tail)
            if re.search(_ARTIFACT + '|' + _PASSIVE_EVENT, counterpart): continue
            if re.search(r'\b(?:automated|automatic|chatbot|robot|database|program)\b', counterpart): continue
            human = re.search(_HUMAN, counterpart)
            role = any(_term(counterpart, label) for label in role_labels if label)
            if human or role: return {'grammar': 'consult_original_person_or_role'}
        if head in participation or head in hosting:
            subject = _event_subject(tail)
            if re.search(_ARTIFACT + '|' + _PASSIVE_EVENT, subject): continue
            if not _interaction(subject, guard): continue
            # Hosting generic live/joint work does not establish contact.
            if head in hosting and not _reciprocal(subject, guard): continue
            return {'grammar': 'explicit_reciprocal_event_hosting' if head in hosting else 'participatory_interaction_event'}
    # Anchor both actions to an executable clause. A reading object's title
    # mentioning "ask and answer" cannot establish performed interaction.
    paired = re.search(r'(?:^|;\s*|\band\s+)ask(?:[- ]and[- ](?:answer|respond)|\b[^;]{0,35}\band\s+(?:answer|respond)\b)', text)
    if paired and not re.search(r'\b(alone|independently|yourself|itself|chatbot|database)\b', text):
        return {'grammar': 'paired_ask_and_reply_actions'}
    channel_heads = guard.get('task_channel_action_heads', ['obtain', 'seek', 'request', 'clarify', 'resolve', 'learn', 'get'])
    if (any(re.match(r'^' + re.escape(head) + r'\b', text) for head in channel_heads)
            and not re.search(_ARTIFACT + '|' + _PASSIVE_EVENT, text)
            and re.search(r'\b(?:via|through|in)\s+(?:live\s+)?q&a\b', text)):
        return {'grammar': 'active_reciprocal_question_answer_channel'}
    return None


def contact_task_matches(label, guard, role_labels=()):
    return bool(_contact_binding(_text(label), guard, role_labels))


def _explicit_noncontact_action(text):
    """Recognize performed, expressly one-way/independent artifact operations.

    This is negative evidence for reciprocal contact, not an assumption from
    an unrecognized action. Remove only the explicit contact exclusion before
    checking all other negations, conditions and compound/participant clauses.
    Local installation alone is not an independence assertion.
    """
    exclusion = _CONTACT_EXCLUSION
    excludes_contact = bool(re.search(exclusion, text))
    body = re.sub(exclusion, ' ', text)
    independent = bool(re.search(r'\b(?:independently|alone|unassisted)\b', body))
    if not (excludes_contact or independent) or _denied(body):
        return None
    # A colleague/interactive channel or another performed clause defeats the
    # narrow proof. An artifact recipient ("to a customer") is not by itself
    # reciprocal participation, but "with a colleague" is left unresolved.
    if re.search(r';|\b(?:and|or|but|then|before|after|subsequently|with|together|joint\w*|shared|collaborative|interactive|'
                 r'alongside|among|between|while|during|via|through)\b', body):
        return None
    if re.search(r'\b(?:(?:consult|discuss|convers|ask|answer|join|participat)\w*|technician|instructor)\b', body):
        return None
    action = re.sub(r'^(?:independently|alone|unassisted)\s+', '', body).strip()
    transfer = re.match(r'^(?:send|supply|provide|deliver|issue|distribute|give)\b', action)
    document = re.search(r'\b(?:handouts?|documents?|guides?|manuals?|notices?|bulletins?|instructions?|schedules?|'
                         r'written\s+(?:instructions?|refusals?|responses?|material))\b', action)
    if transfer and document:
        return {'effect': 'absent', 'grammar': 'explicit_nonconversational_artifact_transfer'}
    if re.match(r'^(?:read|review|study|use)\b', action) and document:
        return {'effect': 'absent', 'grammar': 'explicit_independent_document_action'}
    installation = re.match(r'^(?:install|load|apply)\b', action)
    package = re.search(r'\b(?:patch|package|update|software|firmware|application|program)\b', action)
    local_media = re.search(r'\bfrom\s+(?:(?:the|same|verified|approved|signed|trusted|local)\s+)*'
                            r'(?:media|(?:cd|dvd|tape|disk|disc|usb)(?:\s+(?:media|drive))?)\b', action)
    explicitly_local = bool(re.search(r'\blocal\b', action))
    if installation and package and local_media and explicitly_local:
        return {'effect': 'absent', 'grammar': 'explicit_independent_local_media_operation'}
    return None


def contact_task_semantics(label, guard, role_labels=()):
    """Classify literal task evidence; UNKNOWN must never become ABSENT."""
    text = _text(label)
    present = _contact_binding(text, guard, role_labels)
    if present: return {'effect': 'present', **present}
    explicit = _explicit_noncontact_action(text)
    if explicit: return explicit
    # A negative contact modifier on an otherwise performed reading action
    # negates the contact, not the reading. Other "without ..." clauses still
    # block the proof, as do independent conditions or collaborative clauses.
    text = re.sub(_CONTACT_EXCLUSION, ' ', text)
    if not text or _denied(text): return {'effect': 'unknown', 'grammar': None}
    # Performed reading, or use of an explicitly written artifact as the
    # channel, gives a finite negative proof. Generic "use" is unresolved.
    heads = guard.get('solitary_document_action_heads', ['read', 'review', 'study'])
    document_action = any(re.match(r'^' + re.escape(head) + r'\b', text) for head in heads)
    written_use = (any(re.match(r'^' + re.escape(head) + r'\b', text)
                       for head in guard.get('solitary_written_use_heads', ['use']))
                   and re.search(r'\bwritten\b', text) and re.search(_ARTIFACT, text))
    if ((document_action or written_use)
            and re.search(_ARTIFACT + r'|\b(written\s+(?:instructions?|material)|text)\b', text)
            and not re.search(r'\b(with|together|joint\w*|shared|collaborative|interactive|alongside|among|between|while|during|via|through)\b', text)
            and not re.search(r'\bto\s+(?:consult|discuss|converse|ask|answer|join|participate)\b', text)
            and not re.search(r';|\b(?:and|or|but|then|before|after|subsequently)\b', text)):
        return {'effect': 'absent', 'grammar': 'explicit_written_artifact_use' if written_use else 'solitary_written_artifact_action'}
    return {'effect': 'unknown', 'grammar': None}


def direct_contact_evidence(model, scope, guard, must_nodes):
    role_labels = [value if isinstance(value, str) else value.get('label', '')
                   for value in model.get('roles', {}).values()]
    return [{'node_id': node, 'quote': model['nodes'][node]['label']}
            for node in sorted(must_nodes(model, scope, scope))
            if model['nodes'][node]['kind'] == 'task'
            and contact_task_matches(model['nodes'][node]['label'], guard, role_labels)]


def direct_solitary_evidence(model, scope, guard):
    """Every possible scope leaf must prove an explicit noncontact operation.

    This is evidence only. Callers must reject original reciprocal-quality
    counterevidence and verify roles, scope and complete feasible witnesses.
    Optional/OR contact is not silently ignored.
    """
    refs = {row['parent']: row for row in model.get('refinements', [])}
    pending = [scope]; visited = set(); leaves = []
    roles = [v if isinstance(v, str) else v.get('label', '') for v in model.get('roles', {}).values()]
    while pending:
        node = pending.pop()
        if node in visited: continue
        visited.add(node)
        entry = model['nodes'].get(node)
        if not entry: return []
        if entry['kind'] == 'task':
            proof = contact_task_semantics(entry['label'], guard, roles)
            if proof['effect'] != 'absent': return []
            for field, segment in _original_field_segments(entry):
                if field != 'label' and (contact_task_semantics(segment, guard, roles)['effect'] == 'present'
                        or _possible_contact_action(_text(segment), guard, roles)):
                    return []
            leaves.append({'node_id': node, 'quote': entry['label'], 'role': entry.get('role'), 'grammar': proof['grammar']})
        elif entry['kind'] == 'goal' and node in refs:
            pending.extend(child for child in refs[node]['children'] if model['nodes'][child]['kind'] in ('task', 'goal'))
        else: return []
    return sorted(leaves, key=lambda row: row['node_id'])


def _original_field_segments(node):
    """Keep original semantic fields and sentences independent of label heads."""
    for field in ('label', 'description', 'meaning'):
        value = node.get(field)
        if isinstance(value, str):
            for segment in re.split(r'(?<=[.!?])\s+|[\r\n]+', value):
                if segment.strip():
                    yield field, segment.strip()


def _possible_contact_action(text, guard, role_labels):
    """A condition on an interpersonal action is unresolved, not negative."""
    text = re.sub(r'^(?:if|when|unless)\b[^,;]*[,;]\s*', '', text)
    text = re.split(r'\b(?:if|when|unless|pending|provided)\b', text, maxsplit=1)[0]
    text = re.sub(r'^(?:possibly|optionally|conditionally|may|might)\s+', '', text)
    if _contact_binding(text, guard, role_labels):
        return True
    # A single performed reply/telephone action may provide interpersonal
    # opportunity without a literal "with" phrase or a paired ask-and-answer
    # construction. This is an unknown-contact veto only, never a positive
    # reciprocal-contact certificate. Reading an answer manual is not replying.
    response = re.match(r'^(?:answer|reply|respond|ask|call|phone|telephone)\b\s*(.*)', text)
    if response:
        tail = response[1]
        artifact_only = re.search(_ARTIFACT + r'|\b(?:handouts?|answer\s+manuals?)\b', tail)
        human = re.search(_HUMAN + r'|\b(?:technicians?|instructors?|operators?|advisers?)\b', tail)
        if not artifact_only and (human or any(_term(tail, role) for role in role_labels if role)):
            return True
    # Unknown verbs with an explicit human participant cannot be certified
    # noninterpersonal by a surrounding goal claim. Artifact contents such as
    # "advisor notes" are not themselves participating people.
    with_object = re.search(r'\bwith\s+(?:(?:a|an|the|verified|named|independent)\s+)*(.+)', text)
    if with_object:
        counterpart = with_object[1]
        if re.search(r'\b(?:notes?|records?|files?|details?|documentation|manuals?)\b', counterpart):
            return False
        return bool(re.search(_HUMAN + r'|\b(?:technicians?|instructors?|operators?|advisers?)\b', counterpart)
                    or any(_term(counterpart, role) for role in role_labels if role))
    return False


def scope_noncontact_evidence(model, scope, guard):
    """Literal completed-scope assertion, vetoed by any represented contact.

    A completed implementation explicitly declared without conversation can
    cover neutral bookkeeping leaves. A general objective, local channel,
    tutorial or absence of recognized interaction cannot provide this proof.
    Descendants include every nested OR alternative and optional activity.
    """
    nodes = model.get('nodes', {})
    entry = nodes.get(scope, {})
    label = entry.get('label', '')
    text = _text(label)
    if entry.get('kind') != 'goal':
        return []
    if re.match(r'^(?:read|review|study|explain|understand|learn|choose|select|plan|goal|aim|'
                r'knowledge|understanding|description|overview|example|training|simulation)\b', text):
        return []
    if re.match(_ARTIFACT, text):
        return []
    if not re.search(r'\b(?:completed|performed|carried out|conducted|delivered|installed|handled|processed)\s+'
                     + _CONTACT_EXCLUSION, text):
        return []
    body = re.sub(_CONTACT_EXCLUSION, ' ', text)
    if _denied(body) or re.search(r';|\b(?:and|or|but|then)\b', body):
        return []
    refs = {row['parent']: row['children'] for row in model.get('refinements', [])}
    region, pending = set(), [scope]
    roles = [v if isinstance(v, str) else v.get('label', '') for v in model.get('roles', {}).values()]
    while pending:
        node = pending.pop()
        if node in region:
            continue
        region.add(node)
        item = nodes[node]
        for field, original in _original_field_segments(item):
            if item['kind'] == 'task':
                # Do not concatenate a neutral label with a separate meaning:
                # that would hide the meaning's actual interpersonal verb.
                without_modifier = re.sub(_CONTACT_EXCLUSION, ' ', _text(original))
                state = contact_task_semantics(original, guard, roles)['effect']
                if (state == 'present' or _contact_binding(without_modifier, guard, roles)
                        or state == 'unknown' and _possible_contact_action(without_modifier, guard, roles)):
                    return []
            elif node != scope and contact_quality_matches(original, guard):
                return []
        pending.extend(child for child in refs.get(node, []) if nodes[child]['kind'] in ('goal', 'task'))
    for edge in model.get('contributions', []):
        target = nodes.get(edge['target'], {})
        if (edge['source'] in region and edge['type'] in ('makes', 'helps')
                and any(contact_quality_matches(segment, guard) for field, segment in _original_field_segments(target))):
            return []
    return [{'node_id': scope, 'quote': label, 'field': 'label',
             'grammar': 'explicit_completed_scope_without_contact',
             'all_original_descendants_checked': sorted(region)}]
