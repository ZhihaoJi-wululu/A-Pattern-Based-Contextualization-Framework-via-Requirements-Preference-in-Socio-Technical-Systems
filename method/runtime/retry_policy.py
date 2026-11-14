"""Bounded P10 transport retry policy based on recorded attempt evidence."""

import json

MAX_ATTEMPTS = 3
RETRY_INTERVAL_SECONDS = 60
AUTHORIZATION_SCOPE = 'approved_new_framework_after_P07'


def retry_decision(audit, *, parsed_response_received, exception, attempt_number=1):
    """Return a hypothetical eligibility decision for one completed attempt.

    ``attempt_number`` counts the current already-used physical attempt: only
    attempts 1 and 2 can be followed by another attempt, after 60 seconds.
    ``parsed_response_received=True`` always refuses retry, including when a
    subsequent schema, citation, semantic or fixed local validation failed.

    ``exception`` must be the actual caught exception, not a saved error string.
    It is used only as failure presence and to exclude explicit JSON/decode
    exception types. It never supplies positive transport eligibility.
    """
    used = attempt_number if type(attempt_number) is int and attempt_number >= 1 else None

    def result(retry, reason, *, event=None, status_code=None):
        return {
            'retry': retry,
            'reason': reason,
            'attempt_number': used,
            'next_attempt': used + 1 if retry else None,
            'delay_seconds': RETRY_INTERVAL_SECONDS if retry else None,
            'max_attempts': MAX_ATTEMPTS,
            'audit_event': event,
            'status_code': status_code,
            'proposal_only': False,
            'authorization_scope': AUTHORIZATION_SCOPE,
        }

    if parsed_response_received is True:
        return result(False, 'parsed_response_received')
    if parsed_response_received is not False:
        return result(False, 'invalid_parsed_response_flag')
    if not isinstance(exception, BaseException):
        return result(False, 'missing_actual_exception')
    if isinstance(exception, (json.JSONDecodeError, UnicodeDecodeError)):
        return result(False, 'parse_or_decode_exception')
    if used is None:
        return result(False, 'invalid_attempt_number')
    if used >= MAX_ATTEMPTS:
        return result(False, 'attempt_limit_reached')
    if not isinstance(audit, (list, tuple)) or any(not isinstance(row, dict) for row in audit):
        return result(False, 'invalid_audit_shape')
    if any(row.get('event') in ('response_bytes', 'response_envelope') for row in audit):
        return result(False, 'successful_response_observed')
    failures = [row for row in audit if row.get('event') in ('http_error', 'network_error')]
    if not failures:
        return result(False, 'no_transport_failure_audit')
    if len(failures) != 1:
        return result(False, 'ambiguous_transport_audit')
    failure = failures[0]
    event = failure['event']
    if event == 'network_error':
        return result(True, 'network_error_audit', event=event)
    status = failure.get('status_code')
    if type(status) is not int:
        return result(False, 'http_status_not_integer', event=event)
    if status in (408, 429) or 500 <= status <= 599:
        return result(True, 'retryable_http_status', event=event, status_code=status)
    return result(False, 'http_status_not_retryable', event=event, status_code=status)
