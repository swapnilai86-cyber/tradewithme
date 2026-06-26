#!/bin/bash
echo "Setting up environment..."
cp .env.example .env
npm install --prefix frontend
echo "Setup complete."
