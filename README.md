# Jito ShredStream Alternative: Migration Kit for Solana Shred Feeds

Tools and a step-by-step guide for moving a **Jito ShredStream** setup to another Solana shred feed, and for proving the new feed is at least as fast before you cut over.

Jito's documentation announced that ShredStream would be **shut down on September 5, 2026**. If your bot, validator or indexer still depends on `jito-shredstream-proxy`, this repo helps you replace it with a feed that sends shreds in the same wire format, such as [NoLimitNodes Shredstream](https://nolimitnodes.com/products/shredstream).

**Contents:**

- [What's in the kit](#whats-in-the-kit)
- [Quick start](#quick-start)
- [How Jito ShredStream settings map to a replacement feed](#how-jito-shredstream-settings-map-to-a-replacement-feed)
- [Comparing two shred feeds](#comparing-two-shred-feeds)
- [FAQ](#faq)

## What's in the kit

| Path | What it does |
|---|---|
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | 7-step migration checklist from Jito ShredStream to a new shred feed |
| [`tools/shred_sniff.py`](tools/shred_sniff.py) | Checks that a new feed is arriving: packets/s, Mbit/s, slots, data/code mix, lead over RPC |
| [`tools/shred_compare.py`](tools/shred_compare.py) | Runs two feeds side by side and reports which delivers each shred first, by how many ms, and which feed misses shreds |
| [`tools/shredlib.py`](tools/shredlib.py) | Dependency-free parser for the common shred header (slot, index, version, FEC set, data/code, legacy/merkle) |
| [`tools/fake_feeds.py`](tools/fake_feeds.py) | Sends synthetic shreds so you can try the tools without a live feed |
| [`firewall/`](firewall) | `ufw`, `iptables` and `nftables` rules for opening the shred UDP port |
| [`tuning/99-shreds.conf`](tuning/99-shreds.conf) | `sysctl` UDP buffer settings that stop the kernel from dropping shred bursts |

Everything is plain Python 3.9+ with no third-party packages.

## Quick start

```bash
git clone https://github.com/no-limit-nodes/jito-shredstream-alternative
cd jito-shredstream-alternative

# 1. Raise UDP receive buffers (Linux)
sudo cp tuning/99-shreds.conf /etc/sysctl.d/ && sudo sysctl --system

# 2. Open the UDP port your new feed sends to
sudo PORT=20000 ./firewall/ufw.sh

# 3. Confirm shreds are arriving
python3 tools/shred_sniff.py --listen 0.0.0.0:20000 --rpc https://your-rpc-endpoint
```

Expected output once the feed is live:

```text
listening on 0.0.0.0:20000 (Ctrl-C to stop)
   ##### pkt/s     ##.# Mbit/s  data ####  code ####  invalid 0  slots 12  newest 3########  rpc 3########  shred lead +1 slots
```

If you see `no packets yet`, check the destination IP:port registered with your provider, the host firewall, and your cloud security group. Shred feeds need a **public IPv4 address**, because shreds are pushed to you over UDP and cannot reach a host behind NAT.

## How Jito ShredStream settings map to a replacement feed

| `jito-shredstream-proxy` setting | What it did | With NoLimitNodes Shredstream |
|---|---|---|
| `BLOCK_ENGINE_URL` | Where the proxy authenticated and fetched shreds | Not needed: there is no proxy to run. Shreds are pushed straight to your server. |
| `AUTH_KEYPAIR` + Discord approval | Access control | An NLN account and plan ([dashboard](https://dash.nolimitnodes.com/login)) |
| `DEST_IP_PORTS` | Where the proxy forwarded shreds | **Destinations**: public `IPv4:port` pairs, each verified with a UDP challenge |
| `SRC_BIND_PORT` (default 20000) | UDP port the proxy listened on | Any UDP port you choose for each destination |
| `GRPC_SERVICE_PORT` | Optional decoded entries over gRPC | Raw shreds only. Deshred them yourself, or use a decoded gRPC stream for transactions. |

Your consumer reads the same Jito-compatible shred format, so in most setups the only code change is the port it listens on. On NoLimitNodes, the Ultra plan includes 1 shred destination and Enterprise includes 2. Extra destinations are $100/month each, up to 5 per account. See [pricing](https://nolimitnodes.com/pricing) for current terms.

Setup docs: [Shredstream setup](https://nolimitnodes.com/docs/api-reference/shredstream/setup) and [firewall configuration](https://nolimitnodes.com/docs/api-reference/shredstream/firewall).

## Comparing two shred feeds

Point two feeds at two ports on the **same host**: your old and new provider, two providers, or two regions of one provider. Then run:

```bash
python3 tools/shred_compare.py --a 0.0.0.0:20000 --b 0.0.0.0:20001 --names old,new --duration 1800
```

```text
[  1800.0s] shreds on both feeds: ...
  feed         packets  only here    first   win %  median lead  p90 lead
  old              ...        ...      ...     ...          ...       ...
  new              ...        ...      ...     ...          ...       ...
```

- **first / win %**: how often this feed delivered a shared shred first
- **median / p90 lead**: how far ahead this feed was when it won
- **only here**: shreds this feed delivered that the other never did. A high number on one side means the other feed is losing shreds.

A shred is matched across feeds by `(slot, data|code, index)`. Both sockets are read by one loop on one clock, so the timings can be compared directly. Run it for at least 30 minutes, and during busy hours, before you decide.

To try the tool without a feed:

```bash
cd tools
python3 shred_compare.py --a 127.0.0.1:21000 --b 127.0.0.1:21001 --names old,new --duration 8 &
python3 fake_feeds.py --a 127.0.0.1:21000 --b 127.0.0.1:21001 --b-lead-ms 3 --a-loss 0.05
```

## FAQ

**Is Jito ShredStream really shutting down?**
Jito's low-latency transaction feed docs announced a shutdown date of September 5, 2026 and pointed users to alternatives. Check [docs.jito.wtf](https://docs.jito.wtf/lowlatencytxnfeed/) for the current status.

**What are Jito shreds?**
They are standard Solana shreds: the roughly 1.2 KB UDP packets a leader splits each block into and sends out through Turbine. ShredStream forwarded them to subscribers before they reached most of the network. Any feed that sends the same packets is a drop-in source for code that parses them.

**Do I need to change my shred-parsing code?**
Usually not. If your code reads shred packets from a UDP port today, point it at the new port. If you relied on the proxy's decoded gRPC entries, you need a deshred step or a decoded transaction stream instead.

**Can I run the old and new feeds at the same time?**
Yes, on different ports. That is exactly what `shred_compare.py` is for. Cut over once the new feed wins the comparison or matches your current latency.

**Does this work behind NAT or on a home connection?**
No. Shreds are pushed to you over UDP, so you need a server with a public IPv4 address and an open UDP port.

## Related

- [NoLimitNodes Shredstream](https://nolimitnodes.com/products/shredstream): Jito-compatible Solana shred feed
- [Jito ShredStream vs NoLimitNodes](https://nolimitnodes.com/compare/jito-shredstream-vs-nolimitnodes)
- [Shredstream vs Yellowstone gRPC](https://nolimitnodes.com/compare/shredstream-vs-yellowstone-grpc)
- [Solana Shredstream guide](https://nolimitnodes.com/blog/solana-shredstream-guide)
- [pumpfun-sniper-bot](https://github.com/no-limit-nodes/pumpfun-sniper-bot) and [solana-copy-trading-bot](https://github.com/no-limit-nodes/solana-copy-trading-bot): trading bots built on NoLimitNodes streams

Need help planning a migration? [Talk to the NoLimitNodes team](https://nolimitnodes.com/talk-to-sales).

## License

MIT
