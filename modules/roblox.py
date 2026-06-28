def signup_with_email(
    self,
    username: str,
    password: str,
    birthday_iso: str,
    gender: int,
    email: str,
) -> tuple[RobloxChallenge | None, dict]:
    """
    Signup with email included. Returns (challenge, response_json).
    If challenge is None, signup succeeded (no captcha required).
    """
    body = {
        "username": username,
        "password": password,
        "birthday": birthday_iso,
        "gender": gender,
        "email": email,
        "isTosAgreementBoxChecked": True,
        "agreementIds": [
            "306cc852-3717-4996-93e7-086daafd42f6",
            "2ba6b930-4ba8-4085-9e8c-24b919701f15",
        ],
    }
    resp = self.client._session.post(
        f"{AUTH_URL}/v2/signup?urlLocale=en_us",
        json=body,
        headers=self._auth_headers(),
        timeout=30,
    )
    # Handle CSRF token refresh
    new_csrf = resp.headers.get("x-csrf-token")
    if new_csrf and new_csrf != self.csrf_token:
        self.csrf_token = new_csrf
        resp = self.client._session.post(
            f"{AUTH_URL}/v2/signup?urlLocale=en_us",
            json=body,
            headers=self._auth_headers(),
            timeout=30,
        )

    if resp.status_code == 200:
        return None, resp.json()

    # Check for challenge
    challenge_id = resp.headers.get("rblx-challenge-id")
    challenge_type = resp.headers.get("rblx-challenge-type")
    challenge_meta_b64 = resp.headers.get("rblx-challenge-metadata")

    if challenge_id and challenge_type == "captcha" and challenge_meta_b64:
        meta = json.loads(base64.b64decode(challenge_meta_b64).decode())
        challenge = self._parse_captcha_challenge(challenge_id, meta)
        return challenge, resp.json()

    raise RobloxError(f"signup failed {resp.status_code}: {resp.text[:200]}")
