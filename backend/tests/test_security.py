"""Access control: deny by default, cookie sessions, CSRF origin check, applicant scoping."""


def test_case_data_media_and_mocks_need_analyst(client):
    for path in ("/api/apps", "/api/apps/X", "/files/population.json", "/uploads/x.jpg", "/mock/uidai/123", "/api/graph",
                 "/docs", "/openapi.json", "/api/audit/verify"):
        assert client.get(path).status_code == 401, path


def test_demo_tools_need_analyst(client):
    for path in ("/api/ring-sim", "/api/testkit", "/api/demo/kit", "/api/attack/live"):
        assert client.post(path).status_code == 401, path


def test_public_endpoints(client):
    assert client.get("/api/health").json()["model"] in ("unavailable", "stale", "ok")
    assert client.get("/api/auth/me").json()["analyst"] is False


def test_wrong_key_rejected_right_key_sets_httponly_cookie(client):
    assert client.post("/api/auth/login", json={"key": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"key": "test-analyst-key"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/apps").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/apps").status_code == 401


def test_header_key_for_scripts(client):
    assert client.get("/api/apps", headers={"X-Analyst-Key": "test-analyst-key"}).status_code == 200


def test_query_string_key_no_longer_works(client):
    assert client.get("/api/apps?key=test-analyst-key").status_code == 401


def test_cross_site_post_refused(client):
    assert client.post("/api/session", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/session", headers={"Origin": "http://localhost:3001"}).status_code == 200


def test_apply_needs_applicant_session(client):
    client.cookies.clear()
    assert client.post("/api/apply").status_code == 401
    assert client.post("/api/liveness/challenge").status_code == 401


def test_jobs_are_scoped_to_their_session(client):
    from app import main
    client.cookies.clear()
    client.post("/api/session")
    main.JOBS["LOTHER"] = main.Job("LOTHER", "someone-else")
    assert client.get("/api/apply/LOTHER/events").status_code == 404
    assert client.get("/api/apply/LOTHER/result").status_code == 404


def test_forged_session_token_rejected():
    from app import security as S
    tok, sid = S.make_token("applicant", 60)
    assert S.read_token(tok, "applicant") == sid
    assert S.read_token(tok, "analyst") is None
    assert S.read_token(tok[:-2] + "00", "applicant") is None


def test_media_path_traversal_blocked(client):
    h = {"X-Analyst-Key": "test-analyst-key"}
    assert client.get("/files/../backend/.secrets/analyst_key", headers=h).status_code == 404
    assert client.get("/files/x.json", headers=h).status_code == 404


def test_payload_validation_and_consent(client):
    import json
    client.cookies.clear()
    client.post("/api/session")
    files = {"card": ("c.jpg", b"x", "image/jpeg"), "selfie": ("s.jpg", b"x", "image/jpeg")}
    bad = {"form": {"name": "A"}, "consent": {"accepted": True, "version": "x"}}
    assert client.post("/api/apply", data={"payload": json.dumps(bad)}, files=files).status_code == 422
    from app.config import CONSENT_VERSION
    good_form = {"name": "Asha Naik", "dob": "01/01/1990", "gender": "F", "id_number": "234567890123",
                 "phone": "9876543210", "email": "a@b.co"}
    no_consent = {"form": good_form, "consent": {"accepted": False, "version": CONSENT_VERSION}}
    assert client.post("/api/apply", data={"payload": json.dumps(no_consent)}, files=files).status_code == 422
    ok = {"form": good_form, "consent": {"accepted": True, "version": CONSENT_VERSION}}
    r = client.post("/api/apply", data={"payload": json.dumps(ok)}, files=files)
    assert r.status_code == 400 and "readable image" in r.text  # bytes that are not an image never reach the pipeline
