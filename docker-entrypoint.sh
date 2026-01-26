#!/bin/bash
# Docker entrypoint script for KMS Backend
# Handles SSH key permissions for remote GPU monitoring

# Setup SSH keys with proper permissions
if [ -d "/tmp/.ssh-source" ]; then
    echo "Setting up SSH keys..."
    mkdir -p /root/.ssh

    # Copy SSH keys
    if [ -f "/tmp/.ssh-source/id_ed25519" ]; then
        cp /tmp/.ssh-source/id_ed25519 /root/.ssh/id_ed25519
        chmod 600 /root/.ssh/id_ed25519
    fi

    if [ -f "/tmp/.ssh-source/id_rsa" ]; then
        cp /tmp/.ssh-source/id_rsa /root/.ssh/id_rsa
        chmod 600 /root/.ssh/id_rsa
    fi

    if [ -f "/tmp/.ssh-source/known_hosts" ]; then
        cp /tmp/.ssh-source/known_hosts /root/.ssh/known_hosts
        chmod 644 /root/.ssh/known_hosts
    fi

    if [ -f "/tmp/.ssh-source/config" ]; then
        cp /tmp/.ssh-source/config /root/.ssh/config
        chmod 600 /root/.ssh/config
    fi

    chmod 700 /root/.ssh
    echo "SSH keys configured."
fi

# Execute the main command
exec "$@"
