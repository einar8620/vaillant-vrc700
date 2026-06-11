#!/usr/bin/env python3
"""Phase A live test — READ ONLY, makes no changes to the system.

Logs in, discovers systems, fetches the main system read + connection
status + trouble codes, and prints every field the integration will expose.

Usage:
    cp scripts/secrets.example.json scripts/secrets.json   # fill in
    python3 scripts/test_api.py [--raw] [--secrets PATH]

--raw additionally dumps the full system JSON to scripts/system_raw.json
(useful for comparing against the mitmproxy captures).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import aiohttp

# Allow running from the repo root without installing anything
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from vaillant_vrc700.api import VRC700Client, VRC700System, VaillantAuth  # noqa: E402


def p(label: str, value) -> None:
    print(f"  {label:<38} {value}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--secrets",
        default=str(Path(__file__).parent / "secrets.json"),
        help="path to secrets JSON (default: scripts/secrets.json)",
    )
    parser.add_argument(
        "--raw", action="store_true", help="dump raw system JSON to scripts/system_raw.json"
    )
    args = parser.parse_args()

    secrets_path = Path(args.secrets)
    if not secrets_path.exists():
        print(f"Secrets file not found: {secrets_path}")
        print("Copy scripts/secrets.example.json to scripts/secrets.json and fill it in.")
        return 1
    secrets = json.loads(secrets_path.read_text())

    async with aiohttp.ClientSession() as session:
        auth = VaillantAuth(
            session,
            secrets["username"],
            secrets["password"],
            brand=secrets.get("brand", "vaillant"),
            country=secrets.get("country"),
        )
        client = VRC700Client(session, auth)

        print(f"\n[1/5] Logging in (realm: {auth.realm}) ...")
        await auth.login()
        print("      OK — token obtained")

        print("\n[2/5] Discovering systems (/homes) ...")
        homes = await client.get_homes()
        if not homes:
            print("      No systems found on this account!")
            return 1
        for h in homes:
            print(f"      systemId={h.get('systemId')}  name={h.get('homeName')!r}")
        system_id = homes[0].get("systemId")

        print("\n[3/5] Control identifier ...")
        ci = await client.get_control_identifier(system_id)
        print(f"      {ci}  {'(VRC700 — good)' if ci == 'vrc700' else '(WARNING: not vrc700!)'}")

        print("\n[4/5] Main system read ...")
        raw = await client.get_system_raw(system_id)
        if args.raw:
            out = Path(__file__).parent / "system_raw.json"
            out.write_text(json.dumps(raw, indent=2))
            print(f"      raw JSON saved to {out}")
        system = VRC700System.from_api(system_id, raw)

        print("\n  --- System ---")
        p("Controller", f"{system.controller_type} {system.controller_revision} (scheme {system.system_scheme})")
        p("System status (derived 6b)", system.system_status)
        p("Energy manager state", system.energy_manager_state)
        p("Outside temp (6e)", system.outdoor_temperature)
        p("Outside temp 24h avg", system.outdoor_temperature_avg24h)
        p("Water pressure (6d)", system.water_pressure)
        p("System flow temp", system.system_flow_temperature)
        p("Manual cooling days (4)", f"{system.manual_cooling_days} (active: {system.manual_cooling_active})")

        for z in system.zones:
            print(f"\n  --- Zone {z.index} ({z.name!r}, active={z.is_active}) ---")
            p("Heating mode (2a)", z.heating_mode)
            p("Heating day temp (2c)", z.heating_day_temp)
            p("Heating setback temp (2b)", z.heating_setback_temp)
            p("Cooling mode (3a)", z.cooling_mode)
            p("Cooling day temp (3b)", z.cooling_day_temp)
            p("Indoor temp (6f)", z.room_temperature)
            p("Humidity (6g)", z.humidity)

        for c in system.circuits:
            print(f"\n  --- Circuit {c.index} ---")
            p("State", c.state)
            p("Flow temp (6c)", c.flow_temperature)
            p("Heating curve", c.heating_curve)
            p("Cooling allowed", c.is_cooling_allowed)

        for d in system.dhw:
            print(f"\n  --- Hot water (index {d.index}) ---")
            p("Current temp (6h-i)", d.current_temperature)
            p("Setpoint (6h-ii)", f"{d.setpoint} (range {d.min_setpoint}-{d.max_setpoint})")
            p("Mode", d.mode)
            p("Special function", d.special_function)
            p("DHW status (derived 6h-iii)", system.dhw_status)

        print("\n[5/5] Connection status + trouble codes ...")
        connected = await client.get_connection_status(system_id)
        p("Online (6i)", connected)
        dtcs = await client.get_trouble_codes(system_id)
        codes = [
            c for dev in dtcs for c in (dev.get("diagnosticTroubleCodes") or [])
        ]
        p("Trouble codes (6a)", codes if codes else "none")

        print(f"\nDone. API requests made: {client.request_count}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
