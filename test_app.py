import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from app import app, init_db

init_db()
client = app.test_client()

print("=" * 60)
print("EasyMind AI - Full Automated Verification Test Suite")
print("=" * 60)

# 1. Root Route
print("1. Testing Root Route / ...")
res = client.get("/")
assert res.status_code == 200, f"Root returned {res.status_code}"
assert b"EasyMind AI" in res.data
print("   [OK] Root Route returned 200 OK with full dashboard template")

# 2. Connection Status
print("2. Testing /api/status ...")
res = client.get("/api/status")
assert res.status_code == 200
data = res.get_json()
print(f"   [OK] LM Studio Connected: {data.get('connected')}")
print(f"   [OK] Active Model: {data.get('active_model')}")

# 3. Supported Languages
print("3. Testing /api/languages ...")
res = client.get("/api/languages")
assert res.status_code == 200
langs = res.get_json()["languages"]
assert len(langs) >= 8
print(f"   [OK] Supported Languages count: {len(langs)}")

# 4. Curated Examples
print("4. Testing /api/examples ...")
res = client.get("/api/examples")
assert res.status_code == 200
examples = res.get_json()["examples"]
assert "python" in examples and "javascript" in examples and "sql" in examples
print(f"   [OK] Loaded curated examples for {len(examples)} languages")

# 5. Safe Python Runner
print("5. Testing /api/run-code (Python) ...")
res = client.post("/api/run-code", json={
    "language": "python",
    "code": "print(sum([x * 2 for x in range(5)]))"
})
assert res.status_code == 200
p_out = res.get_json()
assert p_out["success"] is True
assert "20" in p_out["output"]
print(f"   [OK] Python execution output: {p_out['output'].strip()} ({p_out['execution_time_ms']}ms)")

# 6. Safe JavaScript Runner
print("6. Testing /api/run-code (JavaScript via Node) ...")
res = client.post("/api/run-code", json={
    "language": "javascript",
    "code": "console.log([10, 20, 30].reduce((a, b) => a + b, 0))"
})
assert res.status_code == 200
js_out = res.get_json()
assert js_out["success"] is True
assert "60" in js_out["output"]
print(f"   [OK] JS execution output: {js_out['output'].strip()} ({js_out['execution_time_ms']}ms)")

# 7. Safe In-Memory SQL Runner
print("7. Testing /api/run-code (In-Memory SQLite) ...")
res = client.post("/api/run-code", json={
    "language": "sql",
    "code": "CREATE TABLE demo(id INT, name TEXT); INSERT INTO demo VALUES(1, 'Alice'); SELECT * FROM demo;"
})
assert res.status_code == 200
sql_out = res.get_json()
assert sql_out["success"] is True
assert "Alice" in sql_out["output"]
print(f"   [OK] SQL execution output returned tabular data cleanly")

# 8. Test Cases Evaluator
print("8. Testing /api/run-tests (Automated Test Evaluator) ...")
res = client.post("/api/run-tests", json={
    "language": "python",
    "code": "import sys\nval = int(sys.stdin.read().strip())\nprint(val * val)",
    "test_cases": [
        {"input": "4", "expected": "16"},
        {"input": "7", "expected": "49"}
    ]
})
assert res.status_code == 200
t_res = res.get_json()
assert t_res["success"] is True
assert t_res["summary"]["passed"] == 2
print(f"   [OK] All {t_res['summary']['total']} test cases evaluated and PASSED!")

# 9. Save, Retrieve, Download, and Delete Snippet
print("9. Testing Snippet Lifecycle (/api/save-code, /api/saved-code, /api/delete-code) ...")
res = client.post("/api/save-code", json={
    "title": "sample_test_algo",
    "language": "python",
    "code": "def algo(): return True",
    "notes": "Automated test snippet"
})
assert res.status_code == 200
s_data = res.get_json()
snippet_id = s_data["id"]
filename = s_data["filename"]

res = client.get("/api/saved-code")
assert res.status_code == 200
assert any(s["id"] == snippet_id for s in res.get_json()["snippets"])

res = client.get(f"/api/download/{filename}")
assert res.status_code == 200

res = client.delete(f"/api/delete-code/{snippet_id}")
assert res.status_code == 200
print(f"   [OK] Snippet lifecycle verified (create, list, download, delete)")

# 10. Live Chat & LM Studio Inference
print("10. Testing Live LM Studio /api/chat ...")
res = client.post("/api/chat", json={
    "message": "Output 1 line of Python: print('EasyMind')",
    "language": "python",
    "mode": "generate",
    "session_id": "test_suite_session"
})
assert res.status_code == 200, f"Chat returned {res.status_code}: {res.get_data(as_text=True)}"
chat_data = res.get_json()
assert chat_data["success"] is True
assert "response" in chat_data and len(chat_data["response"]) > 0
print(f"   [OK] Live LM Studio response received!")
print(f"   [OK] Model used: {chat_data.get('model_used')}")

# 11. Clear History
print("11. Testing /api/clear ...")
res = client.post("/api/clear", json={"session_id": "test_suite_session"})
assert res.status_code == 200
res_hist = client.get("/api/history?session_id=test_suite_session")
assert len(res_hist.get_json()["history"]) == 0
print("   [OK] Session history cleared successfully")

print("\n" + "=" * 60)
print(">>> ALL 11 TEST SUITE PHASES PASSED WITH ZERO ERRORS! <<<")
print("=" * 60)
