#!/usr/bin/env bash
#
# Rollback do wcześniejszej wersji obrazu.
#
#   ./rollback.sh            # pokaż dostępne wersje
#   ./rollback.sh <sha>      # przywróć konkretną wersję
#   ./rollback.sh --prev     # przywróć poprzednią (przedostatni DEPLOY z historii)
#
# Działa bez przebudowy: przestawia IMAGE_TAG w .env na istniejący, niezmienny
# obraz mieszkania:<sha> i recreate'uje kontener. Żadnego nadpisywania tagów.
#
# ⚠️  UWAGA o bazie danych:
#   Dane (SQLite + cache zdjęć) są we wspólnym wolumenie ./data i NIE są cofane.
#   Migracje schematu (_light_migrations w app/database.py) są jednokierunkowe —
#   dodają kolumny. Cofnięcie kodu jest bezpieczne, dopóki migracja tylko
#   DODAWAŁA rzeczy (stary kod ignoruje nadmiarowe kolumny). Jeśli nowa wersja
#   USUWAŁA/zmieniała kolumny, zrób wcześniej kopię ./data.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="mieszkania"
SERVICE="app"

cd "$REPO_DIR"

set_image_tag() {
  local tag="$1"
  if grep -q '^IMAGE_TAG=' .env; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$tag|" .env
  else
    printf 'IMAGE_TAG=%s\n' "$tag" >> .env
  fi
}

current_tag() { grep '^IMAGE_TAG=' .env 2>/dev/null | tail -n1 | cut -d= -f2-; }

list_versions() {
  echo "Wersja live: $(current_tag || echo '(brak IMAGE_TAG w .env)')"
  echo
  echo "Dostępne obrazy (najnowsze u góry):"
  docker images "$IMAGE" --format '  {{.Tag}}\t{{.CreatedSince}}\t{{.ID}}' | grep -vP '^  dev\t' || true
  if [ -f .deploy_history ]; then
    echo
    echo "Ostatnie wdrożenia (.deploy_history):"
    tail -n 8 .deploy_history | sed 's/^/  /'
  fi
}

TARGET="${1:-}"

if [ -z "$TARGET" ]; then
  list_versions
  echo
  echo "Użycie: ./rollback.sh <sha> | --prev"
  exit 0
fi

if [ "$TARGET" = "--prev" ]; then
  # Przedostatni DEPLOY z historii (ostatni = obecnie wdrożony).
  TARGET="$(grep -P '\tDEPLOY\t' .deploy_history 2>/dev/null | tail -n 2 | head -n 1 | cut -f3 || true)"
  if [ -z "$TARGET" ]; then
    echo "❌ Nie znaleziono poprzedniej wersji w .deploy_history." >&2
    list_versions
    exit 1
  fi
  echo "ℹ️  Poprzednia wersja wg historii: $TARGET"
fi

if ! docker image inspect "$IMAGE:$TARGET" >/dev/null 2>&1; then
  echo "❌ Nie ma obrazu $IMAGE:$TARGET" >&2
  list_versions
  exit 1
fi

echo "▶ Rollback do $TARGET"
set_image_tag "$TARGET"
docker compose up -d --force-recreate "$SERVICE"

CONTAINER="$(docker compose ps -q "$SERVICE")"
echo "⏳ Czekam aż kontener będzie healthy..."
for _ in $(seq 1 30); do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER" 2>/dev/null || echo unknown)"
  case "$status" in
    healthy) echo "✅ healthy"; break ;;
    unhealthy) echo "❌ kontener unhealthy — sprawdź: docker compose logs $SERVICE"; exit 1 ;;
    none) break ;;
  esac
  sleep 2
done

printf '%s\tROLLBACK\t%s\t-\n' "$(date -Iseconds)" "$TARGET" >> "$REPO_DIR/.deploy_history"
echo "✅ Przywrócono $TARGET (IMAGE_TAG w .env zaktualizowany)."
echo "   Uwaga: working tree dalej wskazuje aktualny commit — cofnięty jest TYLKO obraz."
echo "   Aby zsynchronizować też kod: git checkout $TARGET"
