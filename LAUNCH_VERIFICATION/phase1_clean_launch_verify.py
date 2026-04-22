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
RUN_DIR = ROOT / "_tmp_phase1_clean_launch_verification"
RUN_DATA_DIR = RUN_DIR / "data"
RESULTS_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE1_RESULTS.json"
REPORT_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE1_REPORT.md"

ADMIN_EMAIL = "ledgerflowglow@gmail.com"
ADMIN_PASSWORD = "LedgerTemp!2026"
BUSINESS_EMAIL = "phase1demo@ledgerflow.local"
BUSINESS_PASSWORD = "Phase1Demo!2026"


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
    module_name = f"ledgerflow_phase1_verify_{int(datetime.now().timestamp())}"
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("Could not load LedgerFlow app module for verification.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def seed_demo_business(module) -> dict:
    now = datetime.now().replace(microsecond=0)
    now_iso = now.isoformat(timespec="seconds")
    tomorrow = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
    tomorrow_end = tomorrow + timedelta(hours=4)
    with sqlite3.connect(RUN_DATA_DIR / "rds_core_web.db") as conn:
        conn.row_factory = sqlite3.Row
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
                "Phase 1 Demo Painting LLC",
                "LLC",
                "Painting",
                "Interior repaint and recurring touch-up work",
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
                "Danielle Demo",
                "9415550101",
                BUSINESS_EMAIL,
                "3934 Brookside Dr, Sarasota, FL 34231",
                "Phase 1 launch verification demo business.",
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
                BUSINESS_EMAIL,
                generate_password_hash(BUSINESS_PASSWORD),
                "Danielle Demo",
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
                "Sarah Bennett",
                "sarah.bennett@example.com",
                "9415550110",
                "101 Harbor View Dr, Sarasota, FL 34236",
                "Weekly repaint touch-up client for launch verification.",
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
                "Harbor View Residence",
                "101 Harbor View Dr",
                "Sarasota",
                "FL",
                "34236",
                "Call on arrival.",
                "Primary demo service location.",
                now_iso,
                now_iso,
            ),
        )
        service_location_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        conn.execute(
            """
            INSERT INTO workers (
                client_id, name, worker_type, phone, email, preferred_language, hire_date, pay_notes, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                client_id,
                "Miguel Demo",
                "1099",
                "9415550111",
                "miguel.demo@example.com",
                "en",
                now.date().isoformat(),
                "Launch verification worker record.",
                now_iso,
            ),
        )
        worker_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        service_type = conn.execute(
            "SELECT id, name FROM service_types WHERE client_id=? AND lower(name)=lower(?) ORDER BY id LIMIT 1",
            (client_id, "Painting"),
        ).fetchone()
        service_type_id = int(service_type["id"]) if service_type else None

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
                "Harbor View Interior Touch-Up",
                "Sarah Bennett",
                "HB-001",
                service_type["name"] if service_type else "Painting",
                "high",
                "scheduled",
                "not_started",
                "101 Harbor View Dr",
                "Sarasota",
                "FL",
                "34236",
                tomorrow.isoformat(timespec="seconds"),
                tomorrow_end.isoformat(timespec="seconds"),
                240,
                1800.00,
                250.00,
                420.00,
                85.00,
                "Demo job for dispatch, agenda, team, and owner-view verification.",
                "Bring trim brushes and touch-up kit.",
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
                invoice_total_amount, paid_amount, invoice_date, due_date, invoice_status, notes, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                client_id,
                job_id,
                "customer_invoice",
                "Harbor View Touch-Up Invoice",
                "Sarah Bennett",
                "sarah.bennett@example.com",
                "101 Harbor View Dr, Sarasota, FL 34236",
                1800.00,
                900.00,
                now.date().isoformat(),
                (now.date() + timedelta(days=14)).isoformat(),
                "sent",
                "Phase 1 verification invoice.",
                now_iso,
            ),
        )

        module.ops_log_activity(
            conn,
            client_id=client_id,
            job_id=job_id,
            actor_type="business_user",
            actor_id=business_user_id,
            event_type="job_seeded",
            event_text="Phase 1 launch verification seeded operational records.",
        )
        conn.commit()
    return {
        "client_id": client_id,
        "business_user_id": business_user_id,
        "worker_id": worker_id,
        "job_id": job_id,
        "customer_contact_id": customer_contact_id,
        "service_location_id": service_location_id,
    }


def login(client, email: str, password: str) -> dict:
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
        legal_post = client.post(
            "/legal-acceptance",
            data={"accept_terms": "1", "accept_privacy": "1", "next": next_path},
            follow_redirects=False,
        )
        response = legal_post
        location = response.headers.get("Location", "")
    return {
        "status_code": response.status_code,
        "location": location,
        "ok": response.status_code in {302, 303},
    }


def check_route(client, label: str, path: str, marker: str) -> dict:
    response = client.get(path, follow_redirects=True)
    body = response.get_data(as_text=True)
    body_plain = html.unescape(body).lower()
    marker_found = marker.lower() in body_plain
    internal_error = "internal server error" in body_plain
    return {
        "label": label,
        "path": path,
        "status_code": response.status_code,
        "final_path": response.request.path if response.request else "",
        "marker": marker,
        "marker_found": marker_found,
        "internal_error": internal_error,
        "pass": response.status_code == 200 and marker_found and not internal_error,
    }


def build_route_sets(client_id: int) -> dict[str, list[tuple[str, str, str]]]:
    return {
        "admin_supervised": [
            ("Administrator Dashboard", "/cpa-dashboard", "Administrator Dashboard"),
            ("Business Owner View", f"/dashboard?client_id={client_id}", "Owner View"),
            ("Business Welcome Center", f"/welcome-center?client_id={client_id}", "Welcome Center"),
            ("Billing Center", f"/business-payments?client_id={client_id}", "Billing Center"),
            ("Jobs", f"/jobs?client_id={client_id}", "Jobs"),
            ("Dispatch", f"/dispatch?client_id={client_id}", "Dispatch"),
            ("Agenda", f"/agenda?client_id={client_id}", "Schedule"),
            ("Team", f"/team?client_id={client_id}", "Team"),
            ("Availability", f"/availability?client_id={client_id}", "Availability"),
            ("Activity", f"/activity?client_id={client_id}", "Activity"),
            ("Locations", f"/locations?client_id={client_id}", "Locations"),
            ("Templates", f"/templates?client_id={client_id}", "Templates"),
            ("Clients and Sales", f"/clients-sales?client_id={client_id}", "Clients & Sales"),
            ("Reports", f"/reports?client_id={client_id}", "Reports"),
            ("Summary", f"/summary?client_id={client_id}", "Summary"),
        ],
        "business_workspace": [
            ("Owner View", "/dashboard", "Owner View"),
            ("Welcome Center", "/welcome-center", "Welcome Center"),
            ("Billing Center", "/business-payments", "Billing Center"),
            ("Jobs", "/jobs", "Jobs"),
            ("Dispatch", "/dispatch", "Dispatch"),
            ("Agenda", "/agenda", "Schedule"),
            ("Team", "/team", "Team"),
            ("Availability", "/availability", "Availability"),
            ("Activity", "/activity", "Activity"),
            ("Locations", "/locations", "Locations"),
            ("Templates", "/templates", "Templates"),
            ("Clients and Sales", "/clients-sales", "Clients & Sales"),
            ("Reports", "/reports", "Reports"),
            ("Summary", "/summary", "Summary"),
        ],
    }


def write_report(results: dict) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin_ok = sum(1 for item in results["admin_supervised"] if item["pass"])
    business_ok = sum(1 for item in results["business_workspace"] if item["pass"])
    report_lines = [
        "# Phase 1 Clean Launch Verification Report",
        "",
        f"Generated: {timestamp}",
        "",
        "## Result",
        "",
        f"- Admin supervised routes passed: {admin_ok}/{len(results['admin_supervised'])}",
        f"- Business workspace routes passed: {business_ok}/{len(results['business_workspace'])}",
        f"- Overall pass: {'YES' if results['overall_pass'] else 'NO'}",
        "",
        "## Seeded Demo Records",
        "",
        f"- Business: Phase 1 Demo Painting LLC",
        f"- Business login: {BUSINESS_EMAIL}",
        f"- Job ID: {results['seed']['job_id']}",
        f"- Worker ID: {results['seed']['worker_id']}",
        f"- Customer contact ID: {results['seed']['customer_contact_id']}",
        "",
        "## Admin Login",
        "",
        f"- Status: {results['admin_login']['status_code']}",
        f"- Redirect: {results['admin_login']['location']}",
        "",
        "## Business Login",
        "",
        f"- Status: {results['business_login']['status_code']}",
        f"- Redirect: {results['business_login']['location']}",
        "",
        "## Route Results",
        "",
    ]
    for section_name in ("admin_supervised", "business_workspace"):
        report_lines.append(f"### {section_name.replace('_', ' ').title()}")
        report_lines.append("")
        for row in results[section_name]:
            report_lines.append(
                f"- {'PASS' if row['pass'] else 'FAIL'} | {row['label']} | {row['path']} | "
                f"status={row['status_code']} | final={row['final_path']} | marker={row['marker_found']}"
            )
        report_lines.append("")
    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")


def main() -> int:
    prepare_run_dir()
    module = load_app_module()
    seed = seed_demo_business(module)

    admin_client = module.app.test_client()
    business_client = module.app.test_client()

    admin_login = login(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    business_login = login(business_client, BUSINESS_EMAIL, BUSINESS_PASSWORD)

    route_sets = build_route_sets(seed["client_id"])
    admin_results = [check_route(admin_client, *route) for route in route_sets["admin_supervised"]]
    business_results = [check_route(business_client, *route) for route in route_sets["business_workspace"]]

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reset_bundle_dir": str(RESET_BUNDLE_DIR),
        "run_data_dir": str(RUN_DATA_DIR),
        "admin_login": admin_login,
        "business_login": business_login,
        "seed": seed,
        "admin_supervised": admin_results,
        "business_workspace": business_results,
        "overall_pass": admin_login["ok"]
        and business_login["ok"]
        and all(item["pass"] for item in admin_results + business_results),
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results)
    return 0 if results["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
