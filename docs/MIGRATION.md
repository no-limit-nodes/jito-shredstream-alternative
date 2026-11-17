# Jito ShredStream Migration Checklist

Use this checklist to move from `jito-shredstream-proxy` to a new Solana shred feed with no gap in coverage.

## 1. List what you run today

- [ ] Which hosts run `jito-shredstream-proxy`, and in which regions (`DESIRED_REGIONS`)?
- [ ] What is in `DEST_IP_PORTS`? Each entry is a consumer you must re-point.
- [ ] Is `GRPC_SERVICE_PORT` set? If so, something reads decoded entries, and it needs a deshred step or a decoded stream after migration.
- [ ] Which processes read the shreds (bot, validator, indexer), and what UDP port does each listen on?

## 2. Pick a replacement and a destination

- [ ] Choose a feed that sends the same shred wire format, for example [NoLimitNodes Shredstream](https://nolimitnodes.com/products/shredstream), so your parsers keep working unchanged.
- [ ] Decide how many destinations you need: one per server that receives shreds.
- [ ] Each destination needs a **public IPv4 address** and a UDP port. NAT is not supported, because shreds are pushed to you.

## 3. Prepare the host

- [ ] Raise UDP buffers: `sudo cp tuning/99-shreds.conf /etc/sysctl.d/ && sudo sysctl --system`
- [ ] Open the UDP port on the host firewall (`firewall/ufw.sh`, `firewall/iptables.sh` or `firewall/nftables.conf`).
- [ ] Open the same UDP port in your cloud security group or provider firewall. This is the most common reason no packets arrive.
- [ ] If your provider publishes source IPs, allow only those (`SOURCES=` in the scripts).

## 4. Register and verify the destination

- [ ] Add the `IPv4:port` destination in your provider dashboard ([NoLimitNodes dashboard](https://dash.nolimitnodes.com/login)).
- [ ] Complete the UDP challenge verification. See the [setup docs](https://nolimitnodes.com/docs/api-reference/shredstream/setup).
- [ ] Run `python3 tools/shred_sniff.py --listen 0.0.0.0:<port>` and confirm packets/s and slots are increasing with `invalid 0`.

## 5. Compare before cutting over

- [ ] Run the old and new feeds on two ports at the same time.
- [ ] `python3 tools/shred_compare.py --a 0.0.0.0:<old> --b 0.0.0.0:<new> --names old,new --duration 1800`
- [ ] Check the win %, the median and p90 lead, and the "only here" count on each side.
- [ ] Repeat during peak hours (for example, US market open) when shred volume is highest.

If the old feed is already gone, compare the new feed against a second provider or region, or use `shred_sniff.py --rpc` to confirm it stays ahead of RPC.

## 6. Cut over

- [ ] Point each consumer at the new port, or move the new feed to the old port.
- [ ] If you used `GRPC_SERVICE_PORT`, switch those readers to your own deshred step or a decoded transaction stream.
- [ ] Remove `jito-shredstream-proxy` from systemd, Docker or Kubernetes so it does not restart.

## 7. Monitor

- [ ] Alert when packets/s drops to zero for more than a few seconds.
- [ ] Watch the shred slot vs RPC slot gap (`--rpc`). The shred feed should stay level with or ahead of RPC.
- [ ] Re-run `shred_compare.py` after any provider, region or server change.

Questions? [Talk to the NoLimitNodes team](https://nolimitnodes.com/talk-to-sales).
