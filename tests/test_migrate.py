"""v1 -> v2 migration (R9.5) against a faithful synthetic v1 tree."""

import hashlib
import json
import secrets

import pytest

from agentbridge.migrate import migrate
from agentbridge.mesh.service import Mesh
from agentbridge.transport.folder import FolderTransport


def v1_hash_password(password: str) -> dict:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return {"salt": salt, "hash": dk.hex(), "iterations": 200_000}


def v1_msg(ns: int, sender: str, body: str, kind: str = "human", **extra) -> dict:
    return {"id": f"{ns:x}-{sender}", "ns": ns, "ts": "2026-07-10T10:00:00Z",
            "from": sender, "kind": kind, "body": body,
            "tags": [], "files": [], **extra}


@pytest.fixture
def v1_tree(tmp_path):
    """A miniature but shape-faithful v1 mesh (fields read from v1 mesh.py)."""
    src = tmp_path / "v1mesh"
    (src / "users").mkdir(parents=True)
    (src / "users" / "aryan.json").write_text(json.dumps({
        "username": "aryan", "kind": "human", "display": "Aryan Kumar",
        "created": "2026-07-01T09:00:00Z", "auth": v1_hash_password("aryan-legacy"),
    }), encoding="utf-8")
    (src / "users" / "fable.json").write_text(json.dumps({
        "username": "fable", "kind": "human", "display": "Fable",
        "created": "2026-07-01T09:05:00Z", "auth": v1_hash_password("fable-legacy"),
    }), encoding="utf-8")
    (src / "users" / "claude.json").write_text(json.dumps({
        "username": "claude", "kind": "agent", "display": "Claude",
        "created": "2026-07-01T09:10:00Z", "owners": ["aryan"],
        "settings": {"model": "opus", "default_rule": "tagged", "rules": {}},
    }), encoding="utf-8")

    chat = src / "chats" / "qa-room-abc123"
    (chat / "msgs").mkdir(parents=True)
    (chat / "state").mkdir()
    (chat / "files").mkdir()
    (chat / "meta.json").write_text(json.dumps({
        "id": "qa-room-abc123", "kind": "group", "name": "QA Room",
        "created": "2026-07-05T08:00:00Z", "created_by": "aryan",
        "owner": "aryan", "members": ["aryan", "fable", "claude"],
        "archived": False, "color": "#3B82F6",
        "pins": [{"id": f"{2000:x}-fable", "by": "aryan",
                  "at": "2026-07-10T11:00:00Z", "until": "2099-01-01T00:00:00Z"}],
    }), encoding="utf-8")

    aryan_lines = [
        v1_msg(1000, "aryan", "first message ever"),
        v1_msg(3000, "aryan", "this one gets deleted"),
        {"id": f"{3500:x}-aryan", "ns": 3500, "ts": "2026-07-10T10:20:00Z",
         "from": "aryan", "kind": "info", "event": "added",
         "target": "claude", "body": "@aryan added @claude", "tags": [], "files": []},
    ]
    fable_lines = [
        v1_msg(2000, "fable", "typo mesage",
               reply_to={"id": f"{1000:x}-aryan", "from": "aryan",
                         "body": "first message ever"}),
    ]
    claude_lines = [v1_msg(4000, "claude", "agent says hello", kind="agent")]
    for name, lines in (("aryan", aryan_lines), ("fable", fable_lines),
                        ("claude", claude_lines)):
        (chat / "msgs" / f"{name}.jsonl").write_text(
            "".join(json.dumps(m) + "\n" for m in lines), encoding="utf-8")

    (chat / "redactions.json").write_text(json.dumps({
        f"{3000:x}-aryan": {"by": "aryan", "at": "2026-07-10T10:30:00Z"},
    }), encoding="utf-8")
    (chat / "edits.json").write_text(json.dumps({
        f"{2000:x}-fable": {"body": "typo message, fixed", "tags": [],
                            "by": "fable", "at": "2026-07-10T10:10:00Z"},
    }), encoding="utf-8")
    (chat / "state" / "fable.json").write_text(json.dumps({
        "read_ts": "2026-07-10T12:00:00Z", "read_ns": 5000,
        "starred": {f"{1000:x}-aryan": {"from": "aryan", "body": "first message ever",
                                        "ts": "2026-07-10T10:00:00Z"}},
        "hidden": [], "pinned": True,
    }), encoding="utf-8")
    (chat / "files" / "notes.txt").write_bytes(b"attachment payload")
    return src


@pytest.fixture
def migrated(v1_tree, tmp_path):
    dest = tmp_path / "mesh2"
    report = migrate(v1_tree, dest, dry_run=False)
    return dest, report, tmp_path


def mk(dest, tmp_path, user):
    return Mesh(FolderTransport(dest), user, "mach1",
                home=tmp_path / f"home-{user}")


# ------------------------------------------------------------------- report

def test_report_and_verification(migrated):
    _, report, _ = migrated
    assert report.users == 3 and report.chats == 1
    assert report.messages == 4          # 3 human/agent + ... (info counted apart)
    assert report.info_events == 2       # genesis + the v1 'added' pill
    assert report.blobs == 1
    assert report.verified, report.warnings
    assert report.warnings == []


def test_dry_run_writes_nothing(v1_tree, tmp_path):
    dest = tmp_path / "never-created"
    report = migrate(v1_tree, dest, dry_run=True)
    assert not dest.exists()
    assert report.users == 3 and report.chats == 1 and report.verified


def test_refuses_nonempty_destination(v1_tree, tmp_path):
    dest = tmp_path / "occupied"
    dest.mkdir()
    (dest / "something.txt").write_text("here first")
    with pytest.raises(SystemExit):
        migrate(v1_tree, dest)


# ------------------------------------------------------------------ accounts

def test_accounts_carry_over_and_legacy_login_works(migrated):
    dest, _, tmp = migrated
    aryan = mk(dest, tmp, "aryan")
    try:
        assert aryan.directory.kind("claude").value == "agent"
        assert aryan.directory.owner_of("claude") == "aryan"
        acc = aryan.directory.get("claude")
        assert acc.agent.machine == "migrated"
        assert acc.agent.harness["model"] == "opus"   # v1 settings preserved

        # the PBKDF2 record verifies in v2 (upgrade happens at login, R13)
        assert aryan.accounts.verify_password("aryan", "aryan-legacy")
        assert not aryan.accounts.verify_password("aryan", "wrong")
        # and password change moves the record to scrypt
        aryan.accounts.change_password("aryan-legacy", "fresh-pass-1")
        doc = aryan.tx.get_doc("users/aryan.json")
        assert doc["auth"]["algo"] == "scrypt"
        assert aryan.accounts.verify_password("aryan", "fresh-pass-1")
    finally:
        aryan.close()


# --------------------------------------------------------------------- chats

def test_chat_reads_correctly_for_members(migrated):
    dest, _, tmp = migrated
    fable = mk(dest, tmp, "fable")
    try:
        chats = fable.membership.chats_for()
        assert [c.id for c in chats] == ["qa-room-abc123"]
        snap = chats[0]
        assert snap.name == "QA Room"
        assert snap.members["aryan"].role.value == "admin"   # v1 owner -> admin
        assert snap.members["claude"].role.value == "member"

        fable.sync.sync_once([snap.id])
        msgs = fable.messages_for(snap.id)
        bodies = {m.id: m.body for m in msgs if m.kind.value == "message"}
        assert bodies[f"{1000:x}-aryan"] == "first message ever"
        assert bodies[f"{4000:x}-claude"] == "agent says hello"

        # the redacted one is a tombstone, never its old text
        gone = [m for m in msgs if m.id == f"{3000:x}-aryan"][0]
        assert gone.deleted and gone.body == ""

        # the edit applied, and its v1 timestamp keeps it read (no phantom
        # unread: fable's migrated read_ns=5000 > the edit's derived ns)
        edited = [m for m in msgs if m.id == f"{2000:x}-fable"][0]
        assert edited.body == "typo message, fixed" and edited.edited
        assert fable.unread(snap.id)["unread"] == 0

        # reply quote survived
        assert edited.reply_to["id"] == f"{1000:x}-aryan"

        # v1 star SNAPSHOT became an id, resolved live
        starred = fable.starred(snap.id)
        assert [m.id for m in starred] == [f"{1000:x}-aryan"]

        # pin carried; the v1 info pill is an inert legacy note
        assert f"{2000:x}-fable" in fable.pins(snap.id)
        pills = [m for m in msgs if m.event]
        assert any(m.event.get("type") == "legacy_note" for m in pills)
    finally:
        fable.close()


def test_meta_self_heals_after_migration(migrated):
    dest, _, tmp = migrated
    aryan = mk(dest, tmp, "aryan")
    try:
        chat_id = "qa-room-abc123"
        good = aryan.snapshot(chat_id).to_dict()
        aryan.tx.put_doc(f"chats/{chat_id}/meta.json",
                         {"id": chat_id, "kind": "group", "name": "WRECKED",
                          "members": {}})
        aryan.sync.sync_once([chat_id])
        healed = aryan.membership.refold(chat_id)
        assert healed.to_dict()["members"] == good["members"]
        assert healed.name == "QA Room"
    finally:
        aryan.close()


def test_attachment_blob_copied(migrated):
    dest, _, _ = migrated
    tx = FolderTransport(dest)
    assert tx.get_blob("chats/qa-room-abc123/files/notes.txt") == b"attachment payload"
