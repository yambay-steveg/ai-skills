"""cardctl test suite.

Covers the pure logic and the file-touching commands against temp dirs / fixtures —
never the real vaults or ~/.claude/projects. Module-level globals (CARDS_DIRS, PROJECTS)
are monkeypatched per test.
"""
import json
import uuid
from pathlib import Path

import pytest

from conftest import NS


# ── helpers ─────────────────────────────────────────────────────────────────
def make_card(cards_dir, slug, *, status="in-progress", paths=(), session=None,
              title="A card", extra_body=""):
    cards_dir.mkdir(parents=True, exist_ok=True)
    fm = [f"type: project", f"title: {title}", f"status: {status}"]
    if session:
        fm.append(f"sessionId: {session}")
    fm.append("paths:")
    fm += [f"  - {p}" for p in paths] or ["  - "]
    body = f"\n{extra_body}\n## Sessions\n\n"
    p = cards_dir / f"{slug}.md"
    p.write_text("---\n" + "\n".join(fm) + "\n---\n" + body)
    return p


def fake_transcript(projects, cwd, sid=None, cwd_in_record=True):
    """Create a JSONL transcript under PROJECTS/encode(cwd)/<sid>.jsonl."""
    sid = sid or str(uuid.uuid4())
    proj = projects / cwd.replace("/", "-")
    proj.mkdir(parents=True, exist_ok=True)
    rec = {"type": "user", "cwd": cwd if cwd_in_record else None,
           "message": {"content": "hello there"}}
    (proj / f"{sid}.jsonl").write_text(json.dumps(rec) + "\n")
    return sid


# ── parse_fm ──────────────────────────────────────────────────────────────────
def test_parse_fm_scalars_inline_and_block_lists(cc):
    fm = cc.parse_fm(
        'type: project\n'
        'title: Hello world\n'
        'tags: [area/tools, kind/x]\n'
        '# a comment line\n'
        'paths:\n'
        '  - /a/b\n'
        '  - /c/d\n'
    )
    assert fm["type"] == "project"
    assert fm["title"] == "Hello world"
    assert fm["tags"] == ["area/tools", "kind/x"]
    assert fm["paths"] == ["/a/b", "/c/d"]


def test_parse_fm_empty_block_list_is_list(cc):
    fm = cc.parse_fm("paths:\n")
    assert fm["paths"] == []


# ── ensure_primary_folder ──────────────────────────────────────────────────────
def test_ensure_primary_folder_creates_when_parent_exists(cc, tmp_path):
    new = tmp_path / "act"
    cc.ensure_primary_folder({"title": "T", "paths": [str(new)]})
    assert new.is_dir()
    assert "Activity folder" in (new / "README.md").read_text()


def test_ensure_primary_folder_skips_when_parent_missing(cc, tmp_path):
    new = tmp_path / "missing" / "act"  # parent doesn't exist → don't fabricate deep
    cc.ensure_primary_folder({"title": "T", "paths": [str(new)]})
    assert not new.exists()


def test_ensure_primary_folder_noop_without_paths(cc):
    cc.ensure_primary_folder({"title": "T"})  # must not raise


# ── find_card_for / which (+ cache) ─────────────────────────────────────────────
def test_find_card_for_scans_cards_dirs(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    assert cc.find_card_for(str(folder)) == card


def test_find_card_for_matches_subfolder(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    folder = tmp_path / "active" / "x"
    (folder / "sub").mkdir(parents=True)
    make_card(cards, "x-card", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    assert cc.find_card_for(str(folder / "sub")) is not None


def test_cache_dotfile_roundtrip_and_stale_validation(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})

    cc.write_card_cache(str(folder), str(card))
    dot = folder / ".card"
    assert dot.read_text().strip() == str(card)
    assert not (folder / "README.md").exists()   # never writes into notes
    # idempotent re-write
    cc.write_card_cache(str(folder), str(card))
    assert dot.read_text().strip() == str(card)
    # cache hit still resolves
    assert cc.find_card_for(str(folder)) == card

    # stale dotfile (card no longer references the folder) → falls back to scan, ignores cache
    card.write_text(card.read_text().replace(str(folder), "/nowhere"))
    assert cc.find_card_for(str(folder)) is None


def test_write_card_cache_migrates_legacy_readme_marker(cc, tmp_path):
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    readme = folder / "README.md"
    readme.write_text("# Real spec\n<!-- card: /old/stale.md -->\n\nReal content stays.\n")
    cc.write_card_cache(str(folder), "/new/card.md")
    after = readme.read_text()
    assert "<!-- card:" not in after          # legacy marker stripped
    assert "# Real spec" in after and "Real content stays." in after
    assert (folder / ".card").read_text().strip() == "/new/card.md"


def test_find_card_for_none_when_no_match(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    assert cc.find_card_for(str(tmp_path / "whatever")) is None


# ── resolve_session (pin precedence) ────────────────────────────────────────────
def test_resolve_session_new_forced_beats_pin(cc):
    sid, mode = cc.resolve_session({"sessionId": "abc"}, NS(new=True, pick=False))
    assert sid is None and "new" in mode


def test_resolve_session_pin_used(cc):
    sid, mode = cc.resolve_session({"sessionId": "abc"}, NS(new=False, pick=False))
    assert sid == "abc" and mode == "pinned"


def test_resolve_session_latest_for_folder(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    sid = fake_transcript(projects, str(folder))
    res, mode = cc.resolve_session({"paths": [str(folder)]}, NS(new=False, pick=False))
    assert res == sid and mode == "latest for folder"


# ── link (pin + ## Sessions history + dedup) ────────────────────────────────────
def test_link_pins_and_logs(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    sid = fake_transcript(projects, str(folder))

    cc.cmd_link(NS(card=str(card), session=None, current=False, cwd=None, force=False))
    text = card.read_text()
    assert f"sessionId: {sid}" in text
    assert f"- `{sid}`" in text.split("## Sessions", 1)[1]


def test_link_repins_keeps_old_in_history_no_dup(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    old = fake_transcript(projects, str(folder))
    card = make_card(cards, "x-card", paths=[str(folder)], session=old)
    # log the old one first
    cc.cmd_link(NS(card=str(card), session=old, current=False, cwd=None, force=False))
    new = fake_transcript(projects, str(folder))
    cc.cmd_link(NS(card=str(card), session=new, current=False, cwd=None, force=False))

    text = card.read_text()
    assert f"sessionId: {new}" in text
    body = text.split("## Sessions", 1)[1]
    assert body.count(f"`{old}`") == 1  # old kept, not duplicated
    assert body.count(f"`{new}`") == 1


def test_link_explicit_session_id(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    card = make_card(cards, "x-card", paths=[str(tmp_path / "active" / "x")])
    cc.cmd_link(NS(card=str(card), session="dead-beef", current=False, cwd=None, force=False))
    assert "sessionId: dead-beef" in card.read_text()


# ── reconcile (dry-run; archived-only; shared-folder skip) ───────────────────────
def _active_folder(tmp_path, name="x"):
    f = tmp_path / "repo" / "active" / name
    f.mkdir(parents=True)
    return f


def test_reconcile_only_archived_is_filed(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    f_done = _active_folder(tmp_path, "done-one")
    f_arch = _active_folder(tmp_path, "arch-one")
    make_card(cards, "done", status="done", paths=[str(f_done)])
    make_card(cards, "arch", status="archived", paths=[str(f_arch)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})

    cc.cmd_reconcile(NS(apply=False))
    out = capsys.readouterr().out
    assert "arch-one" in out          # archived → planned
    assert "done-one" not in out      # done → left in place
    assert "dry run" in out
    assert f_arch.is_dir()            # nothing actually moved


def test_reconcile_skips_folder_shared_with_live_card(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    shared = _active_folder(tmp_path, "shared")
    make_card(cards, "arch", status="archived", paths=[str(shared)])
    make_card(cards, "live", status="in-progress", paths=[str(shared)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})

    cc.cmd_reconcile(NS(apply=False))
    out = capsys.readouterr().out
    assert "SKIP (shared with a live card)" in out


def test_reconcile_nothing_to_do(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    make_card(cards, "live", status="in-progress", paths=[str(_active_folder(tmp_path))])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    cc.cmd_reconcile(NS(apply=False))
    assert "nothing to do" in capsys.readouterr().out


# ── deploy: merge helpers (pure) ────────────────────────────────────────────────
def test_merge_list_by_key_replaces_and_appends_preserving_others(cc):
    existing = [{"id": "a", "v": 1}, {"id": "keep", "v": 9}, {"id": "b", "v": 1}]
    ours = [{"id": "a", "v": 2}, {"id": "c", "v": 3}]
    merged, changed = cc.merge_list_by_key(existing, ours)
    assert changed
    by = {x["id"]: x["v"] for x in merged}
    assert by == {"a": 2, "keep": 9, "b": 1, "c": 3}
    # 'keep' (not ours) stays in its original position
    assert [x["id"] for x in merged][:3] == ["a", "keep", "b"]


def test_merge_list_by_key_idempotent(cc):
    existing = [{"id": "a", "v": 1}]
    merged, changed = cc.merge_list_by_key(existing, [{"id": "a", "v": 1}])
    assert not changed and merged == existing


def test_merge_templater_preserves_other_keys(cc):
    existing = {"templates_folder": "Tpl", "some_other": True,
                "folder_templates": [{"folder": "Other", "template": "Other/x.md"}]}
    frag = {"templates_folder": "Templates", "trigger_on_file_creation": True,
            "enable_folder_templates": True,
            "folder_templates": [{"folder": "Cards", "template": "Templates/card.md"}]}
    merged, changed = cc.merge_templater(existing, frag)
    assert changed
    assert merged["some_other"] is True                 # untouched
    assert merged["templates_folder"] == "Tpl"          # existing kept, not clobbered
    folders = {e["folder"] for e in merged["folder_templates"]}
    assert folders == {"Other", "Cards"}                # ours merged alongside


# ── deploy: surface application against a temp vault ─────────────────────────────
def test_deploy_copy_surface_creates_then_idempotent(cc, tmp_path, monkeypatch):
    # point DEPLOY_SRC at the real canonical sources
    src = Path(cc.__file__).resolve().parent / "deploy"
    monkeypatch.setattr(cc, "DEPLOY_SRC", src)
    vault = tmp_path / "vault"
    assert cc._deploy_surface(vault, "Cards/board.base", "copy", "Cards/board.base", apply=True) == "create"
    assert (vault / "Cards/board.base").is_file()
    assert cc._deploy_surface(vault, "Cards/board.base", "copy", "Cards/board.base", apply=True) == "unchanged"


def test_deploy_merge_preserves_existing_plugin_settings(cc, tmp_path, monkeypatch):
    src = Path(cc.__file__).resolve().parent / "deploy"
    monkeypatch.setattr(cc, "DEPLOY_SRC", src)
    vault = tmp_path / "vault"
    dest_rel = ".obsidian/plugins/obsidian-shellcommands/data.json"
    dst = vault / dest_rel
    dst.parent.mkdir(parents=True)
    # a pre-existing file with a foreign setting + an unrelated shell command
    dst.write_text(json.dumps({
        "settings_version": "9.9.9",
        "shell_commands": [{"id": "foreign", "alias": "keep me"}],
    }))
    action = cc._deploy_surface(vault, dest_rel, "array:shell_commands",
                                "fragments/shellcommands.commands.json", apply=True)
    assert action == "update"
    after = json.loads(dst.read_text())
    assert after["settings_version"] == "9.9.9"           # foreign key preserved
    ids = {c["id"] for c in after["shell_commands"]}
    assert "foreign" in ids and "mnosc79dtm" in ids       # our cmd merged, theirs kept


def test_deploy_dry_run_writes_nothing(cc, tmp_path, monkeypatch):
    src = Path(cc.__file__).resolve().parent / "deploy"
    monkeypatch.setattr(cc, "DEPLOY_SRC", src)
    vault = tmp_path / "vault"
    cc._deploy_surface(vault, "Cards/board.base", "copy", "Cards/board.base", apply=False)
    assert not (vault / "Cards/board.base").exists()


# ── set-status ──────────────────────────────────────────────────────────────
def test_set_status_in_text_is_surgical(cc):
    doc = ("---\ntype: project\ntitle: T\nstatus: in-progress\n"
           "summary: a card\n---\nbody\n\n---\n\nmore\n")
    out = cc.set_status_in_text(doc, "done")
    assert out == doc.replace("status: in-progress", "status: done")  # only that line


def test_set_status_in_text_inserts_when_absent(cc):
    doc = "---\ntitle: T\n---\nbody\n"
    assert cc.set_status_in_text(doc, "done") == "---\ntitle: T\nstatus: done\n---\nbody\n"


def test_set_status_writes_card_within_cards_dir(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "demo", status="in-progress")
    cc.cmd_set_status(NS(card=str(card), status="done"))
    assert "status: done\n" in card.read_text()
    assert "status: in-progress" not in card.read_text()


def test_set_status_rejects_unknown_status(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "demo", status="backlog")
    with pytest.raises(SystemExit):
        cc.cmd_set_status(NS(card=str(card), status="blocked"))
    assert card.read_text().count("status: backlog") == 1  # untouched


def test_set_status_refuses_card_outside_cards_dirs(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    outside = tmp_path / "loose.md"
    outside.write_text("---\ntitle: T\nstatus: backlog\n---\nbody\n")
    with pytest.raises(SystemExit):
        cc.cmd_set_status(NS(card=str(outside), status="done"))
    assert "status: backlog" in outside.read_text()  # untouched


def test_set_status_noop_when_already_set(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "demo", status="done")
    before = card.read_text()
    cc.cmd_set_status(NS(card=str(card), status="done"))
    assert card.read_text() == before
    assert "already done" in capsys.readouterr().out
