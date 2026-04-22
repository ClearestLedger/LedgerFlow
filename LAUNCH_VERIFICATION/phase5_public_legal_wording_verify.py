from __future__ import annotations

import importlib.util
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\Users\danie\OneDrive\Desktop\folder for codex")
APP_PATH = ROOT / "_live_sync_tmp" / "app.py"
RESET_BUNDLE = Path(r"C:\Users\danie\OneDrive\Desktop\LedgerNew_Render_Migration")
WORK_DIR = ROOT / "LAUNCH_VERIFICATION" / "_phase5_runtime"
RESULTS_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE5_RESULTS.json"
REPORT_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE5_REPORT.md"


def reset_work_dir() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    shutil.copytree(RESET_BUNDLE, WORK_DIR)


def load_app_module():
    os.environ["DATA_DIR"] = str(WORK_DIR)
    os.environ["DATABASE_PATH"] = str(WORK_DIR / "rds_core_web.db")
    os.environ["APP_ENV"] = "production"
    os.environ.pop("AI_GUIDE_VISIBLE", None)
    spec = importlib.util.spec_from_file_location("phase5_public_legal_probe_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_report(results: dict) -> str:
    lines = [
        "# Phase 5 Final Public Legal Wording Report",
        "",
        f"Generated: {results['generated_at']}",
        "",
        "## Result",
        "",
        f"- Checks passed: {results['passed_checks']}/{results['total_checks']}",
        f"- Overall pass: {'YES' if results['overall_pass'] else 'NO'}",
        "",
        "## Detailed checks",
        "",
    ]
    for item in results["checks"]:
        status = "PASS" if item["passed"] else "FAIL"
        lines.append(f"- {status} | {item['label']} | {item['detail']}")
    lines.extend(
        [
            "",
            "## Pass rule",
            "",
            "- This phase passes only if the public legal page includes privacy scope, admin-managed relationship, public-link responsibility, no-guarantee boundaries, contact/request handling, and retention/deletion language.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    reset_work_dir()
    app_module = load_app_module()
    checks: list[dict] = []

    def record(label: str, passed: bool, detail: str) -> None:
        checks.append({"label": label, "passed": passed, "detail": detail})

    with app_module.app.test_client() as client:
        trust = client.get("/trust-and-policies")
        trust_text = trust.get_data(as_text=True)
        record("Trust page loads publicly", trust.status_code == 200, f"status={trust.status_code}")
        record("Privacy section includes payroll/tax data detail", "worker/payroll records" in trust_text and "W-2" in trust_text, "payroll/tax detail present")
        record("Terms section includes admin-managed relationship wording", "onboarding, permissions, billing arrangements" in trust_text, "admin-managed wording present")
        record("Terms section includes customer/public link responsibility", "estimates, invoices, receipts, and public customer links" in trust_text, "public-link responsibility present")
        record("Security section includes no-guarantee boundary", "does not promise uninterrupted availability, guaranteed delivery, guaranteed accuracy, or guaranteed compliance outcomes" in trust_text, "no-guarantee wording present")
        record("Disclaimer section includes no-accuracy/legal-sufficiency boundary", "does not guarantee the completeness, accuracy, or legal sufficiency" in trust_text, "expanded disclaimer present")
        record(
            "Contact section exists",
            ('Contact' in trust_text and 'Requests' in trust_text) or 'id=\"contact\"' in trust_text or "id='contact'" in trust_text,
            "contact section present",
        )
        record("Contact section includes support contact path", "ledgerflowglow@gmail.com" in trust_text or "support contact listed in your LedgerFlow invite" in trust_text, "support contact path present")
        record(
            "Retention section exists",
            ('Retention' in trust_text and 'Deletion' in trust_text) or 'id=\"retention\"' in trust_text or "id='retention'" in trust_text,
            "retention section present",
        )
        record("Retention section includes archive/backup/deletion limits", "Archived or deactivated accounts may be retained" in trust_text and "Backup copies and delivery logs may continue to exist" in trust_text, "retention detail present")

    results = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
        "total_checks": len(checks),
        "passed_checks": sum(1 for item in checks if item["passed"]),
        "overall_pass": all(item["passed"] for item in checks),
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(build_report(results), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH}")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps({"overall_pass": results["overall_pass"], "passed": results["passed_checks"], "total": results["total_checks"]}))


if __name__ == "__main__":
    main()
