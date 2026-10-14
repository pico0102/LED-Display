#!/usr/bin/env python3
"""tools/send_voice_cmd.py - Desktop CLI tester for MatrixPortal S3 voice control.
Supports LAN HTTP webhook test and Adafruit IO Cloud REST push.
Uses only Python standard library (argparse, urllib.request, urllib.parse, json).
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request


def send_lan_cmd(host, port, cmd, token=""):
    """Send voice command directly to MatrixPortal S3 over local LAN."""
    params = {"app": cmd}
    if token:
        params["token"] = token
    query_str = urllib.parse.urlencode(params)
    url = f"http://{host}:{port}/switch?{query_str}"
    print(f"Sending LAN command to: {url}")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response [{status}]: {body}")
            return status == 200
    except Exception as e:
        print(f"LAN request failed: {e}", file=sys.stderr)
        return False


def send_aio_cmd(username, key, feed, cmd):
    """Send voice command to Adafruit IO feed via REST API (pushes via MQTT to board)."""
    url = f"https://io.adafruit.com/api/v2/{username}/feeds/{feed}/data"
    headers = {
        "X-AIO-Key": key,
        "Content-Type": "application/json",
    }
    payload = json.dumps({"value": cmd}).encode("utf-8")
    print(f"Sending Adafruit IO REST push to feed '{feed}': {url}")
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            print(f"Response [{status}]: {body}")
            return status in (200, 201)
    except Exception as e:
        print(f"Adafruit IO request failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Send voice test commands to MatrixPortal S3 LED Display."
    )
    parser.add_argument("command", help="Command string or phrase (e.g. 'sports', 'bus', 'flights', 'next')")

    group = parser.add_argument_group("LAN Mode")
    group.add_argument("--host", help="IP address or hostname of MatrixPortal S3 on local LAN")
    group.add_argument("--port", type=int, default=8080, help="Port for LAN listener (default: 8080)")
    group.add_argument("--token", default="", help="Optional security token (VOICE_TOKEN)")

    aio_group = parser.add_argument_group("Adafruit IO Cloud Mode")
    aio_group.add_argument("--aio-user", help="Adafruit IO username")
    aio_group.add_argument("--aio-key", help="Adafruit IO active key")
    aio_group.add_argument("--aio-feed", default="led-display", help="Adafruit IO feed name (default: led-display)")

    args = parser.parse_args()

    if args.host:
        success = send_lan_cmd(args.host, args.port, args.command, args.token)
        sys.exit(0 if success else 1)
    elif args.aio_user and args.aio_key:
        success = send_aio_cmd(args.aio_user, args.aio_key, args.aio_feed, args.command)
        sys.exit(0 if success else 1)
    else:
        print("Error: Specify either --host <ip> for LAN mode or --aio-user <user> and --aio-key <key> for cloud mode.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
