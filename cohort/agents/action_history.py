"""Researcher-facing action explanations, separate from private model reasoning."""
from __future__ import annotations

from copy import deepcopy


def explained_tools(tools: list[dict]) -> list[dict]:
    result = deepcopy(tools)
    for tool in result:
        schema = tool['function']['parameters']
        schema.setdefault('properties', {})['action_reason'] = {
            'type': 'string', 'minLength': 1,
            'description': 'Briefly explain why you chose this action and these inputs, '
                           'referring to earlier evidence when relevant. A stated purpose, '
                           'not private reasoning or a claim that the choice is correct.',
        }
        schema.setdefault('required', []).append('action_reason')
    return result


def activity_result(result):
    """Keep result metadata needed by the activity view, never bulk excerpts."""
    if not isinstance(result, dict):
        return result if isinstance(result, (str, int, float, bool, type(None))) else None
    keys = ('uid', 'uid_a', 'uid_b', 'nearest_unit_tally', 'longest_shared_run',
            'witnesses', 'passages', 'withheld_extra', 'margin', 'first', 'second',
            'ref', 'start', 'end', 'total_characters', 'returned', 'limit', 'order',
            'id', 'type', 'status', 'authorship', 'created_by')
    summary = {key: result[key] for key in keys if key in result}
    if isinstance(result.get('hits'), list):
        summary['hits'] = [{'ref': h['ref']} for h in result['hits']]
    if 'shown' in result:
        summary['shown'] = [
            {'neighbors': [{'uid': n['uid']} for n in window.get('neighbors', [])]}
            for window in result['shown']
        ]
    return summary
