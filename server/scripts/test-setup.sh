#!/bin/bash
set -e

echo "Testing Claude Insights Server setup..."

# Wait for services
echo "Waiting for services to be healthy..."
sleep 5

# Test API health
echo "Testing API health..."
curl -sf http://localhost:8080/health | grep -q "ok" && echo "✓ API healthy" || echo "✗ API failed"

# Test Dashboard health
echo "Testing Dashboard health..."
curl -sf http://localhost:8081/health | grep -q "ok" && echo "✓ Dashboard healthy" || echo "✗ Dashboard failed"

# Create test user
echo "Creating test user..."
docker compose exec -T api python -m app.cli create-user testuser --email test@dkd.de > /tmp/api_key.txt 2>&1
API_KEY=$(grep "dkd_sk_" /tmp/api_key.txt | awk '{print $NF}')

if [ -n "$API_KEY" ]; then
    echo "✓ User created"

    # Test session upload
    echo "Testing session upload..."
    RESPONSE=$(curl -sf -X POST http://localhost:8080/api/v1/sessions \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $API_KEY" \
        -d '{
            "session_id": "test-123",
            "project_name": "test-project",
            "started_at": "2026-01-22T10:00:00Z",
            "ended_at": "2026-01-22T11:00:00Z",
            "total_messages": 10,
            "total_tokens_in": 5000,
            "total_tokens_out": 2000,
            "tools": {"Read": {"count": 5, "success": 5}},
            "tags": ["testing"]
        }')

    echo $RESPONSE | grep -q "ok" && echo "✓ Session upload works" || echo "✗ Session upload failed"

    # Test team stats
    echo "Testing team stats..."
    curl -sf http://localhost:8080/api/v1/team/stats | grep -q "total_sessions" && echo "✓ Team stats work" || echo "✗ Team stats failed"

    # Cleanup test user
    docker compose exec -T api python -m app.cli delete-user testuser
    echo "✓ Test user cleaned up"
else
    echo "✗ Failed to create user"
fi

echo ""
echo "Setup test complete!"
