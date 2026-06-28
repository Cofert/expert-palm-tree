from __future__ import annotations
import re
import time
from mailtm import Email

class TempEmail:
    def __init__(self):
        self.email = Email()
        self.address = None

    def create(self) -> str:
        """Create a new inbox and return the email address."""
        self.email.register()
        self.address = self.email.address
        return self.address

    def wait_for_verification_link(self, timeout_s: float = 60.0) -> str | None:
        """Poll inbox for a Roblox verification link."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            messages = self.email.get_messages()
            for msg in messages:
                if "roblox" in msg.subject.lower():
                    full = self.email.get_message(msg.id)
                    # search in both html and plain text
                    content = full.html or full.text
                    match = re.search(r'https://www\.roblox\.com/verify[^\s"\'<>]+', content)
                    if match:
                        return match.group(0)
            time.sleep(2)
        return None
