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
WORK_DIR = ROOT / "LAUNCH_VERIFICATION" / "_phase4_runtime"
RESULTS_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE4_RESULTS.json"
REPORT_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE4_REPORT.md"


def reset_work_dir() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    shutil.copytree(RESET_BUNDLE, WORK_DIR)


def load_app_module():
    os.environ["DATA_DIR"] = str(WORK_DIR)
    os.environ["DATABASE_PATH"] = str(WORK_DIR / "rds_core_web.db")
    os.environ["APP_ENV"] = "production"
    os.environ.pop("AI_GUIDE_VISIBLE", None)
    spec = importlib.util.spec_from_file_location("phase4_privacy_vendor_probe_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_report(results: dict) -> str:
    lines = [
        "# Phase 4 Privacy and Vendor Legal Page Signoff Report",
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
            "## Signoff rule",
            "",
            "- This phase passes only if the public Trust page reflects the current launch-baseline reality for privacy, vendors, billing boundaries, and AI posture.",
            "- Login and create-account entry points must still expose Terms/Privacy access before or during first use.",
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
        record("Trust page shows Privacy Notice section", "Privacy Notice" in trust_text, "Privacy Notice present")
        record("Trust page shows Terms of Use section", "Terms of Use" in trust_text, "Terms of Use present")
        record("Trust page shows Disclaimer section", "Disclaimer" in trust_text, "Disclaimer present")
        record("Trust page discloses Render hosting", "Render" in trust_text, "Render disclosure present")
        record("Trust page discloses Gmail SMTP baseline", "Gmail SMTP" in trust_text, "Gmail SMTP disclosure present")
        record(
            "Trust page discloses hosted billing boundary",
            "external hosted billing processor selected by the administrator" in trust_text,
            "Hosted billing boundary present",
        )
        record(
            "Trust page discloses AI launch posture",
            "optional AI guide is not active in the current launch baseline" in trust_text,
            "AI launch posture present",
        )

        login = client.get("/login")
        login_text = login.get_data(as_text=True)
        record(
            "Login page links to Trust/Terms/Privacy",
            trust.status_code == 200 and "#terms" in login_text and "#privacy" in login_text,
            "Login links to terms/privacy present",
        )

        create_account = client.get("/create-account")
        create_text = create_account.get_data(as_text=True)
        record(
            "Create-account page links to Terms/Privacy",
            create_account.status_code == 200 and "#terms" in create_text and "#privacy" in create_text,
            f"status={create_account.status_code}",
        )

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
