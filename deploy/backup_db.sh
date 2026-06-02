#!/usr/bin/env bash
# Sauvegarde PostgreSQL de Nyris (pg_dump format custom).
# Logs -> stdout (capté par journald via systemd). Aucun fichier de log.
set -euo pipefail

ENV_FILE="/srv/nyris/config/.env"
BACKUP_DIR="/srv/nyris/backups"
RETENTION=14

# 1. Charge POSTGRES_* depuis le .env (fichier maîtrisé, pas de secret en dur)
if [ ! -r "$ENV_FILE" ]; then
  echo "ERREUR: $ENV_FILE introuvable ou illisible" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# 2. Dossier de backup : vérifié / créé avec permissions sûres
umask 077
mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"

# 3. Dump
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/nyris_${TS}.dump"
echo "Backup Nyris -> $OUT"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -Fc -f "$OUT"

# 4. Garde-fou : dump non vide
if [ ! -s "$OUT" ]; then
  echo "ERREUR: dump vide, suppression" >&2
  rm -f "$OUT"
  exit 1
fi

# 5. Rotation : conserver les RETENTION plus récents
ls -1t "$BACKUP_DIR"/nyris_*.dump 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -r rm -f

COUNT="$(ls -1 "$BACKUP_DIR"/nyris_*.dump 2>/dev/null | wc -l)"
echo "Backup OK: $OUT ($(du -h "$OUT" | cut -f1)) — $COUNT backup(s) conservé(s)"
