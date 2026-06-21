#!/usr/bin/env bash
# AGY Agent Tools installer for Linux devices

set -e

echo -e "\033[1;36m⚡ Setting up AGY Download Monitor & Tools...\033[0m"

# 1. Create required directories
echo "Creating folder structure in ~/Documents/agy-agent/..."
mkdir -p "$HOME/Documents/agy-agent"/{bin,chats,downloads/active,logs}

# 2. Copy scripts to bin folder (if running from an extracted folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" != "$HOME/Documents/agy-agent" ] && [ -d "$SCRIPT_DIR/bin" ]; then
    echo "Copying scripts to bin folder..."
    cp -r "$SCRIPT_DIR/bin"/* "$HOME/Documents/agy-agent/bin/"
fi

# 3. Set executable permissions
echo "Setting executable permissions..."
chmod +x "$HOME/Documents/agy-agent/bin"/*

# 4. Add to PATH in ~/.bashrc if not already present
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ]; then
    if ! grep -q "agy-agent/bin" "$BASHRC"; then
        echo "Adding agy-agent bin directory to PATH in ~/.bashrc..."
        echo -e '\n# AGY Agent tools\nexport PATH="$HOME/Documents/agy-agent/bin:$PATH"' >> "$BASHRC"
        echo -e "\033[1;32m✓ PATH updated. Please run 'source ~/.bashrc' or restart your terminal.\033[0m"
    else
        echo "PATH is already configured in ~/.bashrc."
    fi
fi

echo -e "\033[1;32m✓ Setup complete!\033[0m"
echo -e "You can now run:"
echo -e "  - \033[1m_agy-monitor_\033[0m to launch the multi-download dashboard"
echo -e "  - \033[1m_agy-run-dl_\033[0m to run and track downloads"
echo -e "  - \033[1m_agy-save-chat_\033[0m to save chat transcripts"
