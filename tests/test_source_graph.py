from sources.source_graph import SourceReliabilityGraph


def test_rank_prefers_fallback_target():
    graph = SourceReliabilityGraph(damping=0.85)
    graph.add_node("a")
    graph.add_node("b")

    graph.record_success("b")
    graph.record_fallback("a", "b")

    ranks = graph.compute_ranks()

    assert ranks["b"] > ranks["a"]


def test_sink_handling_returns_normalized():
    graph = SourceReliabilityGraph(damping=0.85)
    graph.add_node("a")
    graph.add_node("b")

    ranks = graph.compute_ranks()
    total = sum(ranks.values())

    assert abs(total - 1.0) < 1e-6
    assert set(ranks.keys()) == {"a", "b"}
