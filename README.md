# Vaillant VRC 700 — Home Assistant Integration

Custom Home Assistant integration for Vaillant heat pump systems controlled by a **VRC 700** controller (connected to the myVAILLANT cloud via sensoNET / VR 921).

Built because the VRC 700 operates differently from modern (TLI) controllers: heating and cooling are fully independent, with their own operating modes (Auto / Day / Set-back / Off) and setpoints. Every API endpoint used here was verified against real myVAILLANT app traffic captured with mitmproxy on a live VRC 700 R6 system.

## Status

Running in production on a live VRC 700 R6 system since 2026-06-11 (mypyllant fully replaced).

| Phase | Scope | Status |
|---|---|---|
| A | Standalone API client (`api/`) + CLI test script | ✅ live-verified |
| B | Integration skeleton, config flow, read-only sensors | ✅ done |
| C | Controls (modes, temperatures, manual cooling, DHW boost) | ✅ done |
| D | Options flow, quota backoff, diagnostics | ✅ done |
| E | Production cutover | ✅ done (v0.4.1) |
| F | HACS publication | 🔨 in progress |

## Installation

**Via HACS (custom repository):**

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/einar8620/vaillant-vrc700`, category **Integration**.
3. Find **Vaillant VRC 700** in HACS, **Download**, then restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → "Vaillant VRC 700" → enter your myVAILLANT credentials.

**Manual:** copy `custom_components/vaillant_vrc700` into your HA `config/custom_components/`, restart, then add the integration.

## Configuration

Config flow only — no YAML. You provide your myVAILLANT account email + password (the same credentials as the myVAILLANT app). The integration polls the myVAILLANT cloud (`cloud_polling`) with quota-aware backoff.

## Entities

Granular entities only (no `climate` entity — the VRC 700's independent heating/cooling model doesn't fit it):

- **select:** heating mode (Auto/Day/Set-back/Off), cooling mode (Auto/Day/Off), DHW mode
- **number:** heating day temp, heating setback temp, cooling day temp, DHW setpoint, manual cooling days (1–99)
- **switch:** manual cooling, hot water boost (auto-off timer, default 30 min)
- **sensor:** system status, flow temp, water pressure, outside temp, indoor temp, humidity, DHW temp, DHW status, error codes
- **binary_sensor:** online, problem
- **button:** force refresh

## Testing the API client (Phase A)

```bash
pip install aiohttp
cp scripts/secrets.example.json scripts/secrets.json   # fill in your credentials
python3 scripts/test_api.py                            # read-only: login + print full system state
```

## Credits

Authentication flow adapted from [myPyllant](https://github.com/signalkraft/myPyllant) (MIT, © 2023 Philipp Dörner). API endpoint mapping from original mitmproxy captures of the myVAILLANT Android app.

## License

MIT
