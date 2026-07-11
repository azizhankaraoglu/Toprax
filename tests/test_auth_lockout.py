"""PR-13 — Login brute-force koruma testleri (auth_lockout.py, saf fonksiyonlar)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import auth_lockout


def _reset():
    auth_lockout._failed_attempts.clear()
    auth_lockout._locked_until.clear()


def test_no_lock_below_threshold():
    _reset()
    for _ in range(4):
        auth_lockout.record_failed_attempt("a@test.com", "1.2.3.4")
    assert auth_lockout.is_locked("a@test.com", "1.2.3.4") == 0


def test_locks_after_threshold():
    _reset()
    for _ in range(5):
        auth_lockout.record_failed_attempt("b@test.com", "1.2.3.4")
    assert auth_lockout.is_locked("b@test.com", "1.2.3.4") > 0


def test_different_ip_not_locked():
    _reset()
    for _ in range(5):
        auth_lockout.record_failed_attempt("c@test.com", "1.2.3.4")
    assert auth_lockout.is_locked("c@test.com", "9.9.9.9") == 0


def test_successful_login_clears_lock():
    _reset()
    for _ in range(5):
        auth_lockout.record_failed_attempt("d@test.com", "1.2.3.4")
    assert auth_lockout.is_locked("d@test.com", "1.2.3.4") > 0
    auth_lockout.record_successful_login("d@test.com", "1.2.3.4")
    assert auth_lockout.is_locked("d@test.com", "1.2.3.4") == 0
