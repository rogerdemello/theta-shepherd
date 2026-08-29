# MCP overseer demo — "how is the flock doing?"

The CLI is the agent's hands; **MCP is the human's window into the same
account.** This is a real transcript of the official
[`alpaca-mcp-server`](https://github.com/alpacahq/alpaca-mcp-server) (v3.4.7)
being driven over the MCP stdio protocol against paper account
`PA31OBPWA7MW`, captured Sat Aug 29 2026 while the agent's QQQ iron condor
was open. Any MCP client works the same way — in Claude Code it's:

```bash
claude mcp add alpaca --transport stdio -- uvx alpaca-mcp-server --env-file /path/to/.env
```

then simply ask Claude *"how is the flock doing?"* and it calls these tools.

## The server exposes 72 tools

Account, orders, positions, watchlists, stock/option/crypto market data,
news, corporate actions, docs search — including everything below.

## `get_account_info`

```json
{
  "account_number": "PA31OBPWA7MW",
  "status": "ACTIVE",
  "options_approved_level": 3,
  "equity": "100015.61",
  "last_equity": "100035.61",
  "options_buying_power": "99353.61",
  "position_market_value": "1042",
  "created_at": "2026-08-28T16:20:18Z"
}
```

## `get_all_positions` — the flock, leg by leg

| Symbol | Side | Qty | Avg entry | Current | Unrealized P&L |
|---|---|---|---|---|---|
| QQQ260904C00728000 | short | −2 | $2.00 | $1.54 | **+$92** |
| QQQ260904C00733000 | long | +2 | $0.99 | $0.60 | −$78 |
| QQQ260904P00704000 | short | −2 | $2.39 | $1.91 | **+$96** |
| QQQ260904P00699000 | long | +2 | $1.63 | $1.16 | −$94 |

Net unrealized: **+$16** — both short legs decaying faster than the long
hedges, which is exactly what a premium seller wants to see. (The agent's own
view of the same book lives in `journal/state.json`; broker and journal are
reconciled every cycle.)

## `get_clock`

```json
{"is_open": false, "next_open": "2026-08-31T09:30:00-04:00"}
```

Market closed (Saturday); the agent's scheduled cycles resume at the next
open.

---

*Note: every tool response arrives wrapped in Alpaca's
`_alpaca_mcp_security` envelope marking it as untrusted data, not
instructions — a production-minded touch worth copying in any agent system.*
