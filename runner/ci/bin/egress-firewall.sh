#!/bin/bash
# runner/ci/bin/egress-firewall.sh: the scoring host's network policy (docs/SCORING-INFRA.md §4.2).
#
#   containers on user-defined bridges (br-*: every Compose network the runner creates per game)
#       -> only the provider host(s) on tcp/443 (the gateway's upstream) and DNS to the host's upstream resolvers.
#          The harness and game sit on `internal: true` networks with no route at all; this rule bounds the gateway.
#   containers on the default bridge (docker0: `docker build` of the submission, no secrets)
#       -> tcp/80,443 to public addresses only (pinned dependencies at build time; GAME-API §2), never link-local
#          (cloud metadata), RFC 1918 / CGNAT (the VPC) or the host
#   containers -> the host itself: dropped (no host service is reachable from a container)
#   --host (self-hosted only): the host's own traffic: no inbound except established; outbound tcp/80,443,
#          DNS and NTP only (the GitHub runner, image pulls, apt at provision)
#
# Usage: sudo runner/ci/bin/egress-firewall.sh apply [--host] [--allow openrouter.ai[,host2]]
#        sudo runner/ci/bin/egress-firewall.sh refresh      # re-resolve the allowed hosts (run every 60 s)
#        sudo runner/ci/bin/egress-firewall.sh status | check
# Works on GitHub-hosted ubuntu-24.04 (sudo, iptables-nft) and on our Ubuntu 24.04 hosts. Idempotent. It does not
# touch Docker's own chains; it fills DOCKER-USER (which Docker evaluates first) and our DFB-* chains.
set -euo pipefail
ALLOW_HOSTS=${DFBENCH_EGRESS_ALLOW:-openrouter.ai}
STATE=/run/dfbench-egress
mode=${1:-}; shift || true
HOST_MODE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST_MODE=1 ;;
    --allow) ALLOW_HOSTS=$2; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac; shift
done
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 2; }
IPT=iptables; IP6T=ip6tables

resolvers() {
  # the upstream resolvers Docker's embedded DNS forwards to (systemd-resolved's real upstreams, not 127.0.0.53)
  local f=/run/systemd/resolve/resolv.conf; [ -s "$f" ] || f=/etc/resolv.conf
  awk '/^nameserver/ && $2 !~ /^127\./ && $2 ~ /^[0-9.]+$/ {print $2}' "$f" | sort -u
}

resolve_allowed() {
  local h
  for h in ${ALLOW_HOSTS//,/ }; do getent ahostsv4 "$h" | awk '{print $1}'; done | sort -u
}

chain() {  # create or flush a chain in the filter table
  $IPT -N "$1" 2>/dev/null || $IPT -F "$1"
}

fill_allow() {
  # two chains, A and B: build the idle one, point DFB-ALLOW at it, then flush the old one (no gap in the allowlist)
  local ips cur nxt; ips=$(resolve_allowed)
  [ -n "$ips" ] || { echo "egress-firewall: could not resolve $ALLOW_HOSTS" >&2; return 1; }
  cur=$(cat "$STATE/active" 2>/dev/null || echo B); [ "$cur" = A ] && nxt=B || nxt=A
  chain "DFB-ALLOW-$nxt"
  for ip in $ips; do $IPT -A "DFB-ALLOW-$nxt" -d "$ip" -p tcp --dport 443 -j ACCEPT; done
  $IPT -N DFB-ALLOW 2>/dev/null || true
  $IPT -I DFB-ALLOW 1 -j "DFB-ALLOW-$nxt"
  while [ "$($IPT -S DFB-ALLOW | grep -c -- '-j DFB-ALLOW-')" -gt 1 ]; do $IPT -D DFB-ALLOW 2; done
  $IPT -F "DFB-ALLOW-$cur" 2>/dev/null || true
  mkdir -p "$STATE"; echo "$ips" > "$STATE/allowed"; echo "$nxt" > "$STATE/active"
}

apply() {
  command -v $IPT >/dev/null || { echo "iptables missing" >&2; exit 2; }
  $IPT -N DOCKER-USER 2>/dev/null || true   # Docker creates it; make sure it exists if Docker starts later
  fill_allow

  # br-*: Compose networks (gateway egress). Only the provider and DNS.
  chain DFB-COMPOSE
  $IPT -A DFB-COMPOSE -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  $IPT -A DFB-COMPOSE -o br-+ -j RETURN                       # container <-> container on our bridges
  for r in $(resolvers); do
    $IPT -A DFB-COMPOSE -d "$r" -p udp --dport 53 -j RETURN
    $IPT -A DFB-COMPOSE -d "$r" -p tcp --dport 53 -j RETURN
  done
  $IPT -A DFB-COMPOSE -j DFB-ALLOW                            # ACCEPT for the provider's addresses on 443
  $IPT -A DFB-COMPOSE -j DROP

  # docker0: builds. Public internet on 80/443 only.
  chain DFB-BUILD
  $IPT -A DFB-BUILD -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  for net in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 \
             224.0.0.0/4 240.0.0.0/4; do
    $IPT -A DFB-BUILD -d "$net" -j DROP
  done
  for r in $(resolvers); do
    $IPT -A DFB-BUILD -d "$r" -p udp --dport 53 -j RETURN
    $IPT -A DFB-BUILD -d "$r" -p tcp --dport 53 -j RETURN
  done
  $IPT -A DFB-BUILD -p tcp -m multiport --dports 80,443 -j RETURN
  $IPT -A DFB-BUILD -j DROP

  # DOCKER-USER: our chains first, then Docker's RETURN
  $IPT -F DOCKER-USER
  $IPT -A DOCKER-USER -i br-+ -j DFB-COMPOSE
  $IPT -A DOCKER-USER -i docker0 ! -o docker0 -j DFB-BUILD
  $IPT -A DOCKER-USER -j RETURN

  # containers -> host: nothing (DNS from containers is forwarded from their own netns, not via the host)
  chain DFB-INPUT
  $IPT -A DFB-INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  $IPT -A DFB-INPUT -j DROP
  $IPT -C INPUT -i br-+ -j DFB-INPUT 2>/dev/null || $IPT -I INPUT 1 -i br-+ -j DFB-INPUT
  $IPT -C INPUT -i docker0 -j DFB-INPUT 2>/dev/null || $IPT -I INPUT 1 -i docker0 -j DFB-INPUT

  # IPv6: our Docker networks are IPv4-only; drop any v6 forwarding from containers outright
  if command -v $IP6T >/dev/null; then
    $IP6T -N DOCKER-USER 2>/dev/null || true
    $IP6T -C DOCKER-USER -i br-+ -j DROP 2>/dev/null || $IP6T -I DOCKER-USER 1 -i br-+ -j DROP
    $IP6T -C DOCKER-USER -i docker0 -j DROP 2>/dev/null || $IP6T -I DOCKER-USER 1 -i docker0 -j DROP
  fi

  if [ "$HOST_MODE" = 1 ]; then
    # the host's own traffic (self-hosted only; never on GitHub-hosted VMs)
    chain DFB-HOST-IN
    $IPT -A DFB-HOST-IN -i lo -j ACCEPT
    $IPT -A DFB-HOST-IN -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    $IPT -A DFB-HOST-IN -p icmp -j ACCEPT
    $IPT -A DFB-HOST-IN -j DROP
    $IPT -C INPUT -j DFB-HOST-IN 2>/dev/null || $IPT -A INPUT -j DFB-HOST-IN
    chain DFB-HOST-OUT
    $IPT -A DFB-HOST-OUT -o lo -j ACCEPT
    $IPT -A DFB-HOST-OUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    $IPT -A DFB-HOST-OUT -o br-+ -j ACCEPT
    $IPT -A DFB-HOST-OUT -o docker0 -j ACCEPT
    $IPT -A DFB-HOST-OUT -d 169.254.169.254 -m owner --uid-owner 0 -j ACCEPT   # cloud metadata: root only
    $IPT -A DFB-HOST-OUT -d 169.254.169.254 -j DROP
    $IPT -A DFB-HOST-OUT -p udp -m multiport --dports 53,123 -j ACCEPT
    $IPT -A DFB-HOST-OUT -p tcp -m multiport --dports 53,80,443 -j ACCEPT
    $IPT -A DFB-HOST-OUT -j DROP
    $IPT -C OUTPUT -j DFB-HOST-OUT 2>/dev/null || $IPT -A OUTPUT -j DFB-HOST-OUT
  fi
  echo "egress-firewall: applied (allow ${ALLOW_HOSTS} -> $(tr '\n' ' ' < "$STATE/allowed"); host mode $HOST_MODE)"
}

check() {
  # a container on a fresh user-defined bridge must reach the provider and nothing else
  local net=dfb-fwcheck-$$ img=${DFBENCH_FWCHECK_IMAGE:-curlimages/curl:8.11.1}
  docker network create "$net" >/dev/null
  trap 'docker network rm "$net" >/dev/null 2>&1 || true' RETURN
  local ok=0
  if docker run --rm --network "$net" "$img" -sS -o /dev/null -m 10 "https://${ALLOW_HOSTS%%,*}/" ; then
    echo "check: provider reachable"; else echo "check: provider NOT reachable" >&2; ok=1; fi
  if docker run --rm --network "$net" "$img" -sS -o /dev/null -m 10 https://example.com/ 2>/dev/null; then
    echo "check: example.com reachable (policy broken)" >&2; ok=1; else echo "check: example.com blocked"; fi
  if docker run --rm --network "$net" "$img" -sS -o /dev/null -m 5 http://169.254.169.254/ 2>/dev/null; then
    echo "check: metadata reachable (policy broken)" >&2; ok=1; else echo "check: metadata blocked"; fi
  return $ok
}

case "$mode" in
  apply) apply ;;
  refresh) fill_allow ;;
  status) $IPT -S DOCKER-USER; $IPT -S DFB-ALLOW; $IPT -S "DFB-ALLOW-$(cat $STATE/active)"; cat "$STATE/allowed" 2>/dev/null || true ;;
  check) check ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
