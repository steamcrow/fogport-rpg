# Fogport RPG — Kanka Librarian

A safe, approval-first bridge between ChatGPT-driven RPG sessions and Kanka.

## Current milestone

This starter is **read-only**. It can:

- authenticate with a Kanka API token stored outside GitHub;
- list every Kanka campaign/world the account can access;
- provide the foundation for reading campaign entities later.

It does **not** create, update, or delete Kanka data yet.

## Safety rules

- Never commit a real Kanka API token.
- Keep all Kanka write operations disabled until an approval workflow exists.
- Never delete campaign data through the AI bridge.
- Separate player-facing canon from Kanka Secret/GM material.
- Preserve nested locations, such as `World > Sayir Sea > Fogport > District > Subdistrict > Twisted Eel > Room`.

## Run locally

1. Install Python 3.11 or newer.
2. Copy `.env.example` to `.env`.
3. Put your Kanka token in `.env`.
4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. List available campaigns:

   ```bash
   python scripts/list_campaigns.py
   ```

## API token

Kanka tokens are secrets and expire after roughly one year. The token belongs in a local `.env` file or an encrypted hosting secret—not in this repository.

## Planned phases

1. Read-only campaign discovery.
2. Read characters, locations, organizations, notes, journals, tags, and relations.
3. Prepare proposed Kanka changes as a reviewable change set.
4. Apply only explicitly approved changes.
5. Support multiple Kanka worlds using friendly campaign names and IDs.
