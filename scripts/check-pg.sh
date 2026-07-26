#!/bin/bash
docker exec postgres psql -U admin -d studio -c "SELECT id, email, is_active FROM \"user\" LIMIT 5;" 2>&1
echo "---"
docker exec postgres psql -U admin -d studio -c "SELECT current_database(), version();" 2>&1
