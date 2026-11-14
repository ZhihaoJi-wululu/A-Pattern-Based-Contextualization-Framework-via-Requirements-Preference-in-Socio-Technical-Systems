"""Approved bounded stage transport coordinator; no networking in this module."""
from retry_policy import retry_decision

MAX_ATTEMPTS = 3
INTER_ATTEMPT_SECONDS = 60

class DispatchStopped(RuntimeError):
    """Another facet stopped dispatch; this is not a framework defect."""

def run_transport_stage(attempt_call, guard, wait):
    """Select the first parsed response, retaining every physical attempt record.

    ``guard`` enforces original clocks/stop state. ``wait`` must remain guarded
    and advances no experiment clock of its own. No response quality is compared.
    ``attempt_call`` returns record/audit/exception/parsed_response_received.
    """
    records=[];decisions=[];selected=None;guard_error=None;guard_error_type=None
    for number in range(1,MAX_ATTEMPTS+1):
        try:guard()
        except Exception as exc:
            guard_error=f'{type(exc).__name__}: {exc}';guard_error_type=type(exc).__name__;break
        outcome=attempt_call(number)
        records.append(outcome['record'])
        if outcome['parsed_response_received']:
            selected=outcome['record'];break
        if outcome['record'].get('framework_failure') or not outcome['record'].get('physical_request_attempted'):
            decisions.append({'after_attempt':number,'retry':False,'reason':'framework_failure_or_no_physical_invocation'})
            break
        decision=retry_decision(outcome['audit'],parsed_response_received=False,
            exception=outcome.get('exception'),attempt_number=number)
        decisions.append({'after_attempt':number,**decision})
        if not decision['retry']:break
        try:
            guard();wait(INTER_ATTEMPT_SECONDS);guard()
        except Exception as exc:
            guard_error=f'{type(exc).__name__}: {exc}';guard_error_type=type(exc).__name__;break
    return {'selected':selected,'attempts':records,'decisions':decisions,'guard_error':guard_error,
        'guard_error_type':guard_error_type,'maximum_attempts':MAX_ATTEMPTS,'interval_seconds':INTER_ATTEMPT_SECONDS}


def stage_transport_status(status, selected, attempts, framework_failure, guard_error_type):
    chosen=selected or (attempts[-1] if attempts else {})
    code=chosen.get('http_status_code') if selected is None else None
    temporary_http=type(code) is int and (code in (408,429) or 500<=code<=599)
    permanent=selected is None and type(code) is int and not temporary_http
    if status=='complete':disposition='recovered' if any(r.get('connection_failure') for r in attempts) else 'complete'
    elif framework_failure:disposition='framework_stop'
    elif permanent:disposition='permanent_http'
    elif guard_error_type=='DispatchStopped':disposition='dispatch_stopped'
    elif selected is not None or any(r.get('successful_response_observed') for r in attempts):disposition='parsed_failure'
    elif any(r.get('connection_failure') for r in attempts):disposition='temporary_exhausted'
    else:disposition='non_transport_failure'
    return {'transport_disposition':disposition,'terminal_http_status':code,
        'permanent_http_failure':permanent,'external_auto_resume_allowed':disposition=='temporary_exhausted'}

def aggregate_transport_status(results):
    rows=list(results)
    statuses=sorted({code for row in rows for code in ([row.get('terminal_http_status')]+row.get('terminal_http_statuses',[])) if type(code) is int})
    permanent=any(row.get('permanent_http_failure') for row in rows)
    dispositions={row.get('transport_disposition') for row in rows}
    priority=('permanent_http','framework_stop','temporary_exhausted','parsed_failure','non_transport_failure','dispatch_stopped','recovered')
    disposition=next((value for value in priority if value in dispositions),'complete')
    return {'transport_disposition':disposition,'terminal_http_statuses':statuses,
        'permanent_http_failure':permanent,
        'external_auto_resume_allowed':disposition=='temporary_exhausted' and not permanent}
