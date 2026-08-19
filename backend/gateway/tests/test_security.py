import time
import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class SecurityTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first_hash, first_salt = hash_password("correct horse battery staple")
        second_hash, second_salt = hash_password("correct horse battery staple")
        self.assertNotEqual(first_hash, second_hash)
        self.assertNotEqual(first_salt, second_salt)
        self.assertTrue(verify_password("correct horse battery staple", first_hash, first_salt))
        self.assertFalse(verify_password("wrong password", first_hash, first_salt))

    def test_jwt_signature_and_expiry_are_checked(self):
        token, claims = create_access_token("user-1", "hello@example.com", "test-secret", 10)
        decoded = decode_access_token(token, "test-secret")
        self.assertEqual(decoded.user_id, "user-1")
        self.assertEqual(decoded.jti, claims.jti)
        with self.assertRaises(TokenError):
            decode_access_token(token, "other-secret")
        with self.assertRaises(TokenError):
            decode_access_token(token, "test-secret", now=int(time.time()) + 601)


def test_gateway_internal_ready_requires_the_current_model_token(tmp_path):
    settings = replace(
        load_settings(),
        database_path=tmp_path / "ready.db",
        database_url="",
        root_path="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        before = app.state.db.fetch_one(
            "SELECT COUNT(*) AS count FROM user_transaction_events"
        )["count"]
        assert client.get("/v1/health").status_code == 200
        missing = client.get("/v1/internal/ready")
        stale = client.get(
            "/v1/internal/ready",
            headers={"Authorization": "Bearer stale-model-token"},
        )
        accepted = client.get(
            "/v1/internal/ready",
            headers={"Authorization": f"Bearer {settings.model_service_token}"},
        )
        after = app.state.db.fetch_one(
            "SELECT COUNT(*) AS count FROM user_transaction_events"
        )["count"]

    assert missing.status_code == 401
    assert stale.status_code == 401
    assert stale.headers["www-authenticate"] == "Bearer"
    assert accepted.status_code == 200
    assert accepted.json() == {"status": "ready"}
    assert after == before


if __name__ == "__main__":
    unittest.main()
