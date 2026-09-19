#!/usr/bin/env python3
"""Download the attachments of a Fastmail email to disk.

Usage:
    python3 scripts/download_attachment.py --id <email-id> --out <dir>
    python3 scripts/download_attachment.py --id <email-id> --out <dir> --name "Quote.pdf"
    python3 scripts/download_attachment.py --id <email-id> --out <dir> --index 0
    python3 scripts/download_attachment.py --id <email-id> --out <dir> --keep-name
    python3 scripts/download_attachment.py --id <email-id> --out <dir> --include-inline
    python3 scripts/download_attachment.py --id <email-id> --list

With neither --name nor --index, every attachment on the message is written.
Inline parts (signature images, embedded logos) are skipped in that case unless
--include-inline is passed; --name and --index reach them regardless.
Output filenames are kebab-cased by default (the repo file-naming rule); pass
--keep-name to write the attachment's own name verbatim. An existing file is
never overwritten unless --force is passed, and every download is checked
byte-for-byte against the size JMAP reported.

Output is JSON.
"""

import argparse
import json
import mimetypes
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.jmap import JmapClient, die

DEFAULT_TYPE = "application/octet-stream"


def slugify(name):
    """Kebab-case a filename, preserving its extension.

    "STEVE GODDING - CSV CUTLIST TEMPLATE.pdf" -> "steve-godding-csv-cutlist-template.pdf"
    """
    stem, dot, ext = name.rpartition(".")
    if not dot:  # no extension
        stem, ext = name, ""
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not slug:
        slug = "attachment"
    ext = re.sub(r"[^a-z0-9]+", "", ext.lower())
    return f"{slug}.{ext}" if ext else slug


def attachment_filename(att, index, keep_name):
    """Pick the on-disk filename for an attachment.

    Unnamed parts (inline images, some forwarded messages) get a positional
    name with an extension guessed from the content type.
    """
    name = (att.get("name") or "").strip()
    if not name:
        ext = mimetypes.guess_extension(att.get("type") or "") or ".bin"
        name = f"attachment-{index}{ext}"
    name = Path(name).name  # strip any path the sender smuggled in
    return name if keep_name else slugify(name)


def select(attachments, name, index, include_inline=False):
    """Narrow the attachment list to what the caller asked for.

    Indexes are positions in the full attachment list, so they line up with
    --list output. An explicit --name or --index reaches inline parts too;
    only the download-everything case filters them out.
    """
    if index is not None:
        if index < 0 or index >= len(attachments):
            die(f"No attachment at index {index}",
                attachment_count=len(attachments))
        return [(index, attachments[index])]

    if name is not None:
        target = name.strip().lower()
        matches = [(i, a) for i, a in enumerate(attachments)
                   if (a.get("name") or "").strip().lower() == target]
        if not matches:
            die(f"No attachment named {name!r}",
                available=[a.get("name") for a in attachments])
        return matches

    if include_inline:
        return list(enumerate(attachments))

    real = [(i, a) for i, a in enumerate(attachments)
            if a.get("disposition") != "inline"]
    if not real:
        die("Every part on this message is inline (signature images and the "
            "like). Pass --include-inline to download them anyway.",
            inline_count=len(attachments))
    return real


def fetch_attachments(client, email_id):
    resp = client.call([
        ["Email/get", {"ids": [email_id],
                       "properties": ["id", "subject", "attachments"]}, "a"],
    ])
    emails = client.first_result(resp)["list"]
    if not emails:
        die(f"Email not found: {email_id}")
    return emails[0], emails[0].get("attachments") or []


def main():
    p = argparse.ArgumentParser(description="Download Fastmail email attachments")
    p.add_argument("--id", required=True, help="Email id (from search results)")
    p.add_argument("--out", help="Directory to write into (created if needed)")
    p.add_argument("--name", help="Download only the attachment with this name")
    p.add_argument("--index", type=int,
                   help="Download only the attachment at this 0-based index")
    p.add_argument("--keep-name", action="store_true",
                   help="Write the attachment's own name instead of a kebab-cased one")
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing file")
    p.add_argument("--include-inline", action="store_true",
                   help="Also download inline parts (signature images, embedded logos)")
    p.add_argument("--list", action="store_true",
                   help="List the attachments without downloading anything")
    args = p.parse_args()

    if args.name and args.index is not None:
        die("Pass --name or --index, not both.")
    if not args.list and not args.out:
        die("--out is required unless --list is passed.")

    client = JmapClient()
    email, attachments = fetch_attachments(client, args.id)

    if not attachments:
        die(f"Email has no attachments: {args.id}", subject=email.get("subject"))

    if args.list:
        print(json.dumps({
            "id": email["id"],
            "subject": email.get("subject"),
            "attachments": [{
                "index": i,
                "name": a.get("name"),
                "type": a.get("type"),
                "size": a.get("size"),
                "disposition": a.get("disposition"),
                "suggested_filename": attachment_filename(a, i, args.keep_name),
            } for i, a in enumerate(attachments)],
        }, indent=2))
        return

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    chosen = select(attachments, args.name, args.index, args.include_inline)

    # Refuse the whole run before writing anything if a target already exists,
    # so a multi-attachment download is all-or-nothing.
    planned = []
    for i, att in chosen:
        path = out_dir / attachment_filename(att, i, args.keep_name)
        if path.exists() and not args.force:
            die(f"Refusing to overwrite existing file: {path} (use --force)",
                path=str(path))
        planned.append((i, att, path))

    written = []
    for i, att, path in planned:
        content_type = att.get("type") or DEFAULT_TYPE
        data = client.download_blob(
            att["blobId"], content_type, att.get("name") or path.name)

        expected = att.get("size")
        if expected is not None and len(data) != expected:
            die("Downloaded size does not match the size JMAP reported",
                attachment=att.get("name"), expected_bytes=expected,
                received_bytes=len(data))

        path.write_bytes(data)
        written.append({
            "index": i,
            "name": att.get("name"),
            "type": content_type,
            "size": len(data),
            "disposition": att.get("disposition"),
            "path": str(path),
        })

    print(json.dumps({
        "id": email["id"],
        "subject": email.get("subject"),
        "out_dir": str(out_dir),
        "downloaded": written,
        "count": len(written),
    }, indent=2))


if __name__ == "__main__":
    main()
