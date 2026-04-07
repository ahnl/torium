"""
One-time Tori.fi authentication setup.

On macOS: registers a temporary URL scheme handler via AppleScript, opens the
browser for login, and captures the redirect automatically.

On Windows/Linux (or with manual=True): opens the browser for login. After
logging in, the browser will show a "can't open" error. Copy the full URL
from the address bar and paste it into the terminal.
"""

import base64, hashlib, hmac, json, os, secrets, shutil, subprocess, sys, time
import urllib.parse, webbrowser

import requests

CLIENT_ID = "6079834b9b0b741812e7e91f"
SPID_SERVER_CLIENT_ID = "650421cf50eeae31ecd2a2d3"
REDIRECT_URI = f"fi.tori.www.{CLIENT_ID}://login"
SIGNING_KEY = b"3b535f36-79be-424b-a6fd-116c6e69f137"
CALLBACK_FILE = "/tmp/tori_auth_callback.txt"
APP_PATH = os.path.expanduser("~/Applications/ToriAuthHelper.app")
LSREG = ("/System/Library/Frameworks/CoreServices.framework"
         "/Frameworks/LaunchServices.framework/Support/lsregister")


def _gw_key(method, path, service="", body=b""):
    msg = f"{method.upper()};{path};{service};".encode() + body
    return base64.b64encode(hmac.new(SIGNING_KEY, msg, hashlib.sha512).digest()).decode()


def _register_url_handler():
    """Compile a tiny AppleScript app that writes the callback URL to a file. macOS only."""
    script = f"""
on open location theURL
    set f to open for access POSIX file "{CALLBACK_FILE}" with write permission
    write theURL to f
    close access f
end open location
"""
    os.makedirs(os.path.dirname(APP_PATH), exist_ok=True)
    shutil.rmtree(APP_PATH, ignore_errors=True)
    script_file = "/tmp/tori_handler.applescript"
    with open(script_file, "w") as f:
        f.write(script)
    result = subprocess.run(["osacompile", "-o", APP_PATH, script_file], capture_output=True)
    os.remove(script_file)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode())

    plist_path = os.path.join(APP_PATH, "Contents", "Info.plist")
    url_types = json.dumps([{"CFBundleURLSchemes": [f"fi.tori.www.{CLIENT_ID}"]}])
    r = subprocess.run(["plutil", "-insert", "CFBundleURLTypes", "-json", url_types,
        plist_path], capture_output=True)
    if r.returncode != 0:
        subprocess.run(["plutil", "-replace", "CFBundleURLTypes", "-json", url_types,
            plist_path], check=True, capture_output=True)

    subprocess.run([LSREG, "-f", APP_PATH], check=True, capture_output=True)
    time.sleep(2)


def _get_tori_token(refresh_token: str) -> tuple[str, str]:
    """Returns (tori_bearer, new_refresh_token)."""
    r1 = requests.post("https://login.vend.fi/oauth/token",
        headers={"X-OIDC": "v1"},
        data={"client_id": CLIENT_ID, "grant_type": "refresh_token",
              "refresh_token": refresh_token})
    r1.raise_for_status()
    access_token = r1.json()["access_token"]
    new_refresh = r1.json()["refresh_token"]

    r2 = requests.post("https://login.vend.fi/api/2/oauth/exchange",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"clientId": SPID_SERVER_CLIENT_ID, "type": "code"})
    r2.raise_for_status()
    spid_code = r2.json()["data"]["code"]

    body = json.dumps({"spidCode": spid_code, "deviceId": CLIENT_ID}).encode()
    r3 = requests.post("https://apps-gw-poc.svc.tori.fi/public/login",
        headers={"finn-gw-key": _gw_key("POST", "/public/login", "LOGIN-SERVER-AUTH", body),
                 "finn-gw-service": "LOGIN-SERVER-AUTH",
                 "content-type": "application/json",
                 "user-agent": "ToriApp_iOS/26.16.0-26903"},
        data=body)
    r3.raise_for_status()
    return r3.json()["token"]["value"], new_refresh


def main(manual: bool = False) -> None:
    from tori.auth import save_credentials

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    auth_url = "https://login.vend.fi/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": "openid offline_access",
        "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state, "nonce": secrets.token_urlsafe(16),
    })

    handler_registered = False
    if sys.platform == "darwin" and not manual:
        try:
            if os.path.exists(CALLBACK_FILE):
                os.remove(CALLBACK_FILE)
            _register_url_handler()
            handler_registered = True
        except Exception as e:
            print(f"Warning: could not register URL handler: {e}")

    print(f"\n{auth_url}\n")
    webbrowser.open(auth_url)

    if handler_registered:
        print("Log in to Tori.fi in the browser. Waiting for redirect...")
        for _ in range(120):
            time.sleep(1)
            if os.path.exists(CALLBACK_FILE):
                break
        else:
            print("Timed out waiting for login.")
            sys.exit(1)
        with open(CALLBACK_FILE) as f:
            callback_url = f.read().strip()
        os.remove(CALLBACK_FILE)
    else:
        print("Log in to Tori.fi in the browser.")
        print("After login, the browser will show a 'can't open this page' error.")
        print("Copy the full URL from the address bar and paste it here.")
        callback_url = input("Redirect URL: ").strip()

    print(f"Got callback: {callback_url[:80]}...")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)

    if "error" in qs:
        print(f"Login error: {qs['error'][0]}")
        sys.exit(1)
    if qs.get("state", [None])[0] != state:
        print("State mismatch. Aborting.")
        sys.exit(1)

    code = qs["code"][0]
    print("Exchanging code for tokens...")

    r = requests.post("https://login.vend.fi/oauth/token",
        headers={"X-OIDC": "v1"},
        data={"client_id": CLIENT_ID, "grant_type": "authorization_code",
              "code": code, "redirect_uri": REDIRECT_URI, "code_verifier": verifier})
    r.raise_for_status()
    refresh_token = r.json()["refresh_token"]

    print("Getting tori Bearer token...")
    bearer, new_refresh = _get_tori_token(refresh_token)

    save_credentials(new_refresh)
    print("\n✓ Done! Credentials saved to ~/.config/tori/credentials.json")
    print(f"\nrefresh_token (valid ~1 year):\n{new_refresh}")
    print(f"\ntori Bearer (valid ~1h):\n{bearer}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tori.fi one-time auth setup")
    parser.add_argument("--manual", action="store_true",
                        help="skip URL handler registration and paste redirect URL manually")
    args = parser.parse_args()
    main(manual=args.manual)
