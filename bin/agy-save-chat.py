#!/usr/bin/env python3
"""
AGY Chat Saver — Saves conversation transcripts to ~/Documents/agy-agent/chats/

Usage:
  agy-save-chat <conversation-id> [--label "description"]
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime


AGY_BRAIN = os.path.expanduser("~/.gemini/antigravity-cli/brain")
SAVE_DIR = os.path.expanduser("~/Documents/agy-agent/chats")


def save_chat(conv_id, label=None):
    """Save a conversation transcript to the agy-agent chats folder."""
    os.makedirs(SAVE_DIR, exist_ok=True)

    # Find transcript
    log_dir = os.path.join(AGY_BRAIN, conv_id, ".system_generated", "logs")
    transcript_file = os.path.join(log_dir, "transcript.jsonl")
    transcript_full = os.path.join(log_dir, "transcript_full.jsonl")

    if not os.path.exists(transcript_file):
        print(f"\033[1;31m✗\033[0m No transcript found for: {conv_id}")
        print(f"  Looked in: {log_dir}")
        return False

    # Create readable summary
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_label = (label or "chat").replace(" ", "_").replace("/", "-")[:50]
    folder_name = f"{timestamp}_{safe_label}"
    dest_dir = os.path.join(SAVE_DIR, folder_name)
    os.makedirs(dest_dir, exist_ok=True)

    # Copy raw transcripts
    shutil.copy2(transcript_file, os.path.join(dest_dir, "transcript.jsonl"))
    if os.path.exists(transcript_full):
        shutil.copy2(transcript_full, os.path.join(dest_dir, "transcript_full.jsonl"))

    # Generate human-readable markdown summary
    summary_lines = []
    summary_lines.append(f"# AGY Chat Record")
    summary_lines.append(f"")
    summary_lines.append(f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append(f"- **Conversation ID**: `{conv_id}`")
    if label:
        summary_lines.append(f"- **Label**: {label}")
    summary_lines.append(f"")
    summary_lines.append(f"---")
    summary_lines.append(f"")

    try:
        with open(transcript_file, "r") as f:
            for line in f:
                try:
                    step = json.loads(line.strip())
                    step_type = step.get("type", "")
                    content = step.get("content", "")
                    source = step.get("source", "")

                    if step_type == "USER_INPUT" and content:
                        summary_lines.append(f"## 👤 User")
                        summary_lines.append(f"")
                        summary_lines.append(content[:2000])
                        summary_lines.append(f"")
                    elif step_type == "PLANNER_RESPONSE" and content:
                        summary_lines.append(f"## 🤖 AGY")
                        summary_lines.append(f"")
                        # Truncate very long responses
                        if len(content) > 3000:
                            summary_lines.append(content[:3000])
                            summary_lines.append(f"\n*...truncated ({len(content)} chars total)*\n")
                        else:
                            summary_lines.append(content)
                        summary_lines.append(f"")
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        summary_lines.append(f"*Error reading transcript: {e}*")

    # Write summary
    summary_path = os.path.join(dest_dir, "README.md")
    with open(summary_path, "w") as f:
        f.write("\n".join(summary_lines))

    # Write metadata
    meta = {
        "conversation_id": conv_id,
        "label": label,
        "saved_at": datetime.now().isoformat(),
        "folder": folder_name,
    }
    with open(os.path.join(dest_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\033[1;32m✓\033[0m Chat saved to: {dest_dir}")
    print(f"  📄 README.md — Human-readable summary")
    print(f"  📋 transcript.jsonl — Raw transcript")
    if os.path.exists(transcript_full):
        print(f"  📋 transcript_full.jsonl — Full transcript")
    print(f"  📎 metadata.json — Metadata")
    return True


def list_chats():
    """List all saved chats."""
    if not os.path.exists(SAVE_DIR):
        print("No saved chats yet.")
        return

    chats = sorted(os.listdir(SAVE_DIR), reverse=True)
    if not chats:
        print("No saved chats yet.")
        return

    print(f"\033[1;36m📚 Saved Chats ({len(chats)})\033[0m\n")
    for chat in chats:
        meta_path = os.path.join(SAVE_DIR, chat, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            label = meta.get("label", "unlabeled")
            saved = meta.get("saved_at", "?")[:19]
            conv = meta.get("conversation_id", "?")[:12]
            print(f"  📁 {chat}")
            print(f"     Label: {label} │ Saved: {saved} │ ID: {conv}...")
        else:
            print(f"  📁 {chat}")
        print()


def main():
    parser = argparse.ArgumentParser(description="AGY Chat Saver")
    sub = parser.add_subparsers(dest="command")

    save_cmd = sub.add_parser("save", help="Save a conversation")
    save_cmd.add_argument("conv_id", help="Conversation ID")
    save_cmd.add_argument("--label", "-l", help="Description label for the chat")

    sub.add_parser("list", help="List saved chats")

    args = parser.parse_args()

    if args.command == "save":
        save_chat(args.conv_id, args.label)
    elif args.command == "list":
        list_chats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
