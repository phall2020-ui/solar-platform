import importlib.util
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

NOTION_SYNC_SPEC = importlib.util.spec_from_file_location("notion_sync", MODULE_DIR / "notion_sync.py")
notion_sync = importlib.util.module_from_spec(NOTION_SYNC_SPEC)
assert NOTION_SYNC_SPEC and NOTION_SYNC_SPEC.loader
NOTION_SYNC_SPEC.loader.exec_module(notion_sync)


def test_parse_args_email_dry_run_implies_send(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["notion_sync.py", "--email-dry-run"])
    args = notion_sync.parse_args()
    assert args.email_dry_run is True
    assert args.send_email_summary is True


def test_send_summary_email_dry_run_prints_email(capsys):
    ok = notion_sync.send_summary_email(
        subject="Sync test",
        body="Dry-run body",
        smtp_server="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        use_tls=True,
        from_email="",
        to_emails=[],
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert ok is True
    assert "--- EMAIL TEST (dry-run) ---" in out
    assert "Subject: Sync test" in out
    assert "Dry-run body" in out
