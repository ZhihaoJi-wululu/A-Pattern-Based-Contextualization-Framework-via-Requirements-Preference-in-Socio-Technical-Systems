"""Finite direct-object parsing shared by Organization evidence consumers.

Material identity modifiers remain in the direct object. A simple terminal
classification-key noun phrase belongs to the indexing operation, rather than
to the material being indexed. Complex clauses are deliberately unresolved.
"""
import re

_COMPLEX_KEY = re.compile(
    r'\b(?:if|unless|when|while|before|after|because|provided|pending|may|might|must|'
    r'who|which|that|whose|where|whether|then|but|not|never|without|'
    r'from|to|with|via|through|into|onto|over|under|using|by|according|'
    r'read|reading|reviewing|follow|following|delete|deleting|remove|removing|'
    r'expose|exposing|send|sending|transmit|transmitting|call|calling|'
    r'contact|contacting|invoke|invoking|execute|executing|check|checking)\b')


def organization_direct_object(label):
    """Return original action's material phrase, or None for an unsafe parse.

    This identifies grammatical object/key boundaries only. Callers still check
    the performed action, original OR, same material, equal organization effects,
    persona evidence, original constraints and complete implementation witnesses.
    No material modifier is dropped to force equality with another object.
    """
    text = ' '.join(str(label).lower().split())
    action = re.match(r'^[a-z]+\b\s*(.*)$', text)
    if not action:
        return None
    tail = action[1]
    # An explicit linear-order adjunct is not part of material identity either.
    tail = re.sub(r'\s+in\s+(?:the\s+)?(?:received|arrival|chronological)\s+order\s*$', '', tail)
    boundary = re.search(r'\b(?:by|using|under|according to)(?:\s+|$)', tail)
    if not boundary:
        return tail.strip()
    material, key = tail[:boundary.start()].strip(), tail[boundary.end():].strip()
    words = re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', key)
    if (not words or len(words) > 7 or not re.fullmatch(r'[a-z0-9-]+(?:\s+[a-z0-9-]+)*', key)
            or _COMPLEX_KEY.search(key) or key.startswith('and ') or key.endswith(' and')
            or ' and and ' in key):
        return None
    # Return the full original material phrase. In particular, "source records"
    # and "completion records" stay distinct even when their keys are identical.
    return material
