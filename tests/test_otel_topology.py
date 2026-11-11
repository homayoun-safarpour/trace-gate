"""Graph regressions use synthetic spans and deterministic work-count checks."""
from itertools import product

import pytest

from tracegate.otel import ExportValidationError, SpanEvidence, _topology


def span(identity, parent=None):
    return SpanEvidence(
        trace_id="1" * 32, span_id=identity, parent_span_id=parent,
        start_ns=1, end_ns=2, kind="CHAIN", status="unset",
        input_state="unknown", output_state="unknown",
    )


def chain(size):
    return [span(f"{i:016x}", f"{i - 1:016x}" if i > 1 else None)
            for i in range(1, size + 1)]


@pytest.mark.parametrize("reverse", [False, True])
def test_full_limit_deep_chain_has_no_recursion_or_topology_issue(reverse):
    spans = chain(10000)
    if reverse:
        spans.reverse()
    issues = set()
    _topology(spans, issues)
    assert not issues


@pytest.mark.parametrize("reverse", [False, True])
def test_deep_cycle_is_rejected_without_recursion(reverse):
    spans = chain(10000)
    spans[0].parent_span_id = spans[-1].span_id
    if reverse:
        spans.reverse()
    with pytest.raises(ExportValidationError, match="cyclic span parents"):
        _topology(spans, set())


def test_shared_ancestors_are_not_retraversed():
    class CountingSpan:
        parent_reads = 0

        def __init__(self, identity, parent):
            self.span_id = identity
            self.parent = parent

        @property
        def parent_span_id(self):
            type(self).parent_reads += 1
            return self.parent

    spans = [CountingSpan(f"{i:016x}", f"{i - 1:016x}" if i > 1 else None)
             for i in range(1, 501)]
    issues = set()
    _topology(spans, issues)
    assert not issues
    assert CountingSpan.parent_reads == len(spans)


@pytest.mark.parametrize("spans,expected", [
    ([span("a"), span("b", "a"), span("c", "a")], set()),
    ([span("a"), span("b")], {"incomplete_trace_roots"}),
    ([span("a"), span("b", "missing")], {"missing_parent_span"}),
    ([span("a", "missing"), span("b", "a")],
     {"incomplete_trace_roots", "missing_parent_span"}),
    ([span("A"), span("b", "a"), span("c", "B")], set()),
])
def test_graph_issues_and_case_insensitive_ids_are_preserved(spans, expected):
    issues = {"prior_issue"}
    _topology(spans, issues)
    assert issues == expected | {"prior_issue"}


@pytest.mark.parametrize("spans", [
    [span("a", "a")],
    [span("a", "b"), span("b", "a")],
    [span("root"), span("a", "b"), span("b", "a")],
    [span("root"), span("tail", "A"), span("a", "b"), span("b", "a")],
])
def test_cycles_in_separate_or_shared_components_remain_errors(spans):
    with pytest.raises(ExportValidationError, match="cyclic span parents"):
        _topology(spans, set())


def test_duplicate_normalized_span_ids_remain_errors():
    with pytest.raises(ExportValidationError, match="duplicate span ID"):
        _topology([span("a"), span("A")], set())


def reference_topology(spans):
    """Small exhaustive oracle: independently walk each node's ancestors."""
    parents = {s.span_id.lower(): s.parent_span_id.lower() if s.parent_span_id else None
               for s in spans}
    issues = set()
    if len(parents) != len(spans):
        return "duplicate", issues
    if list(parents.values()).count(None) != 1:
        issues.add("incomplete_trace_roots")
    for start in parents:
        node = start
        path = set()
        while node is not None:
            if node in path:
                return "cycle", issues
            if node not in parents:
                issues.add("missing_parent_span")
                break
            path.add(node)
            node = parents[node]
    return "ok", issues


def test_all_small_parent_graphs_match_reference():
    # 5^3 = 125 graph shapes, including self-cycles and disconnected components.
    for assignment in product([None, "a", "b", "c", "missing"], repeat=3):
        spans = [span(node, parent) for node, parent in zip("abc", assignment, strict=True)]
        expected, expected_issues = reference_topology(spans)
        issues = set()
        if expected == "cycle":
            with pytest.raises(ExportValidationError, match="cyclic span parents"):
                _topology(spans, issues)
        else:
            _topology(spans, issues)
            assert issues == expected_issues
