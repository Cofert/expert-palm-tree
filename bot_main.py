#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import discord
from discord import app_commands
import os
import random
import time
import json
import base64
from queue import Queue
from threading import Lock
from dataclasses import dataclass
from typing import Any
import requests as req

# Local modules
from modules.http import HttpClient
from modules.roblox import RobloxAuth, RobloxError
from modules.solvex_client import SolvexClient, SolverError
from modules.email_client import TempEmail
from modules.logger import C, c
from proxy_fetcher import fetch_webshare_proxies   # <-- new

# ─── config ──────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN environment variable not set")

SOLVEX_KEY = os.environ.get("SOLVEX_API_KEY") or os.environ.get("NOPECHA_API_KEY")
if not SOLVEX_KEY:
    raise RuntimeError("Captcha API key not set (SOLVEX_API_KEY or NOPECHA_API_KEY)")

DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", 0))  # set this!
if not DISCORD_CHANNEL_ID:
    print("⚠️ DISCORD_CHANNEL_ID not set – embeds will not be sent.")

# Proxy mode: "webshare" | "pool" | "none"
PROXY_MODE = os.environ.get("PROXY_MODE", "none").lower()
WEBSHARE_API_KEY = os.environ.get("WEBSHARE_API_KEY")
WEBSHARE_PROXY_LIMIT = int(os.environ.get("WEBSHARE_PROXY_LIMIT", 10))

# ─── helpers ──────────────────────────────────────────────────────────
def gen_password() -> str:
    import string
    chars = (random.choices(string.ascii_lowercase, k=6) +
             random.choices(string.ascii_uppercase, k=3) +
             random.choices(string.digits, k=3) +
             random.choices("!_-", k=1))
    random.shuffle(chars)
    return "".join(chars)

def gen_birthday() -> str:
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc)
    age = random.randint(16, 40)
    year = today.year - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}T22:00:00.000Z"

def gen_gender() -> int:
    return random.choices([1, 2, 3], weights=[45, 45, 10])[0]

def gen_username() -> str:
    adj = ["Swift","Brave","Clever","Epic","Fuzzy","Glitch","Hyper","Jolly",
           "Keen","Lucky","Mystic","Neon","Orbit","Pixel","Quirky","Rapid",
           "Savage","Turbo","Ultra","Vivid","Wild","Zen"]
    noun = ["Arrow","Blaze","Comet","Dash","Echo","Falcon","Glide","Hawk",
            "Ion","Jet","King","Lynx","Max","Nova","Owl","Pulse","Quest",
            "Raven","Spark","Titan","Viper","Wolf"]
    suffix = "".join(random.choices("0123456789abcdef", k=4))
    return f"{random.choice(adj)}{random.choice(noun)}{suffix}"[:20]

# ─── proxy pool ──────────────────────────────────────────────────
proxy_pool = []
proxy_lock = Lock()
proxy_index = 0

def init_proxies():
    global proxy_pool
    if PROXY_MODE == "webshare":
        if WEBSHARE_API_KEY:
            proxy_pool = fetch_webshare_proxies(WEBSHARE_API_KEY, WEBSHARE_PROXY_LIMIT)
            if not proxy_pool:
                print("⚠️ No proxies from Webshare – falling back to none.")
                return False
            print(f"✅ Loaded {len(proxy_pool)} proxies from Webshare.")
            return True
        else:
            print("⚠️ WEBSHARE_API_KEY not set – falling back to none.")
            return False
    elif PROXY_MODE == "pool":
        proxy_file = os.environ.get("PROXY_FILE", "input/proxies.txt")
        try:
            with open(proxy_file, "r") as f:
                proxy_pool = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            print(f"✅ Loaded {len(proxy_pool)} proxies from {proxy_file}.")
            return True
        except:
            print(f"⚠️ Could not read {proxy_file} – falling back to none.")
            return False
    else:
        print("ℹ️ Proxy mode set to none – direct connection.")
        return True

def get_next_proxy() -> str | None:
    if not proxy_pool:
        return None
    with proxy_lock:
        global proxy_index
        proxy = proxy_pool[proxy_index % len(proxy_pool)]
        proxy_index += 1
        return proxy

# ─── account creation logic ─────────────────────────────────────
def create_account_sync(
    solver: SolvexClient,
    username: str | None,
    verify_email: bool,
    proxy: str | None = None,
) -> dict[str, Any]:
    """
    Returns dict with keys:
        success: bool
        username: str
        password: str
        email: str | None
        user_id: int | None
        cookie: str | None
        error: str | None
    """
    if not username:
        username = gen_username()

    password = gen_password()
    birthday = gen_birthday()
    gender = gen_gender()
    email_addr = None
    temp_email = None

    if verify_email:
        temp_email = TempEmail()
        email_addr = temp_email.create()

    # browser profile – chrome
    profile = {
        "impersonate": "chrome146",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "accept_language": "en-US,en;q=0.9",
        "sec_ch_ua": '"Chromium";v="146", "Not?A_Brand";v="24", "Google Chrome";v="146"',
        "sec_ch_ua_platform": '"Windows"',
        "sec_ch_ua_mobile": "?0",
    }

    client = HttpClient(proxy=proxy, impersonate=profile["impersonate"])
    auth = RobloxAuth(
        client=client,
        user_agent=profile["user_agent"],
        accept_language=profile["accept_language"],
        sec_ch_ua=profile["sec_ch_ua"],
        sec_ch_ua_platform=profile["sec_ch_ua_platform"],
        sec_ch_ua_mobile=profile["sec_ch_ua_mobile"],
    )

    try:
        auth.warmup_signup_page()
        challenge, resp_data = auth.signup_with_email(username, password, birthday, gender, email_addr or "")
    except RobloxError as e:
        client.close()
        return {"success": False, "error": f"RobloxError: {e}", "username": username, "password": password, "email": email_addr, "user_id": None, "cookie": None}

    # No challenge → account created
    if challenge is None:
        jar = client._session.cookies
        cookie_str = "; ".join(f"{k}={v}" for k, v in jar.items())
        user_id = resp_data.get("userId") if resp_data else None
        client.close()
        return {"success": True, "username": username, "password": password, "email": email_addr, "user_id": user_id, "cookie": cookie_str, "error": None}

    # Solve captcha
    try:
        ARKOSE_PK = "A2A14B1D-1AF3-C791-9BBC-EE33CC7A0A6F"
        ARKOSE_SURL = "https://arkoselabs.roblox.com"
        ROBLOX_SITE = "https://www.roblox.com"

        arkose_resp = solver.arkose(
            public_key=ARKOSE_PK,
            surl=ARKOSE_SURL,
            site=ROBLOX_SITE,
            blob=challenge.blob,
            cookies=challenge.cookies,
            proxy=proxy,
            location_href="https://www.roblox.com/CreateAccount",
            referrer="https://www.roblox.com/CreateAccount",
            solve_pow=False,
            user_agent=profile["user_agent"],
        )
        if arkose_resp.get("status") != "done":
            client.close()
            return {"success": False, "error": f"Captcha failed: {arkose_resp.get('error')}", "username": username, "password": password, "email": email_addr, "user_id": None, "cookie": None}

        token = arkose_resp["token"]
        auth.submit_arkose_token(token)

        meta_b64 = base64.b64encode(json.dumps({
            "unifiedCaptchaId": challenge.unified_captcha_id,
            "captchaToken": token,
        }).encode()).decode()
        body = {
            "username": username,
            "password": password,
            "birthday": birthday,
            "gender": gender,
            "email": email_addr or "",
            "isTosAgreementBoxChecked": True,
            "agreementIds": ["306cc852-3717-4996-93e7-086daafd42f6", "2ba6b930-4ba8-4085-9e8c-24b919701f15"],
        }
        headers = {
            **auth._auth_headers(),
            "Content-Type": "application/json;charset=utf-8",
            "rblx-challenge-id": challenge.challenge_id,
            "rblx-challenge-type": "captcha",
            "rblx-challenge-metadata": meta_b64,
        }
        final_resp = client._session.post(
            "https://auth.roblox.com/v2/signup?urlLocale=en_us",
            json=body,
            headers=headers,
            timeout=30,
        )
        if final_resp.status_code != 200:
            client.close()
            return {"success": False, "error": f"Final signup failed: {final_resp.text[:200]}", "username": username, "password": password, "email": email_addr, "user_id": None, "cookie": None}

        jar = client._session.cookies
        cookie_str = "; ".join(f"{k}={v}" for k, v in jar.items())
        user_id = final_resp.json().get("userId") if final_resp.json() else None
        client.close()

        if verify_email and temp_email and email_addr:
            link = temp_email.wait_for_verification_link(timeout_s=60)
            if link:
                try:
                    req.get(link, timeout=10)
                except:
                    pass

        return {"success": True, "username": username, "password": password, "email": email_addr, "user_id": user_id, "cookie": cookie_str, "error": None}

    except Exception as e:
        client.close()
        return {"success": False, "error": f"Exception: {e}", "username": username, "password": password, "email": email_addr, "user_id": None, "cookie": None}

# ─── Discord bot ──────────────────────────────────────────────────

class AccountBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.solver = SolvexClient(api_key=SOLVEX_KEY)
        self._background_task = None

    async def setup_hook(self):
        await self.tree.sync()
        self._background_task = self.loop.create_task(self.process_queue())

    async def process_queue(self):
        while True:
            if not job_queue.empty():
                job = job_queue.get()
                await self.execute_job(job)
            await asyncio.sleep(0.5)

    async def execute_job(self, job):
        user_id = job["user_id"]
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                create_account_sync,
                self.solver,
                job.get("username"),
                job.get("verify_email", False),
                get_next_proxy(),
            )
            # Send DM to user
            user = await self.fetch_user(user_id)
            if result["success"]:
                msg = f"✅ Account created!\nUsername: `{result['username']}`\nPassword: `{result['password']}`"
                if result.get("email"):
                    msg += f"\nEmail: `{result['email']}`"
                await user.send(msg)

                # Send embed to configured channel
                await self.send_account_embed(result)
            else:
                await user.send(f"❌ Failed: {result['error']}\nUsername: `{result['username']}`")
        except Exception as e:
            try:
                user = await self.fetch_user(user_id)
                await user.send(f"⚠️ Something went wrong: {e}")
            except:
                pass

    async def send_account_embed(self, account_info: dict):
        """Send a rich embed to DISCORD_CHANNEL_ID with account details."""
        if not DISCORD_CHANNEL_ID:
            return
        channel = self.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.fetch_channel(DISCORD_CHANNEL_ID)
            except:
                print(f"❌ Could not find channel {DISCORD_CHANNEL_ID}")
                return

        embed = discord.Embed(
            title="🎮 New Roblox Account",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Username", value=f"`{account_info['username']}`", inline=True)
        embed.add_field(name="Password", value=f"`{account_info['password']}`", inline=True)
        if account_info.get("email"):
            embed.add_field(name="Email", value=f"`{account_info['email']}`", inline=True)
        embed.add_field(name="Cookie (`.ROBLOSECURITY`)", value=f"```\n{account_info.get('cookie', 'N/A')}\n```", inline=False)

        # Fetch profile picture from Roblox API
        if account_info.get("user_id"):
            avatar_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={account_info['user_id']}&width=420&height=420&format=png"
            embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="User ID", value=f"`{account_info['user_id']}`", inline=True)

        embed.set_footer(text="Generated by Account Creator Bot")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send embed: {e}")

    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        # Initialize proxies
        init_proxies()

# ─── job queue ──────────────────────────────────────────────────
job_queue = Queue()

# ─── Slash commands ──────────────────────────────────────────────

bot = AccountBot()

@bot.tree.command(name="create", description="Create an account with a custom username (email verification optional)")
@app_commands.describe(username="Desired Roblox username", verify_email="Verify email after creation?")
async def create_cmd(interaction: discord.Interaction, username: str, verify_email: bool = False):
    await interaction.response.defer(ephemeral=True)
    job = {
        "user_id": interaction.user.id,
        "username": username,
        "verify_email": verify_email,
    }
    job_queue.put(job)
    await interaction.followup.send(f"Queued account `{username}` (email verification: {verify_email}). You'll get a DM when done.")

@bot.tree.command(name="create_bulk", description="Create multiple random accounts (max 5)")
@app_commands.describe(count="Number of accounts to create (1-5)")
async def create_bulk_cmd(interaction: discord.Interaction, count: int):
    if count < 1 or count > 5:
        await interaction.response.send_message("Count must be between 1 and 5.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    for _ in range(count):
        job = {
            "user_id": interaction.user.id,
            "username": None,  # random
            "verify_email": False,
        }
        job_queue.put(job)
    await interaction.followup.send(f"Queued {count} random accounts. You'll get DMs when each is done.")

@bot.tree.command(name="status", description="Check pending jobs")
async def status_cmd(interaction: discord.Interaction):
    qsize = job_queue.qsize()
    await interaction.response.send_message(f"Jobs in queue: {qsize}", ephemeral=True)

# ─── run ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)y
