#!/bin/bash
# Database Backup Script for MusicBot

BACKUP_DIR="/var/www/musicbot/backups"
mkdir -p "$BACKUP_DIR"

# Read DATABASE_URL from .env file
if [ -f "/var/www/musicbot/.env" ]; then
    # Extract DATABASE_URL value
    DB_URL=$(grep "^DATABASE_URL=" /var/www/musicbot/.env | cut -d'=' -f2-)
fi

if [ -z "$DB_URL" ]; then
    echo "❌ DATABASE_URL is not set in .env file."
    exit 1
fi

# Generate filename with date/time
FILENAME="$BACKUP_DIR/db_backup_$(date +%F_%H-%M-%S).sql"

# Dump database
pg_dump "$DB_URL" > "$FILENAME"

# Gzip the file
gzip "$FILENAME"

# Clean up backups older than 7 days
find "$BACKUP_DIR" -type f -name "db_backup_*.sql.gz" -mtime +7 -delete

echo "✅ Database backup completed: ${FILENAME}.gz"

# Telegram log kanaliga bildirishnoma yuborish
BOT_TOKEN=$(grep "^ADMIN_BOT_TOKEN=" /var/www/musicbot/.env | cut -d'=' -f2-)
LOG_CHAT=$(grep "^LOG_CHANNEL_ID=" /var/www/musicbot/.env | cut -d'=' -f2-)
if [ -n "$BOT_TOKEN" ] && [ -n "$LOG_CHAT" ] && [ "$LOG_CHAT" != "0" ]; then
    FILE_SIZE=$(du -h "${FILENAME}.gz" | cut -f1)
    DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
    MSG="💾 <b>PostgreSQL Avtomatik Zaxira (Backup)</b>%0A%0A✅ Fayl: <code>$(basename "${FILENAME}.gz")</code>%0A📦 Hajm: <b>${FILE_SIZE}</b>%0A💽 Diskda bo'sh joy: <b>${DISK_FREE}</b>"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
         -d "chat_id=${LOG_CHAT}" \
         -d "text=${MSG}" \
         -d "parse_mode=HTML" > /dev/null
fi
