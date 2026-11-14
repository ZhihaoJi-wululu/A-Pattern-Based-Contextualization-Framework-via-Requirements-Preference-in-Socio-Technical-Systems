"""Traceable contracts over the three original inputs (v43-06).

This module neither calls a provider nor reads evaluation/reference files. It
recognizes limited, inspectable semantic grammars, original quality effects and
scope structure. Unsupported language remains unknown. Present/absent claims in
a mapper's response are never used as evidence. Feasibility, personality quote
validation and decision authority remain the caller's independent obligations.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .semantic_anchors import explicit_persona_counterevidence
from .material_objects import organization_direct_object
from .semantic_evidence import (contact_task_semantics, contact_quality_matches,
                                scope_noncontact_evidence, direct_solitary_evidence)


VERSION = 'apate.semantic-contracts.v43-06'
BUSINESS = {'goal', 'task'}
QUALITY = {'softgoal', 'hard_preference', 'quality'}
_FACET_CUES = {
    'Sociability': r'reciprocal|sociab|outgoing|conversation|discussion|exchang\w*\s+views|双向|社交|交谈',
    'Assertiveness': r'assert|express|speak\w*\s+up|speaks?\s+out|own\s+(?:position|opinion|boundar)|主张|表达|边界',
    'Energy Level': r'energetic|physically\s+active|active\s+(?:involvement|engagement)|moving\s+around|精力|身体活动',
    'Compassion': r'compassion|empathet|concern|care\w*\s+about|attends?\s+to|difficult|同情|关心|关怀',
    'Respectfulness': r'respect|courteous|consideration|sharing\s+norm|accepted\s+(?:voluntary|discretionary)\s+shares|尊重|份额',
    'Trust': r'trust|good\s+intentions|goodwill|bounded\s+cooperation|信任|善意|合作',
    'Organization': r'organiz|organis|orderly|systematic|indexing\s+convention|structure|条理|有序|系统|索引',
    'Productiveness': r'persist|finish|steadily|focused|complete\s+work|under\s+way|坚持|专注|完成',
    'Responsibility': r'promise|commitment|commit\w*|reliab|honors?|responsib|承诺|责任|可靠',
    'Anxiety': r'anxi|worr|apprehens|uncertain\w*.{0,45}(?:unsettling|unsettled)|焦虑|担忧|不安',
    'Depression': r'(?:low|little).{0,35}(?:wanting|incentive|motivation|desire)|少有.{0,12}(?:欲望|奖励)|奖励动机低',
    'Emotional Volatility': r'emotion\w*.{0,35}(?:react|strong|fluctuat)|moods?.{0,30}(?:chang|fluctuat)|react\w*.{0,25}emotion|情绪.{0,12}(?:强烈|波动)',
    'Intellectual Curiosity': r'curious|curiosity|understand|explanation|unanswered\s+questions|new\s+questions|求知|理解|新问题',
    'Aesthetic Sensitivity': r'aesthet|artistic|genuine\s+(?:visual\s+)?art|artistic\s+color|艺术|审美',
    'Creative Imagination': r'imagin|original\s+(?:ideas|ways)|additional\s+possibilit|open\s+problem|创造|想象|构思',
}
_WORDS = re.compile(r'[a-z]+')
_NEGATIVE_TRAITS = {
    'Sociability': r'\b(?:unsociable|asocial)\b',
    'Assertiveness': r'\b(?:unassertive|submissive)\b',
    'Energy Level': r'\b(?:unenergetic|habitually\s+inactive)\b',
    'Compassion': r'\b(?:uncaring|uncompassionate|unempathetic|callous)\b',
    'Respectfulness': r'\b(?:disrespectful|inconsiderate|exploitative)\b',
    'Trust': r'\b(?:distrustful|distrusting|suspicious\s+of\s+others)\b',
    'Organization': r'\b(?:disorgani[sz]ed|disorderly|unsystematic)\b',
    'Productiveness': r'\b(?:unproductive|habitually\s+abandons\s+work)\b',
    'Responsibility': r'\b(?:unreliable|irresponsible)\b',
    'Anxiety': r'\b(?:unworried|unapprehensive)\b',
    'Depression': r'\b(?:high|strong)\s+(?:reward.wanting|incentive.motivation)\b',
    'Emotional Volatility': r'\b(?:even.tempered|emotionally\s+stable)\b',
    'Intellectual Curiosity': r'\b(?:uncurious|uninterested\s+in\s+learning)\b',
    'Aesthetic Sensitivity': r'\b(?:uninterested\s+in\s+art|dislikes?\s+art\s+generally)\b',
    'Creative Imagination': r'\b(?:unimaginative|avoids?\s+ideation)\b',
}


def _text(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('‐', '-').replace('‑', '-')).strip().lower()


def _has(text, pattern):
    return bool(re.search(pattern, text, re.I))


def _negation_prefix(prefix):
    return re.split(r'[.;,:]|\bbut\b|\band\s+(?=(?:values?|enjoys?|is|has|keeps?|normally|usually|likes?|seeks?|expresses?|takes?|works?)\b)', prefix)[-1]


def _affirmed(text, pattern):
    """A domain cue is not made positive by a nearby explicit negation."""
    for match in re.finditer(pattern, text, re.I):
        prefix = _negation_prefix(text[max(0, match.start() - 42):match.start()])
        # A root inside an antonym is not an affirmative occurrence: reliable
        # in unreliable, organized in disorganized, sociable in unsociable.
        word_prefix = re.search(r'[a-z]+$', prefix)
        if word_prefix and word_prefix.group() in {'un', 'dis', 'in', 'non', 'anti'}:
            continue
        if re.search(r'(?:\b(?:no|not|never|without|neither|lack\w*|non)\b|rather\s+than|instead\s+of)[^.;,:]{0,36}$', prefix):
            continue
        return True
    return False


def validated_persona_counterevidence(persona, rule, quote, model=None, proposal=None):
    """Validate a literal exception instead of trusting the mapper's label.

    Return a traceable record, or None when the supplied quote does not actually
    express this facet's contrary disposition or relevant content aversion.
    """
    description = persona.get('description', '')
    if not isinstance(quote, str) or not quote.strip() or quote not in description: return None
    facet = rule.get('facet'); text = _text(quote)
    negative = _NEGATIVE_TRAITS.get(facet)
    reason = None
    if negative and _affirmed(text, negative): reason = 'explicit_contrary_trait'
    if facet == 'Organization' and explicit_persona_counterevidence(quote): reason = 'explicit_organization_counterpreference'
    if facet == 'Organization':
        incompatible_standard = (
            _affirmed(text, r'\b(?:adding|using|creating|building|adopting|additional)\b.{0,35}\b(?:index\w*|categor\w*|classif\w*)\b.{0,65}\b(?:violat\w*|breach\w*|contradict\w*)\b.{0,35}\b(?:standard|policy|rule|requirement|preference)\b')
            or _affirmed(text, r'\b(?:own|personal|accepted|existing)\b.{0,30}\b(?:standard|policy|rule|preference)\b.{0,50}\b(?:forbids?|prohibits?|rejects?|excludes?)\b.{0,30}\b(?:index\w*|categor\w*|classif\w*)\b')
            or _has(text, r'(?:添加|采用|建立|额外).{0,8}(?:索引|分类).{0,18}(?:违反|违背).{0,12}(?:标准|规则|偏好)'))
        if incompatible_standard: reason = 'explicit_organization_standard_conflict'
    cue = _FACET_CUES.get(facet)
    if cue and facet != 'Depression':
        for m in re.finditer(cue, text):
            prefix = _negation_prefix(text[max(0, m.start() - 55):m.start()])
            word_prefix = re.search(r'[a-z]+$', prefix)
            if word_prefix and word_prefix.group() in {'un', 'dis', 'in', 'non', 'anti'}: continue
            if re.search(r'\b(?:does?\s+not|is\s+not|never|rarely|seldom|dislikes?|rejects?|avoids?|lacks?)\b[^.;,:]{0,38}$', prefix):
                reason = 'explicit_negation_of_this_facet'; break
    if facet == 'Aesthetic Sensitivity' and model and proposal:
        source = proposal.get('source'); graph = _Graph(model)
        if source in graph.nodes:
            match = re.search(r'\b(?:dislikes?|rejects?|avoids?|averse\s+to)\b\s+([^.;]+)', text)
            if match and _affirmed(text, re.escape(match.group(0).split()[0])):
                content = set(_WORDS.findall(match.group(1))) - {'the', 'a', 'an', 'this', 'that', 'particular'}
                modeled = set(_WORDS.findall(graph.original_text(graph.region(source))))
                # An aversion to jazz cannot suppress a painting opportunity.
                if content & modeled and _has(match.group(1), r'art|paint|music|jazz|mural|poem|liter|sculpt|艺术|画'):
                    reason = 'explicit_aversion_to_modeled_artistic_content'
    return {'supported': True, 'quote': quote, 'facet': facet, 'reason': reason, 'version': VERSION} if reason else None


_PERSONA_PREDICATES = {
    'Sociability': r'^(?:sociable\b|outgoing\b|(?:enjoys?|likes?|seeks?|values?|prefers?)\s+(?:reciprocal\s+|two-way\s+|interpersonal\s+)?(?:conversation|discussion|exchanging\s+views|social\s+contact)|喜欢.{0,8}(?:交流|交谈)|性格开朗|善于交际)',
    'Assertiveness': r'^(?:assertive\b|comfortable\s+speaking\s+up\b|(?:express\w*|state\w*|speak\w*\s+up|speaks?\s+out|set\w*)\b.{0,45}\b(?:own|personal|position|views?|opinions?|boundar)|(?:readily\s+)?express\w*\s+a\s+personal\s+position|敢于表达|表达.{0,8}(?:本人|自己|个人).{0,8}(?:立场|边界|观点))',
    'Energy Level': r'^(?:energetic\b|physically\s+active\b|(?:enjoys?|likes?|seeks?|values?|prefers?)\s+(?:being\s+)?(?:physically\s+active|physical(?:ly\s+active)?\s+(?:activity|involvement|engagement)|active\s+involvement)|精力充沛|喜欢身体活动|喜欢运动)',
    'Compassion': r'^(?:compassionate\b|empathetic\b|caring(?:\s*$|\s+toward)|concerned\s+about\b.{0,65}(?:others?|people|needs?|suffering)|(?:cares?\s+about|feels?\s+compassionate\s+concern\s+for)\b.{0,55}(?:others?|people|colleagues?|difficult)|关心他人|富有同情心|关怀他人)',
    'Respectfulness': r'^(?:respectful\b|courteous\b|considerate\b|treat\w*\s+(?:other\s+)?people\s+with\s+respect|follow\w*\s+(?:voluntarily\s+)?accepted\s+(?:sharing\s+norms?|voluntary\s+shares)|respect\w*\s+(?:other\s+people|others?)(?:\b|\x27)|尊重他人|待人有礼|考虑他人.{0,8}(?:权利|份额|需要))',
    'Trust': r'^(?:trusting\b|(?:has?|have)\s+(?:a\s+)?(?:generally\s+)?trusting\s+view\s+of\s+other\s+people|regard\w*\s+other\s+people\s+as\s+(?:honest|trustworthy)|trust\w*\s+(?:other\s+)?(?:people|others|colleagues)|assum\w*\s+good\s+intentions|willing\s+to\s+(?:try|offer|enter|extend|undertake|engage\s+in|participate\s+in)\b.{0,40}(?:bounded\s+cooperation|goodwill)|愿意信任他人|信任他人|相信他人的善意)',
    'Organization': r'^(?:(?:organi[sz]ed|orderly|systematic)(?:\s*$|\s+(?:at\s+work|in\s+daily\s+life))|(?:likes?|prefers?|values?)\s+(?:to\s+)?(?:keep\s+)?(?:orderly\s+(?:working\s+)?(?:materials|records|papers|files|workspace|routines)|order\s+and\s+structure|orderliness|materials\s+systematically\s+organi[sz]ed)|(?:keeps?|maintains?)\b.{0,65}\b(?:materials|papers|records|routines|workspace|files)\b.{0,40}\b(?:organi[sz]ed|orderly|systematic)|有条理|习惯.{0,8}(?:系统整理|有序整理)|保持.{0,12}(?:井然有序|有条理))',
    'Productiveness': r'^(?:persistent\b|productive\b|focused\b|(?:works?\s+steadily|stays?\s+focused|persists?\b|finishes?\s+what\s+(?:she|he|they|one)\s+starts?)|坚持完成|做事专注|持续推进工作)',
    'Responsibility': r'^(?:reliable\b|responsible(?:\s*$|\s+about\s+(?:personal\s+)?(?:promises|commitments))|takes?\s+(?:her\s+|his\s+|their\s+|own\s+)?(?:personal\s+)?promises?\s+seriously|(?:keeps?|honors?|honours?|fulfills?)\s+(?:the\s+|her\s+|his\s+|their\s+|own\s+|personal\s+|voluntary\s+)*(?:commitments?|promises?)|认真对待.{0,8}承诺|信守.{0,8}承诺|为人可靠)',
    'Anxiety': r'^(?:anxious\b|worried\b|apprehensive\b|worr(?:y|ies)\b|find\w*\s+uncertainty\b.{0,45}(?:unsettling|unsettled)|容易担忧|通常感到焦虑|经常担心)',
    'Depression': r'^(?:(?:has?|have|feels?|experiences?)\s+)?(?:low|little)\b(?=.{0,75}\b(?:reward\w*|incentive)\b).{0,40}(?:wanting|incentive\s+motivation|motivation|desire)\b|^(?:奖励动机低|通常少有.{0,10}(?:奖励欲望|奖励动机))',
    'Emotional Volatility': r'^(?:emotionally\s+(?:volatile|reactive)|(?:experience\w*|has?|feels?)\s+(?:strong\s+)?emotional\s+reactions|feelings?\b.{0,35}(?:change|react|fluctuat)|moods?\b.{0,35}(?:change|fluctuat)|react\w*\s+(?:strongly\s+)?emotionally|情绪容易波动|情绪反应强烈)',
    'Intellectual Curiosity': r'^(?:(?:intellectually\s+)?curious\b|(?:enjoys?|likes?|values?|seeks?)\s+(?:reading\s+explanations|understanding\b|explanations\b|exploring\s+new\s+questions)|求知欲强|喜欢理解.{0,8}(?:原理|机制)|喜欢探索新问题)',
    'Aesthetic Sensitivity': r'^(?:aesthetically\s+sensitive\b|attentive\s+to\s+(?:genuine\s+)?(?:artistic|aesthetic)|(?:has?|takes?|shows?)\s+(?:an?\s+)?(?:sustained\s+|lasting\s+)?interest\s+in\s+(?:genuine\s+)?(?:visual\s+)?art\b|(?:values?|enjoys?|appreciates?|likes?)\s+(?:appreciating\s+)?(?:genuine\s+)?(?:visual\s+art\b|artistic\s+(?:experience|color|form)|art\b|music\b|literature\b|aesthetic\s+experience)|审美敏感|喜欢欣赏.{0,8}(?:艺术|音乐|文学)|重视艺术体验)',
    'Creative Imagination': r'^(?:imaginative\b|(?:has?|have)\s+(?:an?\s+)?(?:active\s+)?imagination\b|(?:enjoys?|likes?)\s+(?:imagining\b|generating\s+original\s+ideas)|(?:imagines?|thinks?\s+of)\b.{0,45}(?:original\s+(?:ideas|ways)|additional\s+possibilities)|富有想象力|喜欢构思.{0,8}(?:新想法|多种可能))',
}
_PERSONA_FREQUENCY = r'(?:usually|normally|generally|typically|often|regularly|habitually|readily|reliably|also|calmly|assertively|traditionally|consistently|chronically)'


def _persona_aliases(persona):
    aliases = {'the actor', 'this person', 'the person', 'the persona', 'he', 'she', 'they', 'i', '本人', '他', '她'}
    name = str(persona.get('name', '')).split(',')[0].strip()
    if name:
        aliases.add(name.lower())
        aliases.add(name.split()[0].lower())
        if len(name.split()) > 1 and name.split()[-1].lower() in {'operator','coordinator','clerk','administrator','janitor','demonstrator','librarian'}:
            aliases.add('the ' + name.split()[-1].lower())
    identity = persona.get('actor_id')
    if isinstance(identity, str) and identity.strip(): aliases.add(identity.lower())
    for role in persona.get('role_ids', []):
        if isinstance(role, str) and re.fullmatch(r'[A-Za-z]{3,}', role): aliases.add('the ' + role.lower())
    if not name and not identity:
        # A metadata-light profile can still explicitly identify its subject.
        match = re.match(r'\s*([A-Z][A-Za-z-]*)\s+(?:is|has|usually|normally|generally|often|tends|enjoys|likes|reliably|prefers|keeps|supports|follows|works|manages|coordinates|studies|maintains|values)\b', persona.get('description', ''))
        if match: aliases.add(match[1].lower())
    return sorted(aliases, key=len, reverse=True)


def _persona_own_clauses(persona, quote):
    """Identify descriptive predicates about this persona, without cue search."""
    aliases = _persona_aliases(persona)
    actor = '|'.join(re.escape(a) for a in aliases)
    spaced = '|'.join(re.escape(a) for a in aliases if re.fullmatch(r'[\x00-\x7f]+', a))
    unspaced = '|'.join(re.escape(a) for a in aliases if not re.fullmatch(r'[\x00-\x7f]+', a))
    subject = r'(?:' + spaced + r')(?=\s|$)' + (r'|(?:' + unspaced + ')' if unspaced else '')
    actor_prefix = re.compile(r'^(?:' + subject + r')\s*(.*)$', re.I)
    reporters = r'(?:(?:her|his|their)\s+)?(?:friends|colleagues|coworkers|co-workers|people|others)'
    person_object = r'(?:her|him|them|' + actor + r')'
    predicate_start = r'^(?:is|am|are|remains?|feels?|tends?|enjoys?|likes?|values?|prefers?|seeks?|keeps?|maintains?|works?|stays?|persists?|finishes?|takes?|honors?|honours?|fulfills?|express\w*|states?|sets?|speaks?|regards?|trusts?|assumes?|has|have|follows?|cares?|experiences?|' + _PERSONA_FREQUENCY + r'|does?\s+not|never|rarely|seldom)\b'
    possession = r'(?:(?:her|his|their|own|my)\s+|(?:' + actor + r")'s\s+)"
    material = r'(?:working\s+)?(?:materials|papers|records|routines|workspace|files)\b'
    sentences = re.split(r'(?<=[.!?。！？])\s+|\n+', quote)
    for sentence in sentences:
        scan = sentence.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
        scan = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', ' ', scan)
        scan = _text(scan).rstrip('.!?。！？')
        # Conditional antecedents do not assert that their consequent holds.
        if re.match(r'^(?:if|unless|suppose|supposing|imagine|假如|如果|若)\b', scan): continue
        bound = False; copular = False
        for fragment in re.split(r'\s*(?:[;,:，；：]|\band\b|\bbut\b)\s*', scan):
            fragment = re.sub(r'^(?:outside\s+work|away\s+from\s+work|at\s+work|in\s+quieter\s+moments|in\s+daily\s+life|in\s+general)\s+', '', fragment.strip())
            if not fragment: continue
            direct = actor_prefix.match(fragment)
            if direct:
                body = direct[1]
                if body.startswith("'s") or not body: continue
                bound = True; copular = bool(re.match(r'^(?:is|am|are|remains?|feels?)\b', body))
                yield body
                continue
            reported = re.match(r'^' + reporters + r'\s+(?:also\s+)?(?:describe|find|consider|regard)\s+' + person_object + r'\s+(?:as\s+)?(.+)$', fragment)
            if reported:
                bound = True; copular = True
                yield reported[1]
                continue
            relied = re.match(r'^' + reporters + r'\s+(?:rely\s+on|trust)\s+' + person_object + r'\s+to\s+(.+)$', fragment)
            if relied:
                bound = True; copular = False
                yield relied[1]
                continue
            # Habitual arrangement of one's working materials is descriptive
            # evidence; a database/system/organization being structured is not.
            owned = re.match(r'^(?:' + possession + r')' + material + r'\s+(?:are\s+)?(.+)$', fragment)
            reported_material = re.match(r'^' + reporters + r'\s+(?:find|describe)\s+(?:' + possession + r')' + material + r'\s+(?:as\s+)?(.+)$', fragment)
            implicit = re.match(r'^working\s+materials\s+are\s+' + _PERSONA_FREQUENCY + r'\s+(.+)$', fragment)
            arranged = owned or reported_material or implicit
            if arranged:
                yield 'keeps working materials ' + arranged[1]
                continue
            experiencer = re.match(r'^.{1,65}\b(?:often|usually|generally|regularly)\s+worr(?:y|ies)\s+(?:' + actor + r')\s*$', fragment)
            if experiencer:
                yield 'usually worries'
                continue
            if bound and (re.match(predicate_start, fragment) or copular):
                # An explicit different subject blocks inherited ownership.
                if (not re.match(predicate_start, fragment)
                        and re.search(r'\b(?:is|are|has|keeps|feels|works|enjoys|likes|values)\b', fragment)):
                    bound = False; copular = False
                    continue
                yield fragment


def _persona_predicate_status(body, facet):
    core = _text(body)
    # These suffixes bound a standing disposition; they do not assert a new
    # current state. Preserve them in the original quote, not in matching text.
    core = re.split(r'\beven\s+(?:when|if)\b', core, maxsplit=1)[0]
    core = re.sub(r'\bafter\s+(?:(?:identity|permission|permissions|verification|authorization|authentication)\b).*$', '', core)
    core = re.sub(r'\bwhen\s+(?:capacity|resources|time)\s+permits?\b.*$', '', core)
    if facet in {'Anxiety','Emotional Volatility'} and _has(core, r'\b(?:usually|often|normally|generally|tends?)\b'):
        core = re.split(r'\bwhen\b', core, maxsplit=1)[0]
    if facet == 'Trust' and _has(core, r'\bif\b.{0,75}\b(?:identity|identities|permissions?|authentication|verification)\b.{0,35}\b(?:verified|checked|complete|completed)\b'):
        core = re.split(r'\bif\b', core, maxsplit=1)[0]
    if _has(core, r'\b(?:if|unless|when|might|may|could|would|pretends?|role.play|hypothetically)\b|如果|假如|也许|可能|只有'):
        return 'unknown'
    if _has(core, r'\b(?:today|right now|this morning|currently|at the moment|in this episode)\b|今天|此刻|当前'):
        return 'unknown'
    usual = _has(core, r'\b' + _PERSONA_FREQUENCY + r'\b|\btends?\b|通常|经常|一贯')
    negative = False
    for _ in range(6):
        previous = core
        core = re.sub(r'^' + _PERSONA_FREQUENCY + r'\s+', '', core)
        core = re.sub(r'^(?:is|am|are|remains?|feels?)\s+', '', core)
        core = re.sub(r'^(?:通常|经常|一贯|总是|也|是|很)', '', core)
        core = re.sub(r'^tends?\s+to\s+(?:(?:be|feel)\s+)?', '', core)
        core = re.sub(r'^does?\s+', '', core)
        if re.match(r'^(?:not|never|rarely|seldom|no)\b\s*|^(?:并不|从不|很少|不)', core):
            core = re.sub(r'^(?:not|never|rarely|seldom|no)\b\s*|^(?:并不|从不|很少|不)', '', core)
            negative = not negative
        if core == previous: break
    contrary = _NEGATIVE_TRAITS.get(facet)
    if contrary and re.match(contrary, core):
        return 'unknown' if negative else 'contradicted'
    pattern = _PERSONA_PREDICATES.get(facet)
    if not pattern or not re.search(pattern, core): return 'unknown'
    if facet == 'Responsibility' and re.match(r'^responsible\s+for\b', core): return 'unknown'
    if facet == 'Depression' and not usual: return 'unknown'
    return 'contradicted' if negative else 'supported'


def persona_quote_evidence(persona, rule, quote):
    """Validate a literal quotation as this person's facet evidence.

    A keyword, job title, other person, teaching object or quoted role does not
    establish a trait. Unsupported language stays unknown. Matching never uses
    a case, reference, business endpoint, expected count or predicted direction.
    """
    facet = rule.get('facet'); description = persona.get('description', '')
    if (facet not in persona.get('facets', []) or facet not in _PERSONA_PREDICATES
            or not isinstance(description, str) or not isinstance(quote, str)
            or not quote.strip() or quote not in description):
        return {'supported': False, 'quote': quote if isinstance(quote, str) else '', 'status': 'unknown'}
    # A substring must not discard its negation, hypothetical antecedent or
    # teaching/quotation context. Resolve the same neutral original sentence
    # around each literal occurrence; no text outside the source is supplied.
    normalized = description.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
    quoted = [(m.start(),m.end()) for m in re.finditer(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', normalized)]
    spans=[];start=0
    for boundary in re.finditer(r'(?<=[.!?。！？])\s+|\n+', description):
        spans.append((start,boundary.start()));start=boundary.end()
    spans.append((start,len(description)))
    contexts=[]
    for occurrence in re.finditer(re.escape(quote),description):
        lo,hi=occurrence.span()
        if any(lo >= a and hi <= b for a,b in quoted): continue
        context=next((description[a:b] for a,b in spans if a<=lo and hi<=b),description)
        contexts.extend(_persona_predicate_status(body,facet) for body in _persona_own_clauses(persona,context))
    if not contexts: return {'supported':False,'quote':quote,'status':'unknown'}
    if 'contradicted' in contexts: return {'supported':False,'quote':quote,'status':'contradicted'}
    if 'supported' not in contexts: return {'supported':False,'quote':quote,'status':'unknown'}
    states = [_persona_predicate_status(body, facet) for body in _persona_own_clauses(persona, quote)]
    status = 'contradicted' if 'contradicted' in states else 'supported' if 'supported' in states else 'unknown'
    return {'supported': status == 'supported', 'quote': quote, 'status': status}


def persona_evidence(persona, rule):
    """Find supported original text in the common neutral sentence domain.

    Every facet examines the same full original description and neutral spans;
    no evidence is selected by a business decision or an evaluation answer.
    """
    description = persona.get('description', '')
    if not isinstance(description, str): return {'supported':False,'quote':'','status':'unknown'}
    segments = [s.strip() for s in re.split(r'(?<=[.!?。！？])\s+|\n+', description) if s.strip()]
    supported = None
    for segment in segments:
        certificate = persona_quote_evidence(persona, rule, segment)
        if certificate['status'] == 'contradicted': return certificate
        if certificate['supported'] and supported is None: supported = certificate
    return supported or {'supported':False,'quote':'','status':'unknown'}


class _Graph:
    def __init__(self, model):
        self.model = model
        self.nodes = model.get('nodes', {})
        self.refs = {r['parent']: r for r in model.get('refinements', [])}
        self.parents = {c: r['parent'] for r in self.refs.values() for c in r['children']}
        self._regions = {}; self._leaves = {}

    def kind(self, node):
        item = self.nodes.get(node, {})
        return item.get('kind', item.get('type'))

    def region(self, node):
        if node not in self.nodes or self.kind(node) not in BUSINESS: return set()
        if node not in self._regions:
            out = {node}
            for child in self.refs.get(node, {}).get('children', []): out |= self.region(child)
            self._regions[node] = out
        return set(self._regions[node])

    def leaves(self, node):
        if node not in self._leaves:
            self._leaves[node] = {x for x in self.region(node) if self.kind(x) == 'task'}
        return set(self._leaves[node])

    def ancestors(self, node):
        out = []
        while node in self.parents:
            node = self.parents[node]; out.append(node)
        return out

    def must(self, scope, implementation=None):
        forced = {}; child = implementation
        while child and child != scope and child in self.parents:
            parent = self.parents[child]
            if self.refs[parent]['kind'] == 'OR': forced[parent] = child
            child = parent
        def visit(node, top=False):
            if not top and self.nodes[node].get('optional'): return set()
            out = {node}; ref = self.refs.get(node)
            if not ref: return out
            if ref['kind'] == 'AND':
                for c in ref['children']: out |= visit(c)
            elif node in forced:
                out |= visit(forced[node])
            else:
                possibilities = [visit(c) for c in ref['children']]
                if possibilities: out |= set.intersection(*possibilities)
            return out
        return visit(scope, True) if scope in self.nodes else set()

    def implementations(self, scope):
        region = self.region(scope)
        return sorted({c for r in self.refs.values() if r['kind'] == 'OR' and r['parent'] in region for c in r['children']} or {scope})

    def original_text(self, ids):
        return ' ; '.join(self.node_text(i) for i in sorted(set(ids)) if i in self.nodes)

    def node_text(self, identity):
        node = self.nodes[identity]
        return _text(' '.join(str(node.get(k, '')) for k in ('label', 'description', 'meaning')))

    def evidence(self, ids, purpose):
        rows = []
        for identity in sorted(set(ids)):
            node = self.nodes.get(identity)
            if not node: continue
            for field in ('label', 'description', 'meaning'):
                value = node.get(field)
                if isinstance(value, str) and value.strip():
                    rows.append({'node_id': identity, 'field': field, 'quote': value, 'purpose': purpose})
        return rows

    def context(self, decision, source, target):
        ids = {decision.get('node_id')} | set(self.ancestors(source)) | set(self.ancestors(target))
        # Include original hard prerequisites, not unrelated business branches.
        relevant = self.region(source) | self.region(target) | {decision.get('node_id')}
        changed = True
        while changed:
            changed = False
            for e in self.model.get('hard_constraints', []):
                if e.get('type') == 'pre' and e.get('target') in relevant and e.get('source') not in relevant:
                    relevant.add(e['source']); ids |= self.region(e['source']); changed = True
        return {i for i in ids if i in self.nodes}

    def dependency_evidence(self, ids):
        rows = []
        for index, dep in enumerate(self.model.get('dependencies', [])):
            if not {dep.get('depender_node'), dep.get('dependee_node')} & set(ids): continue
            value = dep.get('dependum', {}).get('label')
            if isinstance(value, str) and value.strip():
                rows.append({'dependency_id': dep.get('id'), 'field': f'dependencies[{index}].dependum.label',
                             'quote': value, 'purpose': 'original_dependency_context'})
        return rows


_MATERIAL_STOP = set('a an the of for by in on at to with without same existing approved accepted agreed specified required additional extra original either permissible collection method mode option implementation processing process preserve preserved keep retain retained file filed build create prepare add sort tag group store save index indexed indexing categorize categorise categorized categorised category categories classify classification structure structured organize organise organized organised organization organisation append chronological received arrival order date subject topic under using according arrange arranged applied source'.split())
_MATERIAL_STOP.discard('source')  # Source records and completion records are distinct topics.
_MATERIAL_ALIASES = {'records': 'record', 'documents': 'document', 'materials': 'material', 'reports': 'report', 'files': 'file', 'entries': 'entry', 'notes': 'note', 'artifacts': 'artifact'}


def _material_words(text):
    words = {_MATERIAL_ALIASES.get(w, w) for w in _WORDS.findall(text) if w not in _MATERIAL_STOP and len(w) > 1}
    return {w for w in words if w not in _MATERIAL_STOP}


def _organization_action(text):
    if _has(text, r'\b(if|unless|when|pending|may|might|conditional)\b|仅当|除非|或许'):
        return 'unknown', _material_words(text)
    if _has(text, r'\b(read|review|explain|consult|watch|view|open|inspect)\b.{0,60}\b(index\w*|categor\w*|classif\w*)\s+(?:manual|guide|documentation|reference)|--index'):
        return 'not_action', set()
    material = organization_direct_object(text)
    if _has(text, r'^(?:index|categor\w*|classif\w*|structur\w*)\b'):
        if _has(text, r'\b(?:manual|documentation|guide|command\s+flag)\b'): return 'not_action', set()
        return ('positive', _material_words(material)) if material is not None else ('unknown', _material_words(text))
    if _has(text, r'^(?:file|organize|organise|sort|tag|group|arrange)\b') and _affirmed(text, r'\b(index|categor\w*|classif\w*|directory|topic\s+groups?)\b'):
        return ('positive', _material_words(material)) if material is not None else ('unknown', _material_words(text))
    if _has(text, r'^(?:create|build|prepare|add)\b') and _affirmed(text, r'\b(?:index|classification|category\s+structure)\b'):
        return ('positive', _material_words(material)) if material is not None else ('unknown', _material_words(text))
    if _has(text, r'^(?:append|retain|keep|file|store|save)\b') and _has(text, r'\b(?:received|arrival|chronological)\s+order\b|\bby\s+date\b|^append\b'):
        return ('baseline', _material_words(material)) if material is not None else ('unknown', _material_words(text))
    if _has(text, r'(?:索引|分类|分组|结构化|系统整理)') and not _has(text, r'(?:阅读|查阅|说明|解释).{0,15}(?:手册|指南|文档)'):
        stripped = re.sub(r'(?:按|根据|主题|类别|已定|接受|进行|分类|归档|分组|保存|整理|索引|结构化|系统)', '', text)
        return 'positive', {stripped} if stripped else set()
    if _has(text, r'(?:接收|收到|到达|时间|日期).{0,4}顺序'):
        stripped = re.sub(r'(?:按|根据|接收|收到|到达|时间|日期|顺序|保存|保留|归档)', '', text)
        return 'baseline', {stripped} if stripped else set()
    return 'unknown', _material_words(text)


def _same_material(left, right, parent):
    parent = _material_words(parent)
    if left and right and left == right: return sorted(left)
    # The OR supplies omitted topic words; unrelated qualifiers cannot disappear.
    if left and right and (left <= right or right <= left) and left | right <= parent:
        return sorted(left | right)
    if not left and right and right <= parent: return sorted(right)
    if not right and left and left <= parent: return sorted(left)
    if not left and not right and parent & {'record', 'material', 'document', 'evidence', 'file', 'report', 'data', 'archive', 'artifact', 'entry'}:
        return sorted(parent)
    return None


def _quality_sign(rule, outcome, text):
    """Return semantic polarity of an original quality; a mapper's tag is ignored."""
    rid = rule['id']; pattern = None
    if rid == 'MS-ORG-01': pattern = r'index\w*|categor\w*|classif\w*|structur\w*|systemati\w*|索引|分类|结构化'
    elif rid == 'MS-ASSERT-01': pattern = r'own\s+(?:position|opinion|boundar)|self.expression|个人主张|自我表达'
    elif rid == 'MS-ENERGY-01':
        if _affirmed(text, r'stationary|sedentary|physically\s+passive'): return -1
        pattern = r'physical\s+(?:activity|involvement|engagement)|physically\s+active|身体活动'
    elif rid == 'MS-RESPECT-01': pattern = r'(?:other\s+party|other\s+members?|counterpart).{0,65}(?:claim|share|contribution|need|consider)|accepted\s+share.{0,30}other|他人.{0,12}(?:份额|主张|需要)'
    elif rid == 'MS-TRUST-01': pattern = r'bounded.{0,45}(?:cooperat|joint\s+handl)|共同处理|有界合作'
    elif rid == 'MS-ANX-01': pattern = r'earl\w*.{0,35}accurate.{0,40}(?:knowledge|information)|accurate.{0,35}earl\w*.{0,35}(?:knowledge|preview)|准确.{0,8}(?:提前|早知)'
    elif rid == 'MS-VOL-01': pattern = r'(?:reactive|blame.focused).{0,90}(?:provocation|attribut)|挑衅.{0,15}(?:反应|责备)'
    elif rid == 'MS-AS-01': pattern = r'(?:sustain\w*|appreciat\w*|aesthetic\s+experience).{0,60}(?:art|paint|music|liter|mural)|artistic.{0,35}(?:appreciat|experience)|艺术欣赏'
    elif rid == 'MS-IC-01':
        pattern = (r'(?:new|unanswered|not.yet.answered).{0,45}questions?.{0,40}(?:generat|formulat)|questions?.{0,40}(?:independent|generat)|新问题' if outcome == 'new_question_generation'
                   else r'explanat\w*\s+understanding|understand\w*.{0,45}(?:impact|mechanism|topic)|additional.{0,40}(?:knowledge|explanation)|额外解释|理解')
    elif rid == 'MS-DEP-01':
        if _affirmed(text, r'avoid\w*.{0,35}(?:extra|optional).{0,50}(?:effort|reward)'): return 1
        if _has(text, r'(?:extra|additional|incremental).{0,35}(?:uncertain|speculative).{0,35}(?:reward|effort)|extra\s+uncertain\s+reward\s+effort'):
            return -1
        pattern = r'avoid\w*.{0,35}(?:extra|optional).{0,50}(?:effort|reward)'
    elif rid == 'MS-COMPASSION-01':
        pattern = r'empathet|caring\s+(?:support|assistance)|同理|关怀' if outcome == 'modeled_empathetic_care' else r'(?:need|difficulty|distress).{0,30}reliev|relief.{0,45}(?:need|difficulty)|困难.{0,8}缓解'
    elif rid == 'MS-SOC-01':
        guard = rule.get('required_semantic_evidence', {})
        return 1 if contact_quality_matches(text, guard) else 0
    elif rid == 'MS-CI-01': pattern = r'(?:additional|alternative|multiple).{0,45}(?:possibilit|concept|ideas)|额外构思|备选概念'
    elif rid == 'MS-RES-01': pattern = r'(?:own|personal|accepted).{0,35}(?:promis\w*|commit\w*|obligation)|promised\s+(?:obligation|commitment)|本人.{0,8}承诺'
    if not pattern or not _has(text, pattern): return 0
    return 1 if _affirmed(text, pattern) else -1


def _quality_effects(graph, quality, left, right, region):
    """Independent finite local projection for guaranteed selected scope nodes.

    None is returned for crossing contribution sources or branch-dependent
    attainment. Original global truth is deliberately outside this certificate.
    """
    used = []; projected = []; mixed = []
    def quality_value(identity, selected, seen):
        if identity in seen: return None
        positives = []; negatives = []
        for i, edge in enumerate(graph.model.get('contributions', [])):
            if edge['target'] != identity: continue
            leaves = graph.leaves(edge['source'])
            if not leaves & region: continue
            if not leaves <= region:
                mixed.append({'index': i, 'edge': deepcopy(edge)}); return None
            if edge['source'] in selected:
                value = True
            elif not graph.region(edge['source']) & selected:
                value = False
            else:
                value = None
            record = {'index': i, 'edge': deepcopy(edge)}
            if record not in used: used.append(record)
            (positives if edge['type'] == 'makes' else negatives).append(value)
        ref = graph.refs.get(identity)
        if ref:
            projected.append(deepcopy(ref))
            vals = [quality_value(c, selected, seen | {identity}) for c in ref['children']]
            if ref['kind'] == 'AND': child = False if False in vals else None if None in vals else True
            else: child = True if True in vals else None if None in vals else False
            positives.append(child)
        if True in negatives: return False
        if None in negatives: return None
        return True if True in positives else None if None in positives else False
    a = quality_value(quality, left, set()); b = quality_value(quality, right, set())
    return {'quality_id': quality, 'preferred': a, 'other': b, 'original_contributions': used,
            'projected_quality_refinements': projected, 'mixed_sources': mixed,
            'scope': 'Original decision-local contribution criterion; not original global quality truth.'}


def _trust_handling_state(text):
    """Keep handling independence separate from independent verification.

    In "joint check with an independently verified colleague", the adverb
    modifies the verification, not the actor's handling of the check. An own
    "check independently" assertion still establishes independent handling.
    Reading a cooperation document is not a performed cooperative action.
    """
    if _has(text, r'\b(?:if|unless|when|pending|provided|conditional\w*|may|might)\b|'
                  r'\b(?:subject to|only after|after approval|before approval)\b|仅当|除非|或许'):
        return 'unknown'
    verification = r'(?:verified|authenticated|validated|authorized|approved|identified|reviewed)'
    handling = re.sub(r'\bindependently\s+(?=' + verification + r'\b)', '', text)
    handling = re.sub(r'\b(' + verification + r')\s+independently\b', r'\1', handling)
    if _affirmed(handling, r'\b(?:independently|alone|independent\s+handling|declin\w*\s+cooperat)\b|独立处理|单独'):
        return 'absent'
    # Cooperation words inside an object (manual, agreement, lecture topic,
    # quoted action title) do not establish a performed cooperative action.
    handling = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', ' ', handling)
    action = r'(?:check|handle|process|compare|review|inspect|prepare|verify|work|perform|conduct|complete)'
    modifiers = r'(?:jointly|together|cooperatively)'
    joint_operation = (r'^(?:perform|conduct|complete|undertake|do|carry\s+out)\s+'
                       r'(?:(?:a|an|the|same|bounded|authorized|approved|permitted|public|nonsensitive)\s+){0,6}'
                       r'(?:joint|cooperative)\s+(?:check|handling|review|inspection|comparison|processing|work)\b'
                       r'(?!\s+(?:manual|guide|agreement|proposal|lecture|course|training|instructions?|documentation)\b)')
    for clause in re.split(r';\s*|\.\s+|\band\s+', handling):
        clause = clause.strip()
        if not clause: continue
        performed = (re.match(r'^(?:co[- ]?handle(?:s|d)?|cooperat(?:e|es|ed|ing))\b', clause)
                     or re.match(joint_operation, clause)
                     or re.match(r'^' + modifiers + r'\s+' + action + r'\b', clause)
                     or re.match(r'^' + action + r'\s+' + modifiers + r'\b', clause)
                     or (re.match(r'^' + action + r'\b', clause)
                         and re.search(r'\b' + modifiers + r'(?=\s*(?:$|with\b|within\b|using\b))', clause)
                         and not _has(clause, r'\b(?:about|regarding|concerning|how to|instructions? for|steps? to)\b'))
                     or re.match(r'^(?:共同|合作)(?:处理|核对|检查|审阅|完成|比较|准备|执行)', clause))
        if performed and _affirmed(clause, r'co[- ]?handl|cooperat|joint\w*|\btogether\b|共同|合作'):
            return 'present'
    return 'unknown'


def _care_beneficiary_evidence(graph, rule, outcome, decision, source, target, left_ids, right_ids):
    """Bind human references to the compared care opportunity, not ancestors.

    A person mentioned in unrelated root prose cannot supply the beneficiary
    of a care quality about a device. Preserve original field quotations and
    only use care/relief clauses on compared nodes, their actual decision, or
    an original care quality receiving a contribution from this comparison.
    """
    relevant = set(left_ids) | set(right_ids)
    scope = decision.get('node_id')
    if scope in graph.nodes: relevant.add(scope)
    contribution_region = graph.region(source) | graph.region(target)
    for edge in graph.model.get('contributions', []):
        quality = edge.get('target')
        if (edge.get('source') in contribution_region and quality in graph.nodes
                and graph.kind(quality) in QUALITY
                and _quality_sign(rule, outcome, graph.node_text(quality)) == 1):
            relevant.add(quality)
    determiner = r'(?:(?:the|a|an)\s+)?'
    modifiers = r'(?:(?:same|identified|named|specified|verified|known|waiting|unbadged|unfamiliar|affected|registered|other|new)\s+){0,3}'
    human = (determiner + modifiers
             + r'(?:clients?|beneficiar\w*|colleagues?|peers?|attendees?|visitors?|patrons?|customers?|callers?|persons?|individuals?)\b')
    # These are beneficiary links, not a bag of human and care words. In
    # particular, "person reviewed an unrelated help manual" has no link.
    care_noun = r'(?:care|support|assistance|help|relief|reassurance)'
    care_verb = r'(?:(?:is|was|being|expressed|provided|offered|given|delivered|aimed|directed|shown|supplied)\s+){0,4}'
    direct_link = (r'\b' + care_noun + r'\s+' + care_verb + r'(?:for|to|toward|towards)\s+' + human
                   + r'|\b(?:assist|assists|assisted|help|helps|helped|relieve|relieves|relieved)\s+' + human
                   + r'|\backnowledge\s+' + human + r"(?:'s)?\s+(?:(?:reported|modeled|concrete|specific|current|access)\s+){0,3}(?:difficulty|need|distress|confusion)\b"
                   + r'|(?:帮助|安慰|关怀|照顾|支持|缓解|减轻).{0,8}(?:同事|客户|来电者|访客|该人员|同一个人)')
    evidence = []
    for identity in sorted(relevant):
        node = graph.nodes[identity]
        for field in ('label', 'description', 'meaning'):
            value = node.get(field)
            if not isinstance(value, str): continue
            # Quoted titles/actions are artifact mentions, not performed care
            # or a beneficiary attribution. Keep the original field as proof.
            scan = value.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
            scan = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', ' ', scan)
            clauses = re.split(r'[.;。；]', _text(scan))
            grounded = []
            for clause in clauses:
                artifact = _has(clause, r'\b(?:manual|guide|document|agreement|lecture|course|instructions?|documentation)\b')
                if artifact and not re.match(
                        r'^\s*(?:(?:assist|help|relieve|provide|offer|give|express|deliver|acknowledge)\b|'
                        r'(?:(?:explicit|additional|modeled|empathetic|caring)\s+)*(?:care|support|assistance)\b)', clause):
                    continue
                grounded.append(clause)
            if any(_affirmed(clause, direct_link) for clause in grounded):
                evidence.append({'node_id': identity, 'field': field, 'quote': value,
                                 'purpose': 'original_care_beneficiary'})
    return evidence


def _classify(rule, outcome, text, context='', quality=False):
    """Three-valued direct opportunity grammar: present / absent / unknown."""
    rid = rule['id']; t = text
    if not t: return 'absent'
    if rid == 'MS-ORG-01':
        kind, _ = _organization_action(t)
        return {'positive': 'present', 'baseline': 'absent', 'not_action': 'absent'}.get(kind, 'unknown')
    if rid == 'MS-ASSERT-01':
        if _has(t, r'without\s+(?:stating|expressing)|without\s+(?:an?\s+)?own\s+position|passively\s+accept|^(?:accept|record)\b'):
            return 'absent'
        if _affirmed(t, r'\b(?:state|express|propose|speak\w*|offer|set)\b') and _has(t, r'own|alternative|feasible|permissible|boundar|propos|个人|替代|边界'):
            return 'present'
    elif rid == 'MS-ENERGY-01':
        if _affirmed(t, r'\b(?:seated|sedentary|stationary|desk.based|physically\s+passive|desk\s+(?:briefing|assessment|review|checklist|service))\b|坐席'): return 'absent'
        if _affirmed(t, r'\b(?:walk\w*|walkthrough|physically\s+active|physical\s+(?:activity|involvement)|on.foot)\b|步行|走动'):
            return 'present'
    elif rid == 'MS-RESPECT-01':
        if _has(t, r'self.retaining|personal\s+share|retain.{0,35}(?:surplus|token)|less\s+expression|本人份额|保留.{0,8}剩余'): return 'absent'
        if _has(t, r'allocat|sharing|分配') and _affirmed(t, r'consider\w*|accepted.{0,30}(?:share|norm)|(?:other\s+party|counterpart).{0,40}(?:claim|need|contribution)|份额|主张'):
            return 'present'
    elif rid == 'MS-TRUST-01':
        return _trust_handling_state(t)
    elif rid == 'MS-ANX-01':
        if _has(t, r'wait\w*.{0,55}(?:normal|ordinary|later)|等待.{0,12}(?:正常|稍后|普通)'): return 'absent'
        # Receiving an explicitly ordinary later notice is a knowledge-timing
        # channel too. Do not require the implementation's action to be Wait.
        if (_has(t, r'^(?:receive|read|obtain|learn)\b')
                and _has(t, r'\b(?:ordinary|normal|scheduled)\s+later\s+(?:notice|notification|update)\b')
                and not _has(t, r'\b(?:early|earlier|preview|if|unless|when|provided|pending|may|might|conditional\w*|'
                                r'about|regarding|concerning|titled|named|called|training|guide|manual|document|example|sentence|text)\b|'
                                r'\b(?:learn\s+to|how\s+to|instructions?\s+for|steps?\s+to|only\s+after|after\s+approval|before\s+approval|subject\s+to)\b|["\']')):
            return 'absent'
        if _affirmed(t, r'earl\w*|preview|提前|早知') and _affirmed(t, r'accurate|准确'):
            return 'present'
    elif rid == 'MS-VOL-01':
        if _has(t, r'neutral\s+factual|cooling.off|中性事实|冷静'): return 'absent'
        if _affirmed(t, r'reactive|blame.focused|责备|归责') and _has(t, r'respon|reply|expression|correction|回应|表达'):
            return 'present'
    elif rid == 'MS-AS-01':
        if _has(t, r'(?:decorative|plain).{0,25}(?:software|toolbar|interface)|without.{0,40}(?:artistic|art|appreciation)|仅.{0,8}软件装饰'): return 'absent'
        content = _has(t + ' ' + context, r'artwork|artistic|\bpainting\b|\bmural\b|\bsculpture\b|\bpoem\b|\bmusic\b|literary|color\s+and\s+form|艺术|画作|音乐|壁画')
        if content and _affirmed(t, r'appreciat|sustain|\bview\b|\binspect\b|\blisten\b|\bstudy\b|欣赏|细看|聆听'): return 'present'
    elif rid == 'MS-IC-01':
        if outcome == 'new_question_generation':
            if _has(t, r'without.{0,55}(?:formulat|generat|new\s+question)|existing\s+answered|reuse.{0,30}(?:question|list)'): return 'absent'
            if _affirmed(t, r'formulat|generat|\brecord\b|提出|记录') and _affirmed(t, r'unanswered|not.yet.answered|meaningful\s+new|new\s+unanswered|new.{0,18}questions|未回答|新问题'):
                return 'present'
            if _has(t, r'q.and.a|q&a|question.and.answer|questions\s+and\s+answers'): return 'absent'
        else:
            if _has(t, r'without.{0,55}(?:additional|explanation)|(?:only|same\s+required).{0,20}(?:summary|caption)'): return 'absent'
            if _affirmed(t, r'explanation|explanatory|additional\s+(?:knowledge|learning)|understand|detailed.{0,30}(?:note|material)|解释|理解'):
                return 'present'
    elif rid == 'MS-DEP-01':
        effort = _affirmed(t, r'extra\s+effort|effortful|additional\s+effort|额外努力')
        reward = _has(t, r'uncertain.{0,35}(?:reward|engagement|recognition|bonus|benefit)|不确定.{0,10}(?:奖励|回报)')
        if effort and reward: return 'absent'
        if _has(t, r'sufficient\s+standard|adequate\s+standard|standard\s+(?:work|delivery)|without.{0,35}extra\s+effort|充分.{0,6}标准'):
            return 'present'
    elif rid == 'MS-COMPASSION-01':
        if _has(t, r'without.{0,60}(?:relief|relieve|caring)|impersonal|standard\s+(?:help\s+sheet|guide|receipt)|standard\s+map'): return 'absent'
        if outcome == 'modeled_need_relief':
            if _has(t, r'\b(?:assist|help|reliev|explanation)\w*') and _has(t, r'need|difficult|distress|困难|需要'): return 'present'
        elif _affirmed(t, r'empathet|caring\s+(?:support|assistance)|同理|关怀'): return 'present'
    elif rid == 'MS-RES-01':
        if _affirmed(t, r'promis\w*|commit\w*|accepted\s+obligation|承诺|认可义务'): return 'present'
        return 'absent'
    elif rid == 'MS-SOC-01':
        guard = rule.get('required_semantic_evidence', {})
        return contact_task_semantics(t, guard)['effect']
    elif rid == 'MS-CI-01':
        if _affirmed(t, r'generat\w*|imagin\w*|brainstorm\w*|构思|生成') and _has(t, r'ideas|concepts|possibilit|alternative|构思|概念|备选'): return 'present'
        if _has(t, r'qualified\s+baseline|without.{0,25}(?:ideation|generation)|既有合格'): return 'absent'
    return 'unknown'


def _scope_effect(graph, rule, outcome, scope, implementation=None):
    ids = graph.must(scope, implementation)
    evidence = []
    states = []
    for node in sorted(ids):
        if graph.kind(node) != 'task': continue
        state = _classify(rule, outcome, graph.node_text(node), graph.original_text(ids))
        states.append(state)
        if state != 'unknown': evidence.append(node)
    # Original achieved goal semantics can express an explanation supplied by
    # every implementation. Mere 'choose ... option' labels cannot do so.
    if rule['id'] == 'MS-IC-01' and outcome == 'explanatory_understanding':
        for node in ids:
            if graph.kind(node) == 'goal' and _has(graph.node_text(node), r'(?:explanation|understanding|knowledge).{0,30}(?:obtained|gained|achieved)|^understand\b'):
                states.append('present'); evidence.append(node)
    if 'present' in states: return 'present', evidence, ids
    if rule['id'] == 'MS-DEP-01' and graph.kind(scope) == 'goal':
        # A requirement on participation in this original scope applies to
        # every admitted realization; neutral review/submission leaves do not
        # erase its explicitly required effort increment. Arbitrary ancestor
        # prose and merely naming an optional reward are insufficient.
        fields = []
        for field in ('label', 'description', 'meaning'):
            value = graph.nodes[scope].get(field)
            if not isinstance(value, str): continue
            value = _text(value)
            if _has(value, r'\b(?:titled|example|sentence|training|instruction\w*|must\s+(?:output|write|say)|prompt|hypothetical)\b'):
                continue
            value = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', ' ', value)
            fields.append(value)
        text = ' ; '.join(fields)
        requirement = r'^participation\s+(?:requires|entails|involves)\s+(?:extra|additional)\b.{0,40}\beffort\b'
        required_effort = any(_affirmed(clause.strip(), requirement) for value in fields
                              for clause in re.split(r'[.;]', value))
        uncertain_reward = _affirmed(text, r'\buncertain\b.{0,40}\breward\b|\breward\b.{0,20}\bis\s+uncertain\b')
        certain_reward = _affirmed(text, r'\b(?:guaranteed|certain|assured)\s+(?:incremental\s+)?reward\b|\breward\b.{0,20}\bis\s+(?:guaranteed|certain|assured)\b')
        denied_pursuit = _has(text, r'\b(?:no|not|never|without)\b.{0,25}\b(?:additional|extra|incremental)\s+reward\b.{0,25}\b(?:pursu\w*|sought|seek\w*)\b')
        document_purpose = _has(text, r'\beffort\s+to\s+(?:read|study|review|learn)\b.{0,45}\b(?:article|manual|guide|document|note)\b')
        conditional = _has(text, r'\b(?:if|unless|may|might|could|conditional\w*|depending)\b')
        if required_effort and uncertain_reward and not (certain_reward or denied_pursuit or document_purpose or conditional):
            return 'absent', sorted(set(evidence + [scope])), ids
    if rule['id'] == 'MS-SOC-01':
        guard = rule.get('required_semantic_evidence', {})
        if scope_noncontact_evidence(graph.model, scope, guard):
            return 'absent', [scope], ids
        # Guaranteed negative leaves do not prove the absence of an optional
        # or alternate reciprocal-contact activity inside the same scope.
        if not direct_solitary_evidence(graph.model, scope, guard):
            return 'unknown', evidence, ids
    if states and all(s == 'absent' for s in states): return 'absent', evidence, ids
    return 'unknown', evidence, ids


def _predicate(identity, ok, evidence, code=None):
    return {'id': identity, 'status': 'satisfied' if ok is True else 'contradicted' if ok is False else 'unknown',
            'evidence': evidence, 'code': code or identity}


def _requirements(graph, persona, rule, outcome, decision, source, target, left_ids, right_ids):
    rid = rule['id']; context_ids = graph.context(decision, source, target)
    dependency_evidence = graph.dependency_evidence(graph.region(source) | graph.region(target))
    context = graph.original_text(context_ids | left_ids | right_ids) + ' ; ' + ' ; '.join(_text(e['quote']) for e in dependency_evidence)
    rows = []; evidence = graph.evidence(context_ids, 'original_context') + dependency_evidence
    if rid == 'MS-ASSERT-01':
        forbidden = _has(context, r'non.negotiable|not\s+negotiable|fixed\s+(?:nonnegotiable|mandatory)\s+arrangement|不可协商')
        negotiable = _affirmed(context, r'negotiable|可协商') or (_has(graph.original_text(left_ids), r'propose|alternative|feasible|own\s+(?:position|window)|自我表达|替代') and _has(graph.original_text(right_ids), r'accept|offered|original|standard\s+arrangement|接受'))
        rows.append(_predicate('negotiable_arrangement', False if forbidden else True if negotiable else None, evidence))
    elif rid == 'MS-RESPECT-01':
        allocation = _affirmed(context, r'allocat|share|claim|contribution|token|分配|份额|主张')
        invalid = _has(context, r'violat\w*.{0,25}(?:mandatory\s+rights|fairness)|unverified\s+entitlement|侵犯.{0,8}权利')
        rows.append(_predicate('modeled_interpersonal_allocation', False if invalid else True if allocation else None, evidence))
    elif rid == 'MS-TRUST-01':
        conflict = _affirmed(context, r'conflicting\s+identit|identity\s+conflict|failed\s+(?:identity\s+)?verification|adverse\s+evidence|unresolved\s+(?:modeled\s+)?risk|身份冲突|验证失败')
        bounded = _has(context, r'bounded|\bpublic\b|verified\s+(?:helper|colleague|partner)|authorized|existing\s+access\s+scope|checked\s+boundar|有界|公开|已验证|授权')
        bypass = _affirmed(context, r'(?:skip|omit|bypass|drop).{0,35}(?:required\s+)?(?:verification|authentication|authorization|safeguard)|绕过.{0,10}(?:验证|授权)')
        rows += [_predicate('no_explicit_identity_or_risk_conflict', not conflict, evidence),
                 _predicate('bounded_cooperation_same_original_safeguards', False if bypass else True if bounded else None, evidence)]
    elif rid == 'MS-ANX-01':
        a = graph.original_text(left_ids); b = graph.original_text(right_ids)
        changes = _affirmed(context, r'change\w*.{0,30}(?:business\s+)?decision\s+from\s+result|actionable\s+(?:safety|verification|research)|改变.{0,8}决定')
        noninstrumental = _has(context, r'noninstrumental|without\s+changing|unchanged|same\s+fixed\s+outcome|非工具|不改变|同一固定结果')
        knowledge_pair = (_has(a, r'(?:obtain|read|learn).{0,40}(?:early|preview)') and _has(b, r'wait\w*.{0,45}(?:normal|ordinary|later)')
                          and _has(a, r'result|feedback|outcome') and _has(b, r'result|feedback|outcome'))
        rows.append(_predicate('same_eventual_outcome_noninstrumental_knowledge', False if changes else True if noninstrumental or knowledge_pair else None, evidence))
    elif rid == 'MS-VOL-01':
        provocation = _affirmed(context, r'provocation|provok\w*|挑衅') and _affirmed(context, r'attribut\w*|interpersonal|counterpart|人际|归因')
        explicitly_absent = _has(context, r'without.{0,40}(?:attributed\s+)?(?:interpersonal\s+)?provocation|no\s+(?:attributed\s+)?provocation')
        rows.append(_predicate('explicit_attributed_interpersonal_provocation', False if explicitly_absent else True if provocation else None, evidence))
    elif rid == 'MS-COMPASSION-01':
        beneficiary = _care_beneficiary_evidence(graph, rule, outcome, decision, source, target, left_ids, right_ids)
        rows.append(_predicate('identified_modeled_beneficiary', True if beneficiary else None, beneficiary))
    elif rid == 'MS-CI-01':
        generators = [i for i in left_ids if graph.kind(i) == 'task' and _classify(rule, outcome, graph.node_text(i)) == 'present']
        active = (graph.model.get('_active_role') or '')
        reviewers = [i for i in left_ids if graph.kind(i) == 'task' and _has(graph.node_text(i), r'review|screen|审核')
                     and not _has(graph.node_text(i), r'own\s+concepts|same\s+generating\s+persona|self.review|本人自审')]
        independent = [i for i in reviewers if _has(graph.node_text(i), r'independent|独立')]
        openness = any(_has(graph.node_text(i), r'alternative|additional.{0,30}(?:ideas|concepts|possibilit)|multiple|open\s+problem|备选|多种|额外') for i in generators)
        rows += [_predicate('admissible_possibility_generation', True if generators and openness else None, graph.evidence(generators, 'ideation')),
                 _predicate('existing_independent_review_retained', True if independent else None, graph.evidence(reviewers, 'review'))]
    if rid in {'MS-RES-01', 'MS-ASSERT-01', 'MS-ENERGY-01', 'MS-CI-01', 'MS-SOC-01'}:
        active = (persona.get('role_ids') or [None])[0]
        positive = [n for n in left_ids if graph.kind(n) in BUSINESS and _classify(rule, outcome, graph.node_text(n), context) == 'present']
        # An explicit own commitment at a goal may belong to the active role
        # while execution is delegated. Ordinary goal ownership is not such a
        # premise. Other personal actions need an original active-role task.
        eligible = [n for n in positive if graph.kind(n) == 'task' or rid == 'MS-RES-01']
        own = [n for n in eligible if graph.nodes[n].get('role') == active]
        explicit_other = []
        if rid == 'MS-RES-01':
            other_roles = [r for r in graph.model.get('roles', {}) if r != active]
            for n in own:
                text = graph.node_text(n)
                if any(_has(text, r'\b' + re.escape(str(r).lower()) + r'(?:[\'’]s)?\s+(?:own|personal|promis\w*|commit\w*)\b') for r in other_roles):
                    explicit_other.append(n)
            own = [n for n in own if n not in explicit_other]
        quality_carriers = []
        region = graph.leaves(source) | graph.leaves(target)
        for q in graph.nodes:
            if graph.kind(q) not in QUALITY or graph.nodes[q].get('role') != active: continue
            if _quality_sign(rule, outcome, graph.node_text(q)) != 1: continue
            effects = _quality_effects(graph, q, left_ids, right_ids, region)
            if effects['preferred'] is not True: continue
            for item in effects['original_contributions']:
                origin = item['edge']['source']
                carrier_kind = graph.kind(origin)
                # SOC explicitly permits a role-owned original reciprocal-
                # participation quality to establish that role's interaction
                # opportunity for a composite implementation. This is stronger
                # than merely owning a decision or a collaboration-branded goal.
                role_participation_goal = rid == 'MS-SOC-01' and carrier_kind == 'goal'
                if (item['edge']['type'] == 'makes' and origin in left_ids and (carrier_kind == 'task' or role_participation_goal)
                        and graph.nodes[origin].get('role') == active and origin not in explicit_other):
                    quality_carriers.append(origin)
        actor_proof = own or quality_carriers
        identity = 'own_commitment_attribution' if rid == 'MS-RES-01' else 'persona_action_role_attribution'
        rows.append(_predicate(identity, True if actor_proof else False if eligible or explicit_other else None,
                               graph.evidence(actor_proof or eligible, 'personal_actor_attribution')))
    return rows, context_ids


def check_semantic_contract(model, persona, rule, decision, proposal, *, witness_pair=None, quality_check=None, view=None):
    """Inspect an original-model binding and return a JSON-safe certificate.

    ``witness_pair``/``quality_check`` may be retained by callers alongside this
    certificate; no supplied boolean is used to overwrite original semantics.
    This function does not authorize endpoints or assert plan feasibility.
    """
    return _check(_Graph(model), persona, rule, decision, proposal)


def _check(graph, persona, rule, decision, proposal):
    source, target = proposal.get('source'), proposal.get('target')
    outcome = proposal.get('contrast', {}).get('outcome_id')
    result = {'version': VERSION, 'rule_id': rule.get('id'), 'outcome_id': outcome,
              'status': 'insufficient', 'supported': False, 'predicates': [], 'evidence': [], 'quality_certificates': [],
              'boundary': 'Original semantic opportunity only; caller must retain independent persona evidence, decision authority, hard constraints and complete-plan checks.'}
    if source not in graph.nodes or target not in graph.nodes:
        result['reason'] = 'Unknown original endpoint.'; return result
    if outcome not in {r['id'] for r in rule.get('semantic_outcomes', [])}:
        result.update(status='contradicted', reason='Outcome is outside the fixed rule domain.'); return result
    counter = validated_persona_counterevidence(persona, rule, persona.get('description', ''), graph.model, proposal)
    if counter:
        result.update(status='contradicted', reason='Literal original persona counterevidence defeats this proposed opportunity.',
                      persona_counterevidence=counter)
        return result
    if rule['id'] == 'MS-ORG-01' and explicit_persona_counterevidence(persona.get('description', '')):
        result.update(status='contradicted', reason='Explicit original persona counterevidence defeats this organization direction.'); return result
    if decision['kind'] == 'temporal':
        source_context = graph.region(source) | {n for n in graph.ancestors(source) if not graph.leaves(target) <= graph.leaves(n)}
        work = graph.original_text(source_context); diversion = graph.original_text(graph.region(target))
        started = _affirmed(work, r'\b(?:started|remaining|in.progress|under.way)\b|已开始|剩余')
        nonurgent = _affirmed(diversion, r'nonurgent|non.urgent|deferr\w*|diversion|distraction|非紧急|可推迟')
        discretion = graph.nodes[target].get('optional') or _affirmed(diversion, r'discretionary|diversion|distraction|自选|分心')
        proper = rule['id'] == 'MS-PRO-01' and proposal.get('formula') == 'precedes' and source != target
        predicates = [_predicate('original_started_or_remaining_unit', bool(started), graph.evidence(source_context, 'current_work')),
                      _predicate('nonurgent_discretionary_diversion', bool(nonurgent and discretion), graph.evidence(graph.region(target), 'diversion'))]
        supported = proper and all(p['status'] == 'satisfied' for p in predicates)
        result.update(status='supported' if supported else 'contradicted', supported=supported, predicates=predicates,
                      evidence=[e for p in predicates for e in p['evidence']],
                      reason='Original continuity template guards established; caller must prove both complete orders.' if supported else 'Original continuity guards or direction are absent.')
        return result
    optional = decision['kind'] == 'optional_participation'
    pairs = []
    implementations = graph.implementations(source) if optional else [None]
    for implementation in implementations:
        a, ae, ai = _scope_effect(graph, rule, outcome, source, implementation)
        if optional:
            bi, be = set(), []
            # Omission removes only this additional opportunity, not required work.
            bstate = 'present' if rule['id'] == 'MS-DEP-01' else 'absent'
        else:
            bstate, be, bi = _scope_effect(graph, rule, outcome, target)
        if not optional and rule['id'] == 'MS-IC-01' and outcome == 'explanatory_understanding':
            topic = decision.get('node_id')
            if topic in graph.nodes and _has(graph.node_text(topic), r'(?:explanation|understanding|knowledge).{0,30}(?:obtained|gained|achieved)|^understand\b'):
                # Every original OR implementation realizes this named result;
                # an interaction format is not a further learning difference.
                a = bstate = 'present'; ae.append(topic); be.append(topic)
        if optional and proposal.get('formula') == 'never':
            a, bstate, ai, bi, ae, be = bstate, a, bi, ai, be, ae
        predicates, context_ids = _requirements(graph, persona, rule, outcome, decision, source, target, ai, bi)
        if rule['id'] == 'MS-ORG-01' and not optional:
            left_actions = [_organization_action(graph.node_text(i)) for i in ai if graph.kind(i) == 'task']
            right_actions = [_organization_action(graph.node_text(i)) for i in bi if graph.kind(i) == 'task']
            left_materials = [words for kind, words in left_actions if kind == 'positive']
            right_materials = [words for kind, words in right_actions if kind in {'positive', 'baseline'}]
            material = next((common for x in left_materials for y in right_materials
                             if (common := _same_material(x, y, graph.original_text([decision['node_id'], *graph.ancestors(decision['node_id'])])))), None)
            if left_materials and right_materials:
                predicates.append(_predicate('same_original_material_object', bool(material), graph.evidence(ae + be + [decision['node_id']], 'material_object')))
        region = graph.leaves(source) | graph.leaves(target)
        quality_rows = []
        for q, n in graph.nodes.items():
            if graph.kind(q) not in QUALITY: continue
            sign = _quality_sign(rule, outcome, graph.node_text(q))
            if not sign: continue
            cert = _quality_effects(graph, q, ai, bi, region)
            if not cert['original_contributions']: continue
            cert['semantic_polarity'] = 'positive' if sign == 1 else 'negative'
            cert['outcome_effects'] = {'preferred': (cert['preferred'] if sign == 1 else not cert['preferred']) if cert['preferred'] is not None else None,
                                       'other': (cert['other'] if sign == 1 else not cert['other']) if cert['other'] is not None else None}
            quality_rows.append(cert)
        for side, selected in (('preferred', ai), ('other', bi)):
            values = {q['outcome_effects'][side] for q in quality_rows if q['outcome_effects'][side] is not None}
            scoped_break = any(q[side] is False and q['semantic_polarity'] == 'positive'
                               and any(e['edge']['type'] == 'breaks' and e['edge']['source'] in selected for e in q['original_contributions'])
                               for q in quality_rows)
            # A scoped active break is a veto, even when a task label sounds
            # favorable or another makes fires. Outside breaks never enter the
            # local projection and remain the caller's separate global report.
            state = 'absent' if scoped_break else ('present' if values == {True} else 'absent' if values == {False} else None)
            if len(values) > 1 and not scoped_break:
                predicates.append(_predicate('consistent_same_outcome_quality_effects', None, graph.evidence([q['quality_id'] for q in quality_rows], 'quality_semantics')))
            if state is not None:
                if side == 'preferred': a = state
                else: bstate = state
        if optional and rule['id'] == 'MS-DEP-01' and proposal.get('formula') == 'never':
            # The include activity must really be extra effort for uncertainty,
            # not an arbitrary optional task labeled as incentive avoidance.
            include_text = graph.original_text(graph.must(source, implementation))
            valid_increment = _has(include_text, r'(?:extra|additional|effortful).{0,40}(?:effort|uncertain)|额外努力') and _has(include_text, r'uncertain.{0,35}(?:reward|engagement|recognition|benefit)|不确定.{0,10}奖励')
            predicates.append(_predicate('optional_uncertain_reward_effort_increment', True if valid_increment else None, graph.evidence(graph.must(source, implementation), 'effort_reward')))
        statuses = [p['status'] for p in predicates]
        conflict = 'contradicted' in statuses or bstate == 'present' or a == 'absent'
        supported = not conflict and 'unknown' not in statuses and a == 'present' and bstate == 'absent'
        row = {'implementation_id': implementation or source, 'source_outcome': a, 'target_outcome': bstate,
               'status': 'supported' if supported else 'contradicted' if conflict else 'insufficient',
               'predicates': predicates, 'evidence': graph.evidence(ae, 'preferred_outcome') + graph.evidence(be, 'other_outcome') + graph.evidence(context_ids, 'relevant_context') + graph.dependency_evidence(graph.region(source) | graph.region(target)),
               'quality_certificates': quality_rows}
        pairs.append(row)
    result['implementations'] = pairs
    result['predicates'] = [p for x in pairs for p in x['predicates']]
    result['evidence'] = [p for x in pairs for p in x['evidence']]
    result['quality_certificates'] = [p for x in pairs for p in x['quality_certificates']]
    result['status'] = ('supported' if pairs and all(x['status'] == 'supported' for x in pairs)
                        else 'contradicted' if any(x['status'] == 'contradicted' for x in pairs) else 'insufficient')
    result['supported'] = result['status'] == 'supported'
    result['reason'] = {'supported': 'Original semantics prove one fixed-outcome difference.', 'contradicted': 'Original semantics contradict the proposed difference or a required premise.', 'insufficient': 'Original semantics do not yet prove every required premise and the strict same-outcome difference.'}[result['status']]
    return result


def derive_semantic_bindings(model, persona, decisions, rules):
    """Derive finite positive bindings; caller must fresh-check all witnesses.

    Return shape follows the existing canonical binding compiler. Each binding
    has independent literal persona evidence and an original-model certificate.
    No decision, node, contribution, quality or hard relation is invented.
    """
    graph = _Graph(model); bindings = []
    for decision_id, decision in decisions.items():
        kind = decision['kind']
        endpoints = decision['endpoints']
        for rule in rules.values():
            if kind not in rule.get('allowed_kinds', []): continue
            pe = persona_evidence(persona, rule)
            if not pe['supported']: continue
            for outcome in rule.get('semantic_outcomes', []):
                if kind == 'choice': pairs = [(a, z, 'preferred_to') for a in endpoints for z in endpoints if a != z]
                elif kind == 'temporal':
                    # Normalize remaining leaf work to its explicitly started
                    # original work-unit goal, rather than emitting every part.
                    units = [i for i in endpoints if _affirmed(graph.node_text(i), r'\b(?:started|remaining|in.progress|under.way)\b|已开始|剩余')]
                    units = [i for i in units if not any(a in units and graph.kind(a) == 'goal' for a in graph.ancestors(i))]
                    diversions = [i for i in endpoints if graph.kind(i) == 'task' and _affirmed(graph.node_text(i), r'nonurgent|non.urgent|deferr\w*|diversion|distraction|非紧急|可推迟')]
                    pairs = [(a, z, 'precedes') for a in units for z in diversions if a != z and z not in graph.region(a)]
                else: pairs = [(decision['node_id'], decision['node_id'], f) for f in rule.get('allowed_formulas', ['sometime'])]
                for source, target, formula in pairs:
                    proposal = {'rule_id': rule['id'], 'source': source, 'target': target, 'formula': formula,
                                'model_evidence': [], 'semantic_coverage': {}, 'contrast': {'outcome_id': outcome['id'],
                                'source_effect': 'present', 'target_effect': 'absent', 'criterion_quality_id': '__none__', 'criterion_polarity': 'positive'},
                                'rationale': 'Original-model semantic contract; complete-plan checks remain mandatory.'}
                    cert = _check(graph, persona, rule, decision, proposal)
                    if not cert['supported']: continue
                    evidence = {e['node_id']: {'node_id': e['node_id'], 'quote': model['nodes'][e['node_id']]['label']} for e in cert['evidence'] if e['field'] == 'label' and 'node_id' in e}
                    # Cover the original scalar endpoints even when a quality
                    # effect, rather than their generic labels, proves meaning.
                    for node in (source, target): evidence[node] = {'node_id': node, 'quote': model['nodes'][node]['label']}
                    proposal['model_evidence'] = list(evidence.values())
                    strict_q = next((q for q in cert['quality_certificates'] if q['outcome_effects'] == {'preferred': True, 'other': False}), None)
                    if strict_q:
                        proposal['contrast'].update(criterion_quality_id=strict_q['quality_id'], criterion_polarity=strict_q['semantic_polarity'])
                        q = strict_q['quality_id']; proposal['model_evidence'].append({'node_id': q, 'quote': model['nodes'][q]['label']})
                    if kind == 'optional_participation':
                        for implementation in graph.implementations(source):
                            row = next(x for x in cert['implementations'] if x['implementation_id'] == implementation)
                            candidates = [e for e in row['evidence'] if e['purpose'] == 'preferred_outcome' and e['field'] == 'label' and e['node_id'] in graph.must(source, implementation)]
                            if not candidates:
                                candidates = graph.evidence([source], 'preferred_outcome')
                            chosen = candidates[0]
                            proposal['semantic_coverage'][implementation] = {'supported': True, 'node_id': chosen['node_id'], 'quote': model['nodes'][chosen['node_id']]['label']}
                    bindings.append({'decision_id': decision_id, 'facet': rule['facet'], 'proposal': proposal, 'origin': 'original_model_semantic_contract_compiler',
                                     'anchor_id': rule['id'] + '::' + outcome['id'], 'grammar': VERSION,
                                     'persona_evidence': pe, 'semantic_contract': cert})
    return bindings
