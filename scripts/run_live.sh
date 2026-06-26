#!/bin/bash
echo "WARNING: LIVE TRADING MODE"
read -p "Are you sure? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    export ENV_STAGE=prod
    export LIVE_MODE=true
    uvicorn backend.app.main:app
fi
