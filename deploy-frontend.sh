#!/bin/bash
# Frontend deployment script for Railway

echo "🚀 Deploying Boulder Web App v2 Frontend to Railway..."

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    brew install railway
fi

# Login to Railway (if not already logged in)
echo "🔐 Checking Railway authentication..."
railway whoami || railway login

# Create new Railway project for frontend
echo "📦 Creating Railway project for frontend..."
railway new --name boulder-web-app-2-frontend

# Deploy the frontend
echo "🚀 Deploying frontend..."
railway up

# Get the frontend URL
echo "🌐 Getting frontend URL..."
railway domain

echo "✅ Frontend deployment complete!"
echo "🔗 Update the BACKEND_URL in app.js with your actual Railway backend URL"
