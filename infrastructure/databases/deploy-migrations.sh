#!/bin/bash

echo "🚀 Deploying Database Migration System..."
echo ""

# Step 1: Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r infrastructure/databases/requirements.txt
echo ""

# Step 2: Start databases
echo "🐳 Starting databases..."
docker-compose -f docker-compose-simple.yml up -d
echo ""

# Wait for databases to be ready
echo "⏳ Waiting for databases to be ready..."
sleep 10
echo ""

# Step 3: Run all migrations (auto-detects all databases)
echo "🗄️  Running ALL migrations..."
python3 infrastructure/databases/cli.py migrate:all
echo ""

# Step 4: Run all seeders (auto-detects all databases)
echo "🌱 Running ALL seeders..."
python3 infrastructure/databases/cli.py seed:all
echo ""

# Step 6: Verify
echo "✅ Verifying deployment..."
python3 infrastructure/databases/cli.py migrate:status --database postgres --postgres-db auth_db
echo ""

echo "🎉 Deployment complete!"
echo ""
echo "═══════════════════════════════════════════════"
echo "Default Admin Credentials:"
echo "  Email:    admin@ai4i.org"
echo "  Username: admin"
echo "  Password: Admin@123"
echo "═══════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Test admin login"
echo "  2. Connect your application"
echo "  3. Create new migrations as needed"
echo ""
