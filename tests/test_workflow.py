import os
import io
import json
import tempfile
from pathlib import Path

from openpyxl import Workbook

_fd, _db_path = tempfile.mkstemp(prefix="forgequote-tests-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_db_path))
os.environ["AI_API_KEY"] = ""
os.environ["AI_NDA_APPROVED"] = "false"

from fastapi.testclient import TestClient

from backend.main import app


def test_seeded_end_to_end_approval_and_pdf():
    with TestClient(app) as client:
        seeded = client.get("/api/auth/login")
        assert seeded.status_code == 405
        response = client.post("/api/auth/login", json={
            "username": "estimator@demo.local", "password": "estimate-demo"})
        assert response.status_code == 200
        estimator_csrf = response.json()["csrf_token"]
        rfqs = client.get("/api/rfqs").json()["items"]
        assert len(rfqs) == 27
        assert sum(1 for item in rfqs if item["synthetic"]) == 24

        rfq = next(item for item in rfqs if item["rfq_number"] == "RFQ-2611-014")
        calculated = client.post(f"/api/rfqs/{rfq['id']}/cost", json={"volumes": [180000, 10000, 50000]},
                                 headers={"X-CSRF-Token": estimator_csrf})
        assert calculated.status_code == 200, calculated.text
        body = calculated.json()
        assert body["reference_volume"] == 180000
        duplicate_volumes = client.post(f"/api/rfqs/{rfq['id']}/cost", json={"volumes": [50000, 50000]},
                                        headers={"X-CSRF-Token": estimator_csrf})
        assert duplicate_volumes.status_code == 422
        assert body["breakdown"][0]["scenarios"][0]["processing"] == 45.33
        original_snapshot = body["rate_snapshots"][0]["material_rate"]
        part_id = body["breakdown"][0]["part_id"]
        updated_part = client.patch(f"/api/parts/{part_id}", json={"routing_operations":[
            {"operation_name":"Turning", "machine_rate_key":"Turning cell", "cycle_time_min":3.2},
            {"operation_name":"Grinding", "machine_rate_key":"Precision grinding", "cycle_time_min":1.5},
        ]}, headers={"X-CSRF-Token": estimator_csrf})
        assert updated_part.status_code == 200, updated_part.text
        multi_route = client.post(f"/api/rfqs/{rfq['id']}/cost", json={"volumes":[10000, 50000]},
                                  headers={"X-CSRF-Token": estimator_csrf}).json()
        assert multi_route["breakdown"][0]["scenarios"][0]["processing"] == 77.33
        assert len(multi_route["breakdown"][0]["routing_operations"]) == 2
        submitted = client.post(f"/api/revisions/{body['revision_id']}/submit", json={},
                                headers={"X-CSRF-Token": estimator_csrf})
        assert submitted.status_code == 200
        assert client.get("/api/approvals").status_code == 403
        assert client.get("/api/users/estimators").status_code == 403

        sales_login = client.post("/api/auth/login", json={
            "username": "sales@demo.local", "password": "approve-demo"})
        assert sales_login.status_code == 200
        sales_csrf = sales_login.json()["csrf_token"]
        wrong_unit = client.post("/api/rates", json={"rate_type":"material","rate_key":"QA material",
            "unit":"₹ / hour","amount":100,"effective_from": "2026-11-02"},
            headers={"X-CSRF-Token":sales_csrf})
        assert wrong_unit.status_code == 422
        estimators = client.get("/api/users/estimators").json()["items"]
        reassigned = client.patch(f"/api/rfqs/{rfq['id']}/owner", json={"owner_id":next(x["id"] for x in estimators if x["id"] != rfq["owner_id"])},
                                  headers={"X-CSRF-Token":sales_csrf})
        assert reassigned.status_code == 200, reassigned.text
        assert client.get(f"/api/rfqs/{rfq['id']}").json()["owner"] == "Nisha · Estimator"
        queue = client.get("/api/approvals").json()["items"]
        pending = next(item for item in queue if item["id"] == body["revision_id"])
        assert pending["rates"][0]["material_rate"] == original_snapshot

        approval = client.post(f"/api/revisions/{body['revision_id']}/decision",
            json={"decision": "approve"}, headers={"X-CSRF-Token": sales_csrf})
        assert approval.status_code == 200
        pdf = client.get(f"/api/revisions/{body['revision_id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"

        sent = client.post(f"/api/revisions/{body['revision_id']}/sent", json={},
                           headers={"X-CSRF-Token": sales_csrf})
        assert sent.status_code == 200
        updated = client.get(f"/api/rfqs/{rfq['id']}").json()
        assert updated["status"] == "sent"


def test_import_column_mapping_and_synthetic_provenance():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Account", "RFQ Reference", "Item Description", "Alloy", "Part Weight kg",
                  "Production Qty", "Total Cycle Minutes", "Historical Price", "Demo Record"])
    sheet.append(["Demo Customer 14", "DEMO-IMPORT-MAP-001", "Synthetic steering pin", "EN19",
                  1.1, 24000, 4.7, 145.25, "yes"])
    content = io.BytesIO()
    workbook.save(content)
    payload = content.getvalue()
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username":"estimator@demo.local", "password":"estimate-demo"})
        csrf = login.json()["csrf_token"]
        first = client.post("/api/imports/preview", headers={"X-CSRF-Token":csrf},
            files={"file":("synthetic-history.xlsx",payload,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert first.status_code == 200
        assert first.json()["needs_mapping"] is True
        mapping = {"customer":0,"rfq_number":1,"part_name":2,"material":3,"gross_weight_kg":4,
                   "annual_volume":5,"cycle_time_min":6,"quoted_unit_price":7,"synthetic":8}
        preview = client.post("/api/imports/preview", headers={"X-CSRF-Token":csrf},
            data={"mapping":json.dumps(mapping),"force_synthetic":"false"},
            files={"file":("synthetic-history.xlsx",payload,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["valid_count"] == 1
        assert body["preview"][0]["synthetic"] is True
        committed = client.post(f"/api/imports/{body['batch_id']}/commit", json={}, headers={"X-CSRF-Token":csrf})
        assert committed.status_code == 200, committed.text
        imported = client.get("/api/history?q=DEMO-IMPORT-MAP-001").json()["items"][0]
        assert imported["synthetic"] is True
        assert imported["source_label"].startswith("Synthetic demo import")


def test_routing_operations_repeated_update():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "estimator@demo.local", "password": "estimate-demo"})
        csrf = login.json()["csrf_token"]
        rfqs = client.get("/api/rfqs").json()["items"]
        part_id = client.get(f"/api/rfqs/{rfqs[0]['id']}").json()["parts"][0]["id"]
        # First update
        r1 = client.patch(f"/api/parts/{part_id}", json={"routing_operations": [
            {"operation_name": "Op 1", "machine_rate_key": "Turning cell", "cycle_time_min": 2.0},
            {"operation_name": "Op 2", "machine_rate_key": "Precision grinding", "cycle_time_min": 1.0},
        ]}, headers={"X-CSRF-Token": csrf})
        assert r1.status_code == 200
        # Second update (previously triggered UNIQUE constraint collision)
        r2 = client.patch(f"/api/parts/{part_id}", json={"routing_operations": [
            {"operation_name": "Op A", "machine_rate_key": "Turning cell", "cycle_time_min": 3.0},
            {"operation_name": "Op B", "machine_rate_key": "Precision grinding", "cycle_time_min": 1.5},
        ]}, headers={"X-CSRF-Token": csrf})
        assert r2.status_code == 200
        part = client.get(f"/api/rfqs/{rfqs[0]['id']}").json()["parts"][0]
        assert len(part["routing_operations"]) == 2
        assert part["routing_operations"][0]["operation_name"] == "Op A"


def test_corrupt_file_extract_handled_gracefully():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "estimator@demo.local", "password": "estimate-demo"})
        csrf = login.json()["csrf_token"]
        r = client.post("/api/intake/file-extract",
            files={"file": ("corrupt.xlsx", b"invalid-bytes-header", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200
        data = r.json()
        assert data["method"] == "unavailable"
        assert "Extraction failed" in data["extraction_error"]
        assert data["file_id"] is not None


def test_history_paginates_complete_synthetic_dataset():
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "estimator@demo.local", "password": "estimate-demo"})
        first = client.get("/api/history?page=1&page_size=10").json()
        second = client.get("/api/history?page=2&page_size=10").json()
        assert first["total"] >= 50
        assert first["page"] == 1 and second["page"] == 2
        assert len(first["items"]) == len(second["items"]) == 10
        assert not ({(item["rfq_number"], item["part_name"]) for item in first["items"]} &
                    {(item["rfq_number"], item["part_name"]) for item in second["items"]})


def test_rfq_header_update_and_role_access():
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "estimator@demo.local", "password": "estimate-demo"})
        csrf = login.json()["csrf_token"]
        user_id = client.get("/api/me").json()["user"]["id"]
        rfq = next(item for item in client.get("/api/rfqs").json()["items"]
                   if item["owner_id"] == user_id)
        changed = client.patch(f"/api/rfqs/{rfq['id']}", json={
            "rfq_number": rfq["rfq_number"], "customer": "Synthetic validation customer",
            "due_date": rfq["due_date"]}, headers={"X-CSRF-Token": csrf})
        assert changed.status_code == 200
        assert changed.json()["customer"] == "Synthetic validation customer"
        other = next(item for item in client.get("/api/rfqs").json()["items"]
                     if item["owner_id"] != user_id)
        denied = client.patch(f"/api/rfqs/{other['id']}", json={
            "rfq_number": other["rfq_number"], "customer": other["customer"],
            "due_date": other["due_date"]}, headers={"X-CSRF-Token": csrf})
        assert denied.status_code == 403


def test_import_preview_lists_worksheets_and_can_select_one():
    workbook = Workbook()
    workbook.active.title = "Cover"
    sheet = workbook.create_sheet("Historical quotes")
    sheet.append(["RFQ", "Customer", "Part", "Material", "Gross Wt kg", "Annual Volume", "Cycle Time min"])
    sheet.append(["DEMO-MULTI-001", "Synthetic buyer", "Demo pin", "EN8", 0.4, 5000, 2.5])
    content = io.BytesIO()
    workbook.save(content)
    payload = content.getvalue()
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "estimator@demo.local", "password": "estimate-demo"})
        csrf = login.json()["csrf_token"]
        preview = client.post("/api/imports/preview", headers={"X-CSRF-Token": csrf},
            data={"sheet_name": "Historical quotes"},
            files={"file": ("multi-sheet.xlsx", payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert preview.status_code == 200
        result = preview.json()
        assert "Historical quotes" in result["sheets"]
        assert result["sheet_name"] == "Historical quotes"
        assert result["source_rows"] == 1


def test_gst_is_separate_and_snapshotted():
    import backend.main as main
    old_rate = main.GST_RATE_PERCENT
    main.GST_RATE_PERCENT = 5
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={
                "username": "estimator@demo.local", "password": "estimate-demo"})
            csrf = login.json()["csrf_token"]
            rfq = next(x for x in client.get("/api/rfqs").json()["items"]
                       if x["rfq_number"] == "RFQ-2611-014")
            quote = client.post(f"/api/rfqs/{rfq['id']}/cost", json={"volumes": [1000, 2000]},
                headers={"X-CSRF-Token": csrf}).json()
            assert quote["gst_rate_percent"] == 5
            assert quote["annual_value_including_gst"] == round(quote["annual_value"] * 1.05, 2)
            assert quote["gst_annual_value"] == round(quote["annual_value"] * .05, 2)
    finally:
        main.GST_RATE_PERCENT = old_rate


def test_1400_row_synthetic_workbook_import():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["RFQ", "Customer", "Part", "Material", "Gross Wt kg",
                  "Annual Volume", "Cycle Time min", "Quoted Unit Price"])
    for row in range(1400):
        sheet.append([f"DEMO-1400-{row:04d}", "Synthetic buyer", f"Demo part {row}",
                      "EN8", 0.5, 12000, 3.0, 145.25])
    content = io.BytesIO()
    workbook.save(content)
    payload = content.getvalue()
    mapping = {"rfq_number":0,"customer":1,"part_name":2,"material":3,"gross_weight_kg":4,
               "annual_volume":5,"cycle_time_min":6,"quoted_unit_price":7}
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username":"estimator@demo.local","password":"estimate-demo"})
        csrf = login.json()["csrf_token"]
        preview = client.post("/api/imports/preview", headers={"X-CSRF-Token":csrf},
            data={"mapping":json.dumps(mapping),"force_synthetic":"true"},
            files={"file":("synthetic-1400.xlsx",payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert preview.status_code == 200, preview.text
        result = preview.json()
        assert result["valid_count"] == result["source_rows"] == 1400
        assert result["error_count"] == 0
        assert len(result["preview"]) == 12
        committed = client.post(f"/api/imports/{result['batch_id']}/commit", json={},
            headers={"X-CSRF-Token":csrf})
        assert committed.status_code == 200, committed.text
        assert committed.json()["imported"] == 1400
        page = client.get("/api/history?q=DEMO-1400-1399&page=1&page_size=10").json()
        assert page["total"] == 1
        assert page["items"][0]["synthetic"] is True
