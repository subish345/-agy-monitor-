#!/usr/bin/env python3
import os
import base64

AGENT_DIR = os.path.expanduser("~/Documents/agy-agent")
BIN_DIR = os.path.join(AGENT_DIR, "bin")

FILES = [
    "agy-monitor",
    "agy-monitor.py",
    "agy-run-dl",
    "agy-save-chat",
    "agy-save-chat.py"
]

installer_template = """#!/usr/bin/env bash
# AGY Agent Tools self-contained installer

set -e

echo -e "\\033[1;36m⚡ Installing AGY Download Monitor & Tools...\\033[0m"

# Create folders
mkdir -p "$HOME/Documents/agy-agent/bin"
mkdir -p "$HOME/Documents/agy-agent/chats"
mkdir -p "$HOME/Documents/agy-agent/downloads/active"
mkdir -p "$HOME/Documents/agy-agent/logs"

# Write embedded files
echo "Extracting tools..."
{embedded_files}

# Permissions
chmod +x "$HOME/Documents/agy-agent/bin"/*

# Configure PATH
BASHRC="$HOME/.bashrc"
if [ -f "$BASHRC" ]; then
    if ! grep -q "agy-agent/bin" "$BASHRC"; then
        echo "Adding agy-agent to PATH in ~/.bashrc..."
        echo -e '\\n# AGY Agent tools\\nexport PATH="$HOME/Documents/agy-agent/bin:$PATH"' >> "$BASHRC"
        echo -e "\\033[1;32m✓ PATH configured. Please run 'source ~/.bashrc' or open a new terminal.\\033[0m"
    else
        echo "PATH is already configured."
    fi
fi

echo -e "\\033[1;32m✓ Installation successful!\\033[0m"
"""

embedded_blocks = []
for filename in FILES:
    filepath = os.path.join(BIN_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        block = f"""
echo "  -> {filename}"
cat << 'EOF' | base64 -d > "$HOME/Documents/agy-agent/bin/{filename}"
{content_b64}
EOF
"""
        embedded_blocks.append(block)

full_installer = installer_template.format(embedded_files="\n".join(embedded_blocks))

with open(os.path.join(AGENT_DIR, "install.sh"), 'w') as f:
    f.write(full_installer)

print("Self-contained installer generated successfully at ~/Documents/agy-agent/install.sh")
