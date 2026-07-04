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
