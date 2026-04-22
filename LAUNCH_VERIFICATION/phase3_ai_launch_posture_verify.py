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
WORK_DIR = ROOT / "LAUNCH_VERIFICATION" / "_phase3_runtime"
RESULTS_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE3_RESULTS.json"
REPORT_PATH = ROOT / "LAUNCH_VERIFICATION" / "PHASE3_REPORT.md"

ADMIN_EMAIL = "ledgerflowglow@gmail.com"
ADMIN_PASSWORD = "LedgerTemp!2026"


def reset_work_dir() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    shutil.copytree(RESET_BUNDLE, WORK_DIR)


def load_app_module():
    os.environ["DATA_DIR"] = str(WORK_DIR)
    os.environ["DATABASE_PATH"] = str(WORK_DIR / "rds_core_web.db")
    os.environ["APP_ENV"] = "production"
    os.environ.pop("AI_GUIDE_VISIBLE", None)
    spec = importlib.util.spec_from_file_location("phase3_ai_probe_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_report(results: dict) -> str:
    checks = results["checks"]
    lines = [
        "# Phase 3 AI Launch Posture Report",
        "",
        f"Generated: {results['generated_at']}",
        "",
        "## Result",
        "",
        f"- Checks passed: {results['passed_checks']}/{results['total_checks']}",
        f"- Overall pass: {'YES' if results['overall_pass'] else 'NO'}",
        "",
        "## Launch posture",
        "",
        "- Clean launch baseline uses production mode",
        "- AI guide is hidden by default unless explicitly enabled via environment",
        "- AI assistant profile is not configured in the clean reset bundle",
        "- Current launch scope treats AI as out of scope until it is deliberately enabled and red-teamed",
        "",
        "## Detailed checks",
        "",
    ]
    for item in checks:
        status = "PASS" if item["passed"] else "FAIL"
        lines.append(
            f"- {status} | {item['label']} | {item['detail']}"
        )
    lines.extend(
        [
            "",
            "## Release rule",
            "",
            "- Current launch baseline passes this phase only if AI is both hidden and unconfigured in production.",
            "- Any future AI activation must rerun `AI_RED_TEAM_PROMPT_SUITE.md` and complete a dedicated activation review before release.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    reset_work_dir()
    app_module = load_app_module()
    config = app_module.ai_assistant_config()

    checks: list[dict] = []

    def record(label: str, passed: bool, detail: str) -> None:
        checks.append({"label": label, "passed": passed, "detail": detail})

    record(
        "AI guide hidden by default in production",
        app_module.ai_guide_visible() is False,
        f"ai_guide_visible={app_module.ai_guide_visible()}",
    )
    record(
        "AI profile disabled on clean launch baseline",
        config["enabled"] is False,
        f"enabled={config['enabled']}",
    )
    record(
        "AI profile unconfigured on clean launch baseline",
        config["configured"] is False and not config["api_key"],
        f"configured={config['configured']} api_key_present={bool(config['api_key'])}",
    )

    with app_module.app.test_client() as client:
        login_response = client.post(
            "/login",
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            follow_redirects=False,
        )
        login_location = login_response.headers.get("Location", "")
        record(
            "Admin login still routes through legal gate first",
            login_response.status_code == 302 and "/legal-acceptance" in login_location,
            f"status={login_response.status_code} location={login_location}",
        )

        acceptance = client.post(
            "/legal-acceptance",
            data={
                "accept_terms": "1",
                "accept_privacy": "1",
                "next": "/cpa-dashboard",
            },
            follow_redirects=False,
        )
        acceptance_location = acceptance.headers.get("Location", "")
        record(
            "Admin can complete legal acceptance and continue",
            acceptance.status_code == 302 and acceptance_location == "/cpa-dashboard",
            f"status={acceptance.status_code} location={acceptance_location}",
        )

        dashboard = client.get("/cpa-dashboard", follow_redirects=False)
        dashboard_text = dashboard.get_data(as_text=True)
        record(
            "Admin dashboard does not expose AI settings link in launch baseline",
            dashboard.status_code == 200 and "/ai-guide-settings" not in dashboard_text,
            f"status={dashboard.status_code} ai_link_present={'/ai-guide-settings' in dashboard_text}",
        )

        hidden_settings = client.get("/ai-guide-settings", follow_redirects=False)
        record(
            "AI settings route stays hidden for admin in production launch posture",
            hidden_settings.status_code == 404,
            f"status={hidden_settings.status_code}",
        )

        assistant_response = client.post(
            "/assistant/respond",
            json={"question": "Should I file my taxes this way?"},
            follow_redirects=False,
        )
        assistant_json = assistant_response.get_json(silent=True) or {}
        record(
            "AI response endpoint is unavailable in launch baseline",
            assistant_response.status_code == 404 and assistant_json.get("ok") is False,
            f"status={assistant_response.status_code} error={assistant_json.get('error', '')}",
        )

    results = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
        "total_checks": len(checks),
        "passed_checks": sum(1 for item in checks if item["passed"]),
        "overall_pass": all(item["passed"] for item in checks),
        "launch_posture": {
            "ai_guide_visible": app_module.ai_guide_visible(),
            "ai_enabled": config["enabled"],
            "ai_configured": config["configured"],
            "provider": config["provider"],
            "model": config["model"],
        },
    }

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(build_report(results), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH}")
    print(f"Wrote {REPORT_PATH}")
    print(json.dumps({"overall_pass": results["overall_pass"], "passed": results["passed_checks"], "total": results["total_checks"]}))


if __name__ == "__main__":
    main()
