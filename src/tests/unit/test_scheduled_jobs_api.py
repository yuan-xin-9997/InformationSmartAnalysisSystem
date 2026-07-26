"""Scheduled-jobs API tests."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def _make_task(client, h):
    r = client.post("/api/analysis-tasks", json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []}, headers=h)
    return r.json()["id"]


def test_create_list_update_delete(client, admin_headers):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每天9点", "mode": "incremental", "trigger_type": "cron", "cron_expr": "0 9 * * *"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    assert r.json()["next_run_at"] is not None

    lst = client.get(f"/api/scheduled-jobs?task_id={tid}", headers=admin_headers)
    assert lst.status_code == 200 and len(lst.json()) == 1

    up = client.put(f"/api/scheduled-jobs/{jid}", json={"name": "改名"}, headers=admin_headers)
    assert up.status_code == 200 and up.json()["name"] == "改名"

    d = client.delete(f"/api/scheduled-jobs/{jid}", headers=admin_headers)
    assert d.status_code == 200


def test_invalid_cron_returns_400(client, admin_headers):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "bad", "mode": "incremental", "trigger_type": "cron", "cron_expr": "not-a-cron"},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_toggle_and_run_now(client, admin_headers, sync_worker, mock_llm):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental", "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    jid = r.json()["id"]

    run = client.post(f"/api/scheduled-jobs/{jid}/run", headers=admin_headers)
    assert run.status_code == 200 and "run_id" in run.json()

    # 启用时 next_run_at 应有值
    before_toggle = client.get("/api/scheduled-jobs", headers=admin_headers).json()
    before = next(j for j in before_toggle if j["id"] == jid)
    assert before["next_run_at"] is not None

    tg = client.post(f"/api/scheduled-jobs/{jid}/toggle", headers=admin_headers)
    assert tg.status_code == 200 and tg.json()["enabled"] is False
    # 禁用后 DB 的 next_run_at 必须清空,列表不再显示旧的下次运行时间
    after_toggle = client.get("/api/scheduled-jobs", headers=admin_headers).json()
    after = next(j for j in after_toggle if j["id"] == jid)
    assert after["next_run_at"] is None


def test_unmatched_api_non_get_returns_404_not_405(client, admin_headers):
    """SPA fallback: 未匹配的 /api/* 非 GET 请求应返回 404,而非 405。

    已注册的 /api/* POST/PUT/DELETE 路由优先匹配,不受影响。
    """
    # /api/analysis-results 已删除端点: GET 返回 404(spa_fallback)
    assert client.get("/api/analysis-results", headers=admin_headers).status_code == 404
    # POST/PUT/DELETE 同样应返回 404(而非 405)
    assert client.post("/api/analysis-results", headers=admin_headers).status_code == 404
    assert client.put("/api/analysis-results", headers=admin_headers).status_code == 404
    assert client.delete("/api/analysis-results", headers=admin_headers).status_code == 404
    # 已注册的 POST 路由仍正常工作(优先匹配)
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200


def test_forbidden_for_user_without_page(client):
    # tester 是普通用户,默认无 scheduled_jobs 权限
    r = client.post("/api/auth/login", json={"username": "tester", "password": "tester123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = client.get("/api/scheduled-jobs", headers=h)
    assert resp.status_code == 403


def test_next_run_at_is_correct_beijing_time(client, admin_headers):
    """跟进点1: next_run_at 必须是正确的北京时间,不能因时区归一化缺失而 +8h。

    APScheduler 的 next_run_time 是 tz-aware Asia/Shanghai;若直接写入 SQLite
    (DateTime 列会剥离 tzinfo),读回为 naive,BeijingDatetime 的 to_beijing 会
    当作 UTC 再 +8,导致显示时间比真实北京时间晚 8 小时。
    """
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental",
              "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    next_run_at_str = r.json()["next_run_at"]
    assert next_run_at_str is not None

    BJ = ZoneInfo("Asia/Shanghai")
    next_run_at = datetime.fromisoformat(next_run_at_str)
    assert next_run_at.tzinfo is not None  # 序列化后应 tz-aware

    now_bj = datetime.now(BJ)
    delta = (next_run_at - now_bj).total_seconds()
    # interval=60s -> next_run_at 应约在 now+60s。若有 +8h bug,delta ≈ 8*3600+60。
    assert 0 < delta < 600, (
        f"next_run_at {next_run_at} 偏离 now {now_bj} 达 {delta}s,"
        "疑似 next_run_at 时区未归一化(+8h bug)"
    )


def test_update_trigger_type_uses_existing_cron_expr(client, admin_headers):
    """跟进点2: PUT 只改 trigger_type=cron 但未传 cron_expr 时,应合并现有 sj 的
    cron_expr 做校验,而非误报 "cron 模式必须填写 cron_expr"。"""
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每天9点", "mode": "incremental",
              "trigger_type": "cron", "cron_expr": "0 9 * * *"},
        headers=admin_headers,
    )
    jid = r.json()["id"]
    # 只传 trigger_type=cron;合并后 cron_expr 仍为 "0 9 * * *",应通过校验。
    up = client.put(f"/api/scheduled-jobs/{jid}", json={"trigger_type": "cron"}, headers=admin_headers)
    assert up.status_code == 200, up.text
    assert up.json()["cron_expr"] == "0 9 * * *"


def test_update_trigger_type_to_cron_without_any_cron_expr_returns_400(client, admin_headers):
    """跟进点2: 从 interval 切到 cron,且现有 sj 无 cron_expr、req 也未传,应 400。"""
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental",
              "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    jid = r.json()["id"]
    up = client.put(f"/api/scheduled-jobs/{jid}", json={"trigger_type": "cron"}, headers=admin_headers)
    assert up.status_code == 400


def test_update_trigger_type_switch_clears_opposite_field(client, admin_headers):
    """切换 trigger_type 时清对方字段: 切到 cron 清 interval_seconds,切到 interval 清 cron_expr。"""
    tid = _make_task(client, admin_headers)
    # 起点: interval 模式
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental",
              "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    jid = r.json()["id"]

    # 切到 cron: interval_seconds 应被清空
    up = client.put(
        f"/api/scheduled-jobs/{jid}",
        json={"trigger_type": "cron", "cron_expr": "0 9 * * *"},
        headers=admin_headers,
    )
    assert up.status_code == 200, up.text
    assert up.json()["trigger_type"] == "cron"
    assert up.json()["cron_expr"] == "0 9 * * *"
    assert up.json()["interval_seconds"] is None

    # 再切回 interval: cron_expr 应被清空
    up2 = client.put(
        f"/api/scheduled-jobs/{jid}",
        json={"trigger_type": "interval", "interval_seconds": 120},
        headers=admin_headers,
    )
    assert up2.status_code == 200, up2.text
    assert up2.json()["trigger_type"] == "interval"
    assert up2.json()["interval_seconds"] == 120
    assert up2.json()["cron_expr"] is None
