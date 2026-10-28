"""Dépose les prix du jour dans un brouillon Gmail, lu par la page « Cote de mes cartes Pokémon ».

Lancé par GitHub (workflow brouillon-gmail.yml) juste après le relevé quotidien.
Aucun mail n'est envoyé : le message est seulement rangé dans les brouillons (IMAP),
avec l'adresse et le mot de passe d'application Google des secrets GMAIL_ADDRESS et
GMAIL_APP_PASSWORD. Les anciens brouillons « pokemon-watch prix » vont à la corbeille.
"""
import email.policy
import imaplib
import json
import os
import re
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import export_draft

SUBJECT_PREFIX = "pokemon-watch prix"


def quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def special_folder(imap, flag):
    """Nom IMAP du dossier spécial (\\Drafts, \\Trash), quelle que soit la langue de Gmail."""
    _, lines = imap.list()
    for raw in lines or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        if flag.lower() in line.lower():
            match = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', line)
            if match:
                return match.group(1).replace('\\"', '"').replace("\\\\", "\\")
            return line.rsplit(" ", 1)[-1]
    return None


def build_message(address):
    export_draft.main()  # écrit draft_body.txt
    body = Path("draft_body.txt").read_text(encoding="ascii")
    date = json.loads(body.splitlines()[1])["date"]
    msg = EmailMessage()
    msg["From"] = address
    msg["Subject"] = f"{SUBJECT_PREFIX} {date}"
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="pokemon-watch.local")
    msg.set_content(body, charset="us-ascii", cte="quoted-printable")
    return msg, date


def main():
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not address or not password:
        raise SystemExit("Secrets GMAIL_ADDRESS ou GMAIL_APP_PASSWORD absents : brouillon non créé")

    msg, date = build_message(address)
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(address, password)
        drafts = special_folder(imap, "\\Drafts")
        trash = special_folder(imap, "\\Trash")
        if not drafts:
            raise SystemExit("Dossier des brouillons Gmail introuvable")

        typ, resp = imap.append(quote(drafts), "(\\Draft \\Seen)",
                                imaplib.Time2Internaldate(time.time()),
                                msg.as_bytes(policy=email.policy.SMTP))
        if typ != "OK":
            raise SystemExit(f"Gmail a refusé le brouillon : {resp}")
        found = re.search(rb"APPENDUID \d+ (\d+)", b" ".join(r for r in resp if isinstance(r, bytes)))
        new_uid = int(found.group(1)) if found else None
        print(f"Brouillon « {msg['Subject']} » créé")

        # Anciens brouillons des prix : à la corbeille (vidée automatiquement par Gmail)
        imap.select(quote(drafts))
        _, data = imap.uid("SEARCH", None, "HEADER", "Subject", f'"{SUBJECT_PREFIX}"')
        uids = [int(u) for u in (data[0] or b"").split()]
        if new_uid is None and uids:
            new_uid = max(uids)
        old = [str(u) for u in uids if u != new_uid]
        if old:
            ids = ",".join(old)
            if trash and imap.uid("MOVE", ids, quote(trash))[0] == "OK":
                print(f"{len(old)} ancien(s) brouillon(s) mis à la corbeille")
            else:
                imap.uid("STORE", ids, "+FLAGS", "(\\Deleted)")
                imap.expunge()
                print(f"{len(old)} ancien(s) brouillon(s) retiré(s)")
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    print(f"DERNIER_RELEVE={date}")


if __name__ == "__main__":
    main()
