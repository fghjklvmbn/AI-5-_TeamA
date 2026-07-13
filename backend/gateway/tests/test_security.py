import time
import unittest

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


if __name__ == "__main__":
    unittest.main()

