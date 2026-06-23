#!/usr/bin/env bash
#
# Wdrożenie aktualnego kodu na produkcję.
#
# Typowy scenariusz:
#   git pull
#   ./deploy.sh
#
# Wersjonowanie:
#   Obraz dostaje IMMUTABLE tag = SHA commita (mieszkania:<sha>). Tag nigdy nie
#   jest nadpisywany — każdy build to nowy, niezmienny obraz. Nie używamy
#   ruchomego :latest. To, która wersja jest "live", zapisane jest jako
#   IMAGE_TAG w .env (czyta to docker compose przy interpolacji image:).
#
# Co robi:
#   1. Buduje obraz mieszkania:<sha> z aktualnego kodu.
#   2. Zapisuje IMAGE_TAG=<sha> w .env i robi docker compose up -d.
#   3. Czeka aż app będzie "healthy".
#   4. Dopisuje wdrożenie do .deploy_history.
#   5. Sprząta stare obrazy (zostawia ostatnie KEEP_VERSIONS, nigdy nie usuwa live).
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="mieszkania"
SERVICE="app"
KEEP_VERSIONS="${KEEP_VERSIONS:-5}"

cd "$REPO_DIR"

if [ ! -f .env ]; then
  echo "❌ Brak $REPO_DIR/.env — utwórz go (patrz README / .env.example)." >&2
  exit 1
fi

# Ustawia/aktualizuje IMAGE_TAG w .env (źródło prawdy o wersji live).
set_image_tag() {
  local tag="$1"
  if grep -q '^IMAGE_TAG=' .env; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$tag|" .env
  else
    printf 'IMAGE_TAG=%s\n' "$tag" >> .env
  fi
}

# Wersja = krótki SHA. Niezacommitowane zmiany → -dirty-<ts>, żeby tag pozostał
# unikalny i niezmienny (nie nadpisał "czystej" wersji pod tym samym SHA).
VERSION="$(git rev-parse --short HEAD)"
FULL_SHA="$(git rev-parse HEAD)"
if ! git diff --quiet || ! git diff --cached --quiet; then
  VERSION="${VERSION}-dirty-$(date +%Y%m%d%H%M%S)"
  echo "⚠️  Working tree ma niezacommitowane zmiany — wersja: $VERSION"
fi

if docker image inspect "$IMAGE:$VERSION" >/dev/null 2>&1; then
  echo "ℹ️  Obraz $IMAGE:$VERSION już istnieje — przebuduję go (ten sam tag, nowa zawartość tylko jeśli kod się zmienił)."
fi

echo "▶ Wdrażam wersję: $VERSION  ($(git log -1 --pretty=%s))"

# 1. Build pod immutable tagiem (IMAGE_TAG steruje nazwą obrazu w compose).
IMAGE_TAG="$VERSION" docker compose build "$SERVICE"

# 2. Przełącz wersję live i restart.
set_image_tag "$VERSION"
docker compose up -d

# 3. Czekaj na healthy (kontener ma HEALTHCHECK w Dockerfile).
CONTAINER="$(docker compose ps -q "$SERVICE")"
echo "⏳ Czekam aż kontener będzie healthy..."
for _ in $(seq 1 30); do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER" 2>/dev/null || echo unknown)"
  case "$status" in
    healthy) echo "✅ healthy"; break ;;
    unhealthy) echo "❌ kontener unhealthy — sprawdź: docker compose logs $SERVICE"; exit 1 ;;
    none) echo "ℹ️  brak healthcheck — pomijam czekanie"; break ;;
  esac
  sleep 2
done

# 4. Historia wdrożeń.
printf '%s\tDEPLOY\t%s\t%s\n' "$(date -Iseconds)" "$VERSION" "$FULL_SHA" >> "$REPO_DIR/.deploy_history"

# 5. Sprzątanie: dangling + stare wersjonowane obrazy ponad limit (nigdy live).
docker image prune -f >/dev/null 2>&1 || true
docker images "$IMAGE" --format '{{.Tag}}' \
  | grep -vx 'dev' \
  | grep -vx "$VERSION" \
  | tail -n "+$((KEEP_VERSIONS + 1))" \
  | while read -r old; do
      echo "🧹 usuwam stary obraz $IMAGE:$old"
      docker rmi "$IMAGE:$old" >/dev/null 2>&1 || true
    done

echo "✅ Wdrożono $VERSION"
echo "   Rollback: ./rollback.sh   (lista wersji: ./rollback.sh bez argumentu)"
