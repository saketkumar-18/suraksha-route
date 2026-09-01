"""Start + poll GitHub device flow in one shot (prints user code first)."""
import json
import sys
import time

import requests

CLIENT_ID = "178c6fc778ccc68e1d6a"


def start():
    r = requests.post(
        "https://github.com/login/device/code",
        headers={"Accept": "application/json"},
        data={"client_id": CLIENT_ID, "scope": "repo,read:org,gist,workflow"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def poll(device_code, interval, expires_in):
    deadline = time.time() + expires_in
    net_fails = 0
    while time.time() < deadline:
        time.sleep(interval)
        try:
            r = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                timeout=30,
            )
            net_fails = 0
        except requests.RequestException:
            net_fails += 1
            print(f"network hiccup {net_fails}", flush=True)
            if net_fails >= 10:
                print("FLOW_ERROR: network")
                return False
            continue
        d = r.json()
        if "access_token" in d:
            from pathlib import Path
            Path("gh_token.json").write_text(json.dumps({"token": d["access_token"]}))
            print("LOGIN_COMPLETE")
            return True
        err = d.get("error")
        if err == "authorization_pending":
            print("pending", flush=True)
        elif err == "slow_down":
            interval += 5
        else:
            print("FLOW_ERROR:", err)
            return False
    print("EXPIRED")
    return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "poll":
        flow = json.loads(open("gh_device_flow.json").read())
        sys.exit(0 if poll(flow["device_code"], flow["interval"], flow["expires_in"]) else 1)
    d = start()
    json.dump(
        {"device_code": d["device_code"], "user_code": d["user_code"],
         "interval": d.get("interval", 5), "expires_in": d.get("expires_in", 900)},
        open("gh_device_flow.json", "w"),
    )
    print("=" * 46)
    print("USER CODE:", d["user_code"])
    print("OPEN: https://github.com/login/device")
    print("=" * 46)
