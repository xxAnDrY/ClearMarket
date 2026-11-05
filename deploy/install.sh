#!/usr/bin/env bash
# Installa ClearMarket su un server Ubuntu/Debian. Rieseguirlo aggiorna lo stack.
# Uso: sudo DEEPL_API_KEY=... FINNHUB_API_KEY=... DOMAIN=api.esempio.it deploy/install.sh
# Senza DOMAIN usa <ip-pubblico>.sslip.io, che punta gia' al server.
set -euo pipefail

cd "$(dirname "$0")"

if [[ $EUID -ne 0 ]]; then
  echo "Esegui con sudo." >&2
  exit 1
fi

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

# Le VM da 1 GB non reggono build e database senza swap.
if (( $(awk '/MemTotal/ {print $2}' /proc/meminfo) < 2000000 )) && [[ -z "$(swapon --show)" ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Le immagini Ubuntu di alcuni provider bloccano 80 e 443 nel firewall locale.
for port in 80 443; do
  if command -v iptables >/dev/null && ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  fi
done
if command -v netfilter-persistent >/dev/null; then
  netfilter-persistent save
fi

# I segreti si generano una volta sola: rigenerarli renderebbe invalido il database.
if [[ ! -f .env ]]; then
  domain="${DOMAIN:-$(curl -4fsS https://api.ipify.org).sslip.io}"
  umask 077
  cat > .env <<EOF
DOMAIN=${domain}
POSTGRES_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 48)
DEEPL_API_KEY=${DEEPL_API_KEY:-}
FINNHUB_API_KEY=${FINNHUB_API_KEY:-}
EOF
fi

compose() { docker compose --env-file .env -f docker-compose.prod.yml "$@"; }

compose up --build -d --remove-orphans

domain="$(grep '^DOMAIN=' .env | cut -d= -f2)"
for _ in $(seq 1 60); do
  if curl -fsS "https://${domain}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
curl -fsS "https://${domain}/healthz"
echo

echo "Sito online: https://${domain}"
