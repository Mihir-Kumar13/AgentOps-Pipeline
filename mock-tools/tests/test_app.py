"""mock-tools must be deterministic and strict about arguments."""

H = {"X-Alert-Id": "ALR-oom-01"}


def test_health(tools_http):
    assert tools_http.get("/healthz").json()["scenarios"] >= 20


def test_scenario_data_served_by_alert_id(tools_http):
    body = tools_http.post(
        "/tools/get_metrics", json={"service": "checkout-api", "window": "1h"}, headers=H
    ).json()
    assert body["pod_restarts"] == 5
    assert body["series"]["memory_pct"][-1] == 98


def test_unknown_alert_gets_healthy_data(tools_http):
    body = tools_http.post(
        "/tools/get_metrics", json={"service": "x", "window": "1h"}, headers={"X-Alert-Id": "nope"}
    ).json()
    assert body["pod_restarts"] == 0


def test_same_request_same_answer(tools_http):
    args = {"service": "checkout-api", "window": "1h", "query": ""}
    a = tools_http.post("/tools/get_logs", json=args, headers=H).json()
    b = tools_http.post("/tools/get_logs", json=args, headers=H).json()
    assert a == b


def test_log_query_filters_and_falls_back(tools_http):
    def logs(q):
        args = {"service": "checkout-api", "window": "1h", "query": q}
        return tools_http.post("/tools/get_logs", json=args, headers=H).json()

    assert all("oomkilled" in ln["msg"].lower() for ln in logs("OOMKilled")["lines"])
    fallback = logs("no-such-text")
    assert "note" in fallback and fallback["lines"]


def test_extra_argument_is_rejected(tools_http):
    resp = tools_http.post(
        "/tools/get_recent_deploys", json={"service": "a", "extra": 1}, headers=H
    )
    assert resp.status_code == 422


def test_ticket_id_is_deterministic(tools_http):
    body = tools_http.post(
        "/tools/create_ticket", json={"severity": "P2", "title": "t", "body": "b"}, headers=H
    ).json()
    assert body["ticket_id"] == "TCK-ALR-oom-01"
