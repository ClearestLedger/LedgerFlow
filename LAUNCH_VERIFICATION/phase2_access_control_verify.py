from __future__ import annotations

import html
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "_live_sync_tmp" / "app.py"
RESET_BUNDLE_DIR = Path(r"C:\Users\danie\OneDrive\Desktop\LedgerNew_Render_Migration")
RUN_DIR = ROOT / "_tmp_phase2_access_control_verification"
RUN_DATA_DIR = RUN_DIR / "data"
RESULTS_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE2_RESULTS.json"
REPORT_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE2_REPORT.md"

ADMIN_EMAIL = "ledgerflowglow@gmail.com"
ADMIN_PASSWORD = "LedgerTemp!2026"

ALPHA_EMAIL = "phase2.alpha@ledgerflow.local"
ALPHA_PASSWORD = "Phase2Alpha!2026"
BETA_EMAIL = "phase2.beta@ledgerflow.local"
BETA_PASSWORD = "Phase2Beta!2026"

ALPHA_WORKER_EMAIL = "phase2.worker.alpha@ledgerflow.local"
ALPHA_WORKER_PASSWORD = "WorkerAlpha!2026"
BETA_WORKER_EMAIL = "phase2.worker.beta@ledgerflow.local"
BETA_WORKER_PASSWORD = "WorkerBeta!2026"


def prepare_run_dir() -> None:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in (".local_secret_key", "email_runtime_config.json", "rds_core_web.db"):
        shutil.copy2(RESET_BUNDLE_DIR / name, RUN_DATA_DIR / name)


def load_app_module():
    os.environ["DATA_DIR"] = str(RUN_DATA_DIR)
    os.environ["DATABASE_PATH"] = str(RUN_DATA_DIR / "rds_core_web.db")
    os.environ.pop("APP_ENV", None)
    module_name = f"ledgerflow_phase2_verify_{int(datetime.now().timestamp())}"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("Could not load LedgerFlow app module for phase 2 verification.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def seed_business(
    conn: sqlite3.Connection,
    module,
    *,
    business_name: str,
    category: str,
    specialty: str,
    contact_name: str,
    business_email: str,
    business_password: str,
    business_phone: str,
    business_address: str,
    worker_name: str,
    worker_email: str,
    worker_password: str,
    customer_name: str,
    customer_email: str,
    invoice_token: str,
) -> dict:
    now = datetime.now().replace(microsecond=0)
    now_iso = now.isoformat(timespec="seconds")
    scheduled_start = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
    scheduled_end = scheduled_start + timedelta(hours=3)

    conn.execute(
        """
        INSERT INTO clients (
            business_name, business_type, business_category, business_specialty, preferred_language,
            service_level, access_service_level, subscription_plan_code, subscription_status,
            subscription_amount, subscription_interval, subscription_autopay_enabled,
            onboarding_status, record_status, contact_name, phone, email, address, billing_notes,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            business_name,
            "LLC",
            category,
            specialty,
            "en",
            "self_service",
            "premium",
            "premium_monthly",
            "active",
            149.00,
            "monthly",
            0,
            "completed",
            "active",
            contact_name,
            business_phone,
            business_email,
            business_address,
            f"{business_name} seeded for access-control verification.",
            now_iso,
        ),
    )
    client_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    module.ops_ensure_reference_data(conn, client_id)

    conn.execute(
        """
        INSERT INTO users (email, password_hash, full_name, role, client_id, preferred_language, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            business_email,
            generate_password_hash(business_password),
            contact_name,
            "client",
            client_id,
            "en",
            now_iso,
        ),
    )
    business_user_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO customer_contacts (
            client_id, customer_name, customer_email, customer_phone, customer_address,
            customer_notes, status, created_by_user_id, updated_by_user_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            customer_name,
            customer_email,
            "9415550199",
            business_address,
            f"{business_name} tenant-isolation customer record.",
            "active",
            business_user_id,
            business_user_id,
            now_iso,
            now_iso,
        ),
    )
    customer_contact_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO service_locations (
            client_id, customer_contact_id, location_name, address_line1, city, state, postal_code,
            access_notes, location_notes, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            customer_contact_id,
            f"{business_name} Primary Site",
            business_address.split(",")[0],
            "Sarasota",
            "FL",
            "34231",
            "Verification access note.",
            f"{business_name} seeded location.",
            now_iso,
            now_iso,
        ),
    )
    service_location_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    service_type = conn.execute(
        "SELECT id, name FROM service_types WHERE client_id=? ORDER BY id LIMIT 1",
        (client_id,),
    ).fetchone()
    service_type_id = int(service_type["id"]) if service_type else None
    service_type_name = service_type["name"] if service_type else category

    conn.execute(
        """
        INSERT INTO workers (
            client_id, name, worker_type, phone, email, preferred_language, hire_date, pay_notes,
            portal_password_hash, portal_access_enabled, portal_approval_status, portal_requested_at,
            portal_approved_at, portal_approved_by, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            worker_name,
            "1099",
            "9415550188",
            worker_email,
            "en",
            now.date().isoformat(),
            f"{business_name} seeded worker.",
            generate_password_hash(worker_password),
            1,
            "approved",
            now_iso,
            now_iso,
            1,
            now_iso,
        ),
    )
    worker_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO jobs (
            client_id, customer_contact_id, service_location_id, service_type_id, created_by_user_id,
            updated_by_user_id, title, customer_name, customer_reference, service_type_name, priority, status,
            field_progress_status, service_address, city, state, postal_code, scheduled_start, scheduled_end,
            estimated_duration_minutes, revenue_amount, materials_cost_amount, labor_cost_amount,
            other_cost_amount, notes_summary, dispatch_notes, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            customer_contact_id,
            service_location_id,
            service_type_id,
            business_user_id,
            business_user_id,
            f"{business_name} Verification Job",
            customer_name,
            f"{business_name[:4].upper()}-VERIFY",
            service_type_name,
            "high",
            "scheduled",
            "not_started",
            business_address,
            "Sarasota",
            "FL",
            "34231",
            scheduled_start.isoformat(timespec="seconds"),
            scheduled_end.isoformat(timespec="seconds"),
            180,
            2100.00,
            280.00,
            450.00,
            60.00,
            f"{business_name} seeded job for route isolation.",
            "Seeded by phase 2 verifier.",
            now_iso,
            now_iso,
        ),
    )
    job_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO job_assignments (job_id, worker_id, assignment_role, assigned_at, assigned_by_user_id, status, sort_order)
        VALUES (?,?,?,?,?,?,?)
        """,
        (job_id, worker_id, "lead", now_iso, business_user_id, "assigned", 0),
    )

    conn.execute(
        """
        INSERT INTO invoices (
            client_id, job_number, record_kind, invoice_title, client_name, recipient_email, client_address,
            invoice_total_amount, paid_amount, invoice_date, due_date, invoice_status, public_invoice_token,
            notes, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            client_id,
            job_id,
            "customer_invoice",
            f"{business_name} Verification Invoice",
            customer_name,
            customer_email,
            business_address,
            2100.00,
            800.00,
            now.date().isoformat(),
            (now.date() + timedelta(days=14)).isoformat(),
            "sent",
            invoice_token,
            f"{business_name} seeded invoice for public-token isolation.",
            now_iso,
        ),
    )
    invoice_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    conn.execute(
        """
        INSERT INTO worker_payments (
            worker_id, payment_date, amount, payment_method, payment_status, reference_number, note, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            worker_id,
            now.date().isoformat(),
            525.00,
            "direct_deposit",
            "paid",
            f"{business_name[:4].upper()}-PAY-1",
            f"{business_name} seeded pay stub.",
            now_iso,
        ),
    )
    payment_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    module.ops_log_activity(
        conn,
        client_id=client_id,
        job_id=job_id,
        actor_type="business_user",
        actor_id=business_user_id,
        event_type="phase2_seeded",
        event_text=f"{business_name} seeded for phase 2 access-control verification.",
    )

    return {
        "client_id": client_id,
        "business_name": business_name,
        "business_user_id": business_user_id,
        "business_email": business_email,
        "business_password": business_password,
        "worker_id": worker_id,
        "worker_email": worker_email,
        "worker_password": worker_password,
        "worker_name": worker_name,
        "job_id": job_id,
        "invoice_id": invoice_id,
        "invoice_token": invoice_token,
        "payment_id": payment_id,
        "customer_name": customer_name,
    }


def seed_verification_baseline(module) -> dict:
    with sqlite3.connect(RUN_DATA_DIR / "rds_core_web.db") as conn:
        conn.row_factory = sqlite3.Row
        alpha = seed_business(
            conn,
            module,
            business_name="Phase 2 Alpha Painting LLC",
            category="Painting",
            specialty="Interior painting and trim refresh",
            contact_name="Alpha Owner",
            business_email=ALPHA_EMAIL,
            business_password=ALPHA_PASSWORD,
            business_phone="9415550201",
            business_address="3934 Brookside Dr, Sarasota, FL 34231",
            worker_name="Alpha Worker",
            worker_email=ALPHA_WORKER_EMAIL,
            worker_password=ALPHA_WORKER_PASSWORD,
            customer_name="Alpha Customer",
            customer_email="alpha.customer@example.com",
            invoice_token="phase2-alpha-public-token",
        )
        beta = seed_business(
            conn,
            module,
            business_name="Phase 2 Beta Cleaning LLC",
            category="Cleaning",
            specialty="Weekly recurring residential cleaning",
            contact_name="Beta Owner",
            business_email=BETA_EMAIL,
            business_password=BETA_PASSWORD,
            business_phone="9415550202",
            business_address="101 Harbor View Dr, Sarasota, FL 34236",
            worker_name="Beta Worker",
            worker_email=BETA_WORKER_EMAIL,
            worker_password=BETA_WORKER_PASSWORD,
            customer_name="Beta Customer",
            customer_email="beta.customer@example.com",
            invoice_token="phase2-beta-public-token",
        )
        conn.commit()
    return {"alpha": alpha, "beta": beta}


def login_user(client, email: str, password: str) -> dict:
    response = client.post(
        "/main-portal",
        data={"email": email, "password": password, "preferred_language": "en"},
        follow_redirects=False,
    )
    location = response.headers.get("Location", "")
    if response.status_code in {302, 303} and "/legal-acceptance" in location:
        legal_get = client.get(location, follow_redirects=False)
        next_path = "/cpa-dashboard" if "cpa-dashboard" in location else "/dashboard"
        if legal_get.status_code == 200:
            next_match = re.search(r'name=[\"\']next[\"\'] value=[\"\']([^\"\']*)[\"\']', legal_get.get_data(as_text=True))
            if next_match:
                next_path = html.unescape(next_match.group(1))
        response = client.post(
            "/legal-acceptance",
            data={"accept_terms": "1", "accept_privacy": "1", "next": next_path},
            follow_redirects=False,
        )
        location = response.headers.get("Location", "")
    return {"status_code": response.status_code, "location": location, "ok": response.status_code in {302, 303}}


def login_worker(client, email: str, password: str) -> dict:
    response = client.post(
        "/worker-login",
        data={"email": email, "password": password, "preferred_language": "en"},
        follow_redirects=False,
    )
    return {"status_code": response.status_code, "location": response.headers.get("Location", ""), "ok": response.status_code in {302, 303}}


def page_result(response, *, label: str, path: str, expect_text: str = "", forbid_text: str = "", expect_final_path: str = "", expected_status: int = 200) -> dict:
    body = response.get_data(as_text=True)
    body_plain = html.unescape(body).lower()
    expect_ok = True if not expect_text else expect_text.lower() in body_plain
    forbid_ok = True if not forbid_text else forbid_text.lower() not in body_plain
    final_path = response.request.path if response.request else ""
    path_ok = True if not expect_final_path else final_path == expect_final_path
    status_ok = response.status_code == expected_status
    internal_error = "internal server error" in body_plain
    passed = status_ok and expect_ok and forbid_ok and path_ok and not internal_error
    return {
        "label": label,
        "path": path,
        "status_code": response.status_code,
        "final_path": final_path,
        "expected_status": expected_status,
        "expected_text": expect_text,
        "forbidden_text": forbid_text,
        "expected_final_path": expect_final_path,
        "expected_text_found": expect_ok,
        "forbidden_text_absent": forbid_ok,
        "final_path_ok": path_ok,
        "internal_error": internal_error,
        "pass": passed,
    }


def redirect_result(response, *, label: str, path: str, expected_location_fragment: str) -> dict:
    location = response.headers.get("Location", "")
    status_ok = response.status_code in {302, 303}
    location_ok = expected_location_fragment in location
    return {
        "label": label,
        "path": path,
        "status_code": response.status_code,
        "location": location,
        "expected_location_fragment": expected_location_fragment,
        "pass": status_ok and location_ok,
    }


def denial_result(response, *, label: str, path: str, expected_status: int = 403) -> dict:
    return {
        "label": label,
        "path": path,
        "status_code": response.status_code,
        "expected_status": expected_status,
        "pass": response.status_code == expected_status,
    }


def run_phase(module, seed: dict) -> dict:
    admin_client = module.app.test_client()
    alpha_client = module.app.test_client()
    beta_client = module.app.test_client()
    worker_client = module.app.test_client()
    public_client = module.app.test_client()

    admin_login = login_user(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    alpha_login = login_user(alpha_client, seed["alpha"]["business_email"], seed["alpha"]["business_password"])
    beta_login = login_user(beta_client, seed["beta"]["business_email"], seed["beta"]["business_password"])
    worker_login = login_worker(worker_client, seed["alpha"]["worker_email"], seed["alpha"]["worker_password"])

    results = {
        "seed": seed,
        "admin_login": admin_login,
        "alpha_login": alpha_login,
        "beta_login": beta_login,
        "worker_login": worker_login,
        "admin_supervision": [],
        "business_isolation": [],
        "worker_boundaries": [],
        "public_document_isolation": [],
    }

    alpha_name = seed["alpha"]["business_name"]
    beta_name = seed["beta"]["business_name"]

    results["admin_supervision"].append(
        page_result(
            admin_client.get(f"/business-payments?client_id={seed['alpha']['client_id']}", follow_redirects=True),
            label="Admin opens Alpha Billing Center",
            path=f"/business-payments?client_id={seed['alpha']['client_id']}",
            expect_text=alpha_name,
            expect_final_path="/business-payments",
        )
    )
    results["admin_supervision"].append(
        page_result(
            admin_client.get(f"/business-payments?client_id={seed['beta']['client_id']}", follow_redirects=True),
            label="Admin opens Beta Billing Center",
            path=f"/business-payments?client_id={seed['beta']['client_id']}",
            expect_text=beta_name,
            expect_final_path="/business-payments",
        )
    )

    alpha_scenarios = [
        ("Alpha own billing center", "/business-payments", alpha_name, beta_name, "/business-payments"),
        ("Alpha tries Beta billing center", f"/business-payments?client_id={seed['beta']['client_id']}", alpha_name, beta_name, "/business-payments"),
        ("Alpha tries Beta owner view", f"/dashboard?client_id={seed['beta']['client_id']}", "Owner View", beta_name, "/dashboard"),
        ("Alpha tries Beta clients and sales", f"/clients-sales?client_id={seed['beta']['client_id']}", "Clients & Sales", beta_name, "/clients-sales"),
    ]
    for label, path, expect_text, forbid_text, final_path in alpha_scenarios:
        results["business_isolation"].append(
            page_result(
                alpha_client.get(path, follow_redirects=True),
                label=label,
                path=path,
                expect_text=expect_text,
                forbid_text=forbid_text,
                expect_final_path=final_path,
            )
        )

    results["business_isolation"].append(
        denial_result(
            alpha_client.get("/cpa-dashboard", follow_redirects=False),
            label="Alpha blocked from admin dashboard",
            path="/cpa-dashboard",
        )
    )

    beta_scenarios = [
        ("Beta own billing center", "/business-payments", beta_name, alpha_name, "/business-payments"),
        ("Beta tries Alpha billing center", f"/business-payments?client_id={seed['alpha']['client_id']}", beta_name, alpha_name, "/business-payments"),
        ("Beta tries Alpha reports", f"/reports?client_id={seed['alpha']['client_id']}", "Reports", alpha_name, "/reports"),
    ]
    for label, path, expect_text, forbid_text, final_path in beta_scenarios:
        results["business_isolation"].append(
            page_result(
                beta_client.get(path, follow_redirects=True),
                label=label,
                path=path,
                expect_text=expect_text,
                forbid_text=forbid_text,
                expect_final_path=final_path,
            )
        )

    results["worker_boundaries"].append(
        page_result(
            worker_client.get("/worker-portal/time-summary", follow_redirects=True),
            label="Worker opens own time summary",
            path="/worker-portal/time-summary",
            expect_text=seed["alpha"]["worker_name"],
            expect_final_path="/worker-portal/time-summary",
        )
    )
    results["worker_boundaries"].append(
        page_result(
            worker_client.get(f"/worker-portal/pay-stubs/{seed['alpha']['payment_id']}", follow_redirects=True),
            label="Worker opens own pay stub",
            path=f"/worker-portal/pay-stubs/{seed['alpha']['payment_id']}",
            expect_text=seed["alpha"]["worker_name"],
            expect_final_path=f"/worker-portal/pay-stubs/{seed['alpha']['payment_id']}",
        )
    )
    results["worker_boundaries"].append(
        denial_result(
            worker_client.get(f"/worker-portal/pay-stubs/{seed['beta']['payment_id']}", follow_redirects=False),
            label="Worker blocked from other business pay stub",
            path=f"/worker-portal/pay-stubs/{seed['beta']['payment_id']}",
            expected_status=404,
        )
    )
    results["worker_boundaries"].append(
        redirect_result(
            worker_client.get(f"/dashboard?client_id={seed['alpha']['client_id']}", follow_redirects=False),
            label="Worker blocked from business dashboard",
            path=f"/dashboard?client_id={seed['alpha']['client_id']}",
            expected_location_fragment="/login",
        )
    )
    results["worker_boundaries"].append(
        redirect_result(
            worker_client.get("/cpa-dashboard", follow_redirects=False),
            label="Worker blocked from admin dashboard",
            path="/cpa-dashboard",
            expected_location_fragment="/login",
        )
    )
    results["worker_boundaries"].append(
        redirect_result(
            alpha_client.get(f"/worker-portal/pay-stubs/{seed['alpha']['payment_id']}", follow_redirects=False),
            label="Business user blocked from worker portal pay stub route",
            path=f"/worker-portal/pay-stubs/{seed['alpha']['payment_id']}",
            expected_location_fragment="/worker-login",
        )
    )

    results["public_document_isolation"].append(
        page_result(
            public_client.get(f"/customer-invoice/{seed['alpha']['invoice_token']}", follow_redirects=True),
            label="Public alpha invoice token resolves only alpha invoice",
            path=f"/customer-invoice/{seed['alpha']['invoice_token']}",
            expect_text=seed["alpha"]["customer_name"],
            forbid_text=seed["beta"]["customer_name"],
            expect_final_path=f"/customer-invoice/{seed['alpha']['invoice_token']}",
        )
    )
    results["public_document_isolation"].append(
        page_result(
            public_client.get(f"/customer-invoice/{seed['beta']['invoice_token']}", follow_redirects=True),
            label="Public beta invoice token resolves only beta invoice",
            path=f"/customer-invoice/{seed['beta']['invoice_token']}",
            expect_text=seed["beta"]["customer_name"],
            forbid_text=seed["alpha"]["customer_name"],
            expect_final_path=f"/customer-invoice/{seed['beta']['invoice_token']}",
        )
    )
    results["public_document_isolation"].append(
        denial_result(
            public_client.get("/customer-invoice/not-a-real-token", follow_redirects=False),
            label="Invalid public invoice token returns not found",
            path="/customer-invoice/not-a-real-token",
            expected_status=404,
        )
    )

    sections = ["admin_supervision", "business_isolation", "worker_boundaries", "public_document_isolation"]
    results["overall_pass"] = all(item["pass"] for section in sections for item in results[section])
    return results


def write_outputs(results: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    counts = {}
    for section in ("admin_supervision", "business_isolation", "worker_boundaries", "public_document_isolation"):
        passed = sum(1 for item in results[section] if item["pass"])
        counts[section] = (passed, len(results[section]))

    lines = [
        "# Phase 2 Access Control and Tenant Isolation Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Result",
        "",
        f"- Admin supervision checks passed: {counts['admin_supervision'][0]}/{counts['admin_supervision'][1]}",
        f"- Business isolation checks passed: {counts['business_isolation'][0]}/{counts['business_isolation'][1]}",
        f"- Worker boundary checks passed: {counts['worker_boundaries'][0]}/{counts['worker_boundaries'][1]}",
        f"- Public document isolation checks passed: {counts['public_document_isolation'][0]}/{counts['public_document_isolation'][1]}",
        f"- Overall pass: {'YES' if results['overall_pass'] else 'NO'}",
        "",
        "## Seeded Tenants",
        "",
        f"- Alpha business: {results['seed']['alpha']['business_name']} ({results['seed']['alpha']['business_email']})",
        f"- Beta business: {results['seed']['beta']['business_name']} ({results['seed']['beta']['business_email']})",
        f"- Alpha worker: {results['seed']['alpha']['worker_name']} ({results['seed']['alpha']['worker_email']})",
        "",
    ]

    for key in ("admin_login", "alpha_login", "beta_login", "worker_login"):
        login_row = results[key]
        lines.extend(
            [
                f"## {key.replace('_', ' ').title()}",
                "",
                f"- Status: {login_row['status_code']}",
                f"- Redirect: {login_row['location']}",
                "",
            ]
        )

    for section in ("admin_supervision", "business_isolation", "worker_boundaries", "public_document_isolation"):
        lines.append(f"## {section.replace('_', ' ').title()}")
        lines.append("")
        for row in results[section]:
            detail = [f"status={row['status_code']}"]
            if "final_path" in row:
                detail.append(f"final={row['final_path']}")
            if "location" in row:
                detail.append(f"location={row['location']}")
            if "expected_text" in row and row["expected_text"]:
                detail.append(f"expected_text_found={row['expected_text_found']}")
            if "forbidden_text" in row and row["forbidden_text"]:
                detail.append(f"forbidden_text_absent={row['forbidden_text_absent']}")
            if "final_path_ok" in row:
                detail.append(f"final_path_ok={row['final_path_ok']}")
            lines.append(f"- {'PASS' if row['pass'] else 'FAIL'} | {row['label']} | {row['path']} | " + " | ".join(detail))
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    prepare_run_dir()
    module = load_app_module()
    seed = seed_verification_baseline(module)
    results = run_phase(module, seed)
    write_outputs(results)
    return 0 if results["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
