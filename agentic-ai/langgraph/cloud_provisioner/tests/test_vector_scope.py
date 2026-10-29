"""Tenant-scoped vector search on the HNSW index: a small tenant still gets its cases when a big
tenant's records are closer to the query (persistence.STORE_SESSION, hnsw.iterative_scan).

For a selective prefix Postgres usually finds the tenant's rows by the prefix B-tree and sorts
them exactly, which is safe. The risk is the other plan, which the planner picks when it thinks the
prefix is not selective: walk the HNSW index in distance order and filter by prefix afterwards.
The test forces that plan."""

import uuid

import pytest

QUERY = "staging web app with postgres"


def search_count(store, ns, *settings):
    with store.conn.cursor() as cur:
        for s in settings:
            cur.execute(s)
    try:
        return len(store.search(ns, query=QUERY, limit=3))
    finally:
        with store.conn.cursor() as cur:
            cur.execute("RESET enable_seqscan")
            cur.execute("RESET enable_sort")
            cur.execute("RESET hnsw.iterative_scan")


@pytest.fixture
def two_tenants(store):
    big, small = (("episodes", f"t-{uuid.uuid4().hex[:8]}", "provisioner") for _ in range(2))
    for i in range(300):  # a big tenant whose records all match the query
        store.put(big, f"b{i}", {"summary": f"{QUERY} {i}"}, index=["summary"])
    for i in range(3):    # a small tenant with nothing close to it
        store.put(small, f"s{i}", {"summary": f"dev logs bucket {i}"}, index=["summary"])
    return small


def test_store_connections_scan_iteratively(store):
    with store.conn.cursor() as cur:
        cur.execute("SHOW hnsw.iterative_scan")
        assert cur.fetchone()["hnsw.iterative_scan"] == "relaxed_order"


def test_small_tenant_keeps_its_cases_on_the_index(store, two_tenants):
    hnsw_plan = ("SET enable_seqscan = off", "SET enable_sort = off")  # walk the HNSW index in distance order
    without = search_count(store, two_tenants, *hnsw_plan, "SET hnsw.iterative_scan = off")
    with_iterative = search_count(store, two_tenants, *hnsw_plan)
    assert without == 0  # the 40 nearest candidates were all the big tenant's, then filtered away
    assert with_iterative == 3
