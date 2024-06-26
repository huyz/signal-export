"""Extract data from Signal DB."""

import json
from pathlib import Path

from pysqlcipher3 import dbapi2 as sqlcipher

from sigexport import models
from sigexport.logging import log


def fetch_data(
    db_file: Path,
    key: str,
    chats: str | None = None,
    include_empty: bool = False,
) -> tuple[models.Convos, models.Contacts]:
    """Load SQLite data into dicts."""
    contacts: models.Contacts = {}
    convos: models.Convos = {}
    chats_list = chats.split(",") if chats else []

    db = sqlcipher.connect(str(db_file))  # type: ignore
    c = db.cursor()
    # param binding doesn't work for pragmas, so use a direct string concat
    c.execute(f"PRAGMA KEY = \"x'{key}'\"")
    c.execute("PRAGMA cipher_page_size = 4096")
    c.execute("PRAGMA kdf_iter = 64000")
    c.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
    c.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")

    query = "SELECT type, id, e164, name, profileName, members FROM conversations"
    c.execute(query)
    for result in c:
        log(f"\tLoading SQL results for: {result[3]}, aka {result[4]}")
        members = []
        if result[5]:
            members = result[5].split(" ")
        is_group = result[0] == "group"
        cid = result[1]
        contacts[cid] = models.Contact(
            id=cid,
            name=result[3],
            number=result[2],
            profile_name=result[4],
            members=members,
            is_group=is_group,
        )
        if contacts[cid].name is None:
            contacts[cid].name = contacts[cid].profile_name

        if not chats or (result[3] in chats_list or result[4] in chats_list):
            convos[cid] = []

    query = "SELECT json, conversationId FROM messages ORDER BY sent_at"
    c.execute(query)
    for result in c:
        res = json.loads(result[0])
        cid = result[1]
        if cid and cid in convos:
            if res.get("type") in ["keychange", "profile-change"]:
                continue
            con = models.RawMessage(
                conversation_id=res["conversationId"],
                id=res["id"],
                type=res.get("type"),
                body=res.get("body", ""),
                contact=res.get("contact"),
                source=res.get("source"),
                timestamp=res.get("timestamp"),
                sent_at=res.get("sent_at"),
                has_attachments=res.get("has_attachments", False),
                attachments=res.get("attachments", []),
                read_status=res.get("read_status"),
                seen_status=res.get("seen_status"),
                call_history=res.get("call_history"),
                reactions=res.get("reactions", []),
                sticker=res.get("sticker"),
                quote=res.get("quote"),
            )
            convos[cid].append(con)

    if not include_empty:
        convos = {key: val for key, val in convos.items() if len(val) > 0}

    return convos, contacts
