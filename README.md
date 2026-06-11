# Vaillant VRC 700 — Home Assistant Integration

Custom Home Assistant integration for Vaillant heat pump systems controlled by a **VRC 700** controller (connected to the myVAILLANT cloud via sensoNET / VR 921).

Built because the VRC 700 operates differently from modern (TLI) controllers: heating and cooling are fully independent, with their own operating modes (Auto / Day / Set-back / Off) and setpoints. Every API endpoint used here was verified against real myVAILLANT app traffic captured with mitmproxy on a live VRC 700 R6 system.

## Status

| Phase | Scope | Status |
|---|---|---|
| A | Standalone API client (`api/`) + CLI test script | 🔨 in progress |
| B | Integration skeleton, config flow, read-only sensors | ⏳ |
| C | Controls (modes, temperatures, manual cooling, DHW boost) | ⏳ |
| D | Options flow, quota backoff, diagnostics | ⏳ |
| E | Production cutover | ⏳ |
| F | HACS publication | ⏳ |

## Planned entities

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
