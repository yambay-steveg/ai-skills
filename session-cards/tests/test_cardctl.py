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


# ── wikilink / scalar helpers ─────────────────────────────────────────────────
def test_unwrap_wikilink_target_and_alias(cc):
    assert cc.unwrap_wikilink("[[Work Ops]]") == "Work Ops"
    assert cc.unwrap_wikilink("[[Work Ops|Ops]]") == "Work Ops"
    assert cc.unwrap_wikilink('"[[Work Ops|Ops]]"') == "Work Ops"   # unquoted first
    assert cc.unwrap_wikilink("plain") == "plain"
    assert cc.unwrap_wikilink("") == ""


def test_area_of_first_area_tag(cc):
    assert cc.area_of(["kind/x", "area/tools", "area/v7"]) == "tools"
    assert cc.area_of(["kind/x"]) == ""
    assert cc.area_of([]) == ""


# ── list (--json) ─────────────────────────────────────────────────────────────
def _full_card(cards_dir, slug, **fm_extra):
    """A card with the full board field set for list --json assertions."""
    cards_dir.mkdir(parents=True, exist_ok=True)
    fm = ["type: project", "title: My Card", "status: in-progress",
          'summary: "One liner"', 'latest: "Did a thing"',
          "tags: [area/tools, kind/x]",
          'program: "[[Work Ops|Ops]]"', 'project: "[[Big Project]]"',
          "sessionId: abc-123", "paths:", "  - /a/b", "  - /c/d"]
    p = cards_dir / f"{slug}.md"
    p.write_text("---\n" + "\n".join(fm) + "\n---\nbody\n\n## Sessions\n\n")
    return p


def test_list_json_shape_and_fields(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = _full_card(cards, "my-card")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    cc.cmd_list(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list) and len(out) == 1
    c = out[0]
    assert c["filePath"] == str(card.resolve())
    assert c["fileName"] == "my-card"
    assert c["title"] == "My Card"
    assert c["status"] == "in-progress"
    assert c["summary"] == "One liner"          # surrounding quotes stripped
    assert c["latest"] == "Did a thing"
    assert c["tags"] == ["area/tools", "kind/x"]
    assert c["program"] == "Work Ops"           # wikilink unwrapped (alias dropped)
    assert c["project"] == "Big Project"
    assert c["sessionId"] == "abc-123"
    assert c["paths"] == ["/a/b", "/c/d"]
    assert c["area"] == "tools"                 # first area/ tag's slug
    assert c["source"] == "work"
    assert c["archivedAt"] == ""                # not archived → empty


def test_list_json_multiple_dirs_and_source(cc, tmp_path, monkeypatch, capsys):
    work = tmp_path / "work" / "Cards"
    personal = tmp_path / "personal" / "Cards"
    make_card(work, "w1")
    make_card(personal, "p1")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": work, "personal": personal})
    cc.cmd_list(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    by_src = {c["fileName"]: c["source"] for c in out}
    assert by_src == {"w1": "work", "p1": "personal"}


def test_list_json_minimal_card_defaults(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    make_card(cards, "bare", title="Bare")  # no summary/program/tags
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    cc.cmd_list(NS(json=True))
    c = json.loads(capsys.readouterr().out)[0]
    assert c["title"] == "Bare"
    assert c["program"] == "" and c["project"] == "" and c["summary"] == ""
    assert c["tags"] == [] and c["area"] == ""


def test_list_human_listing(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    make_card(cards, "c1", title="Card One", status="backlog")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    cc.cmd_list(NS(json=False))
    assert "Card One — backlog" in capsys.readouterr().out


# ── lastActive ────────────────────────────────────────────────────────────────
def test_last_active_reflects_newest_transcript_under_path(cc, tmp_path, monkeypatch, capsys):
    import datetime
    import os
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    folder = (tmp_path / "active" / "x").resolve()
    folder.mkdir(parents=True)
    older = fake_transcript(projects, str(folder))
    newer = fake_transcript(projects, str(folder))
    # Pin the mtimes so the newest is unambiguous (and not "now").
    proj = projects / str(folder).replace("/", "-")
    os.utime(proj / f"{older}.jsonl", (1_000_000, 1_000_000))
    os.utime(proj / f"{newer}.jsonl", (2_000_000, 2_000_000))
    make_card(cards, "x-card", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_list(NS(json=True))
    c = json.loads(capsys.readouterr().out)[0]
    assert c["lastActive"] is not None
    # ISO-8601, timezone-aware, and the newest of the two transcripts.
    parsed = datetime.datetime.fromisoformat(c["lastActive"])
    assert parsed.tzinfo is not None
    assert parsed == datetime.datetime.fromtimestamp(2_000_000).astimezone()


def test_last_active_picks_up_pinned_session_transcript(cc, tmp_path, monkeypatch, capsys):
    import datetime
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    # Pinned session ran in some OTHER folder (not in the card's paths).
    elsewhere = (tmp_path / "elsewhere").resolve()
    sid = fake_transcript(projects, str(elsewhere))
    make_card(cards, "x-card", paths=[str((tmp_path / "active" / "x").resolve())], session=sid)
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_list(NS(json=True))
    c = json.loads(capsys.readouterr().out)[0]
    assert c["lastActive"] is not None
    assert datetime.datetime.fromisoformat(c["lastActive"]).tzinfo is not None


def test_last_active_null_when_no_sessions(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    make_card(cards, "x-card", paths=[str((tmp_path / "active" / "x").resolve())])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_list(NS(json=True))
    c = json.loads(capsys.readouterr().out)[0]
    assert c["lastActive"] is None


# ── archivedAt in list --json ──────────────────────────────────────────────────
def test_list_json_emits_archived_at(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    make_card(cards, "filed", status="archived",
              extra_body="")  # body unused here
    card = cards / "filed.md"
    card.write_text(card.read_text().replace(
        "status: archived\n",
        "status: archived\narchivedAt: 2026-06-30T09:20:14.123456+08:00\n"))
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    cc.cmd_list(NS(json=True))
    c = json.loads(capsys.readouterr().out)[0]
    assert c["archivedAt"] == "2026-06-30T09:20:14.123456+08:00"


# ── set_fm_field (generic surgical editor) ──────────────────────────────────────
def test_set_fm_field_inserts_when_absent(cc):
    doc = "---\ntitle: T\nstatus: archived\n---\nbody\n"
    out = cc.set_fm_field(doc, "archivedAt", "2026-06-30T09:20:14+08:00")
    assert "archivedAt: 2026-06-30T09:20:14+08:00\n" in out
    assert out.endswith("---\nbody\n")


def test_set_fm_field_removes_when_value_none(cc):
    doc = "---\ntitle: T\narchivedAt: 2026-06-30T09:20:14+08:00\nstatus: archived\n---\nb\n"
    out = cc.set_fm_field(doc, "archivedAt", None)
    assert "archivedAt:" not in out
    assert "title: T" in out and "status: archived" in out


# ── archive / reinstate / delete (real git repo) ─────────────────────────────────
def _git(repo, *argv):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *argv],
                          capture_output=True, text=True, check=True)


def _git_repo_with_folder(tmp_path, rel, name="x"):
    """Init a git repo at tmp_path/repo with a tracked folder <rel>/<name>/ (one file
    inside, since git doesn't track empty dirs), committed. Returns the folder path."""
    import subprocess
    repo = tmp_path / "repo"
    folder = repo / rel / name
    folder.mkdir(parents=True)
    (folder / "README.md").write_text(f"# {name}\nwork\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo, folder


def test_archive_stamps_files_and_relocates(cc, tmp_path, monkeypatch, capsys):
    import datetime
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    repo, folder = _git_repo_with_folder(tmp_path, "active", "thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="in-progress", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    sid = fake_transcript(projects, str(folder))

    cc.cmd_archive(NS(card=str(card), json=True))
    out = json.loads(capsys.readouterr().out)

    prefix = datetime.date.today().strftime("%Y-%m-")
    target = repo / "archive" / f"{prefix}thing"
    assert out["ok"] and out["status"] == "archived"
    assert out["archivedAt"]
    assert out["moved"][0]["to"] == str(target)
    assert out["moved"][0]["transcripts"] == 1
    # disk: folder moved, original gone
    assert target.is_dir() and not folder.exists()
    # frontmatter: status + archivedAt + path updated
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "archived"
    assert fm["archivedAt"]
    assert fm["paths"][0] == str(target)
    # transcripts relocated to the new cwd
    assert (projects / str(target).replace("/", "-") / f"{sid}.jsonl").is_file()
    assert not (projects / str(folder).replace("/", "-")).exists()


def test_archive_pattern_b_skips_shared_folder(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, folder = _git_repo_with_folder(tmp_path, "active", "shared")
    cards = tmp_path / "Cards"
    card = make_card(cards, "arch", status="in-progress", paths=[str(folder)])
    make_card(cards, "live", status="in-progress", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_archive(NS(card=str(card), json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == [str(folder)]
    assert out["moved"] == []
    assert folder.is_dir()                       # not moved — still live elsewhere
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "archived" and fm["archivedAt"]   # status + stamp still set


def test_reinstate_reverses_move_and_clears_stamp(cc, tmp_path, monkeypatch, capsys):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    card.write_text(card.read_text().replace(
        "status: archived\n", "status: archived\narchivedAt: 2026-06-30T09:20:14+08:00\n"))
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    sid = fake_transcript(projects, str(arch_folder))

    cc.cmd_reinstate(NS(card=str(card), json=True))
    out = json.loads(capsys.readouterr().out)

    active = repo / "active" / "thing"           # date prefix stripped
    assert out["ok"] and out["status"] == "in-progress"
    assert out["moved"][0]["to"] == str(active)
    assert active.is_dir() and not arch_folder.exists()
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "in-progress"
    assert "archivedAt" not in fm                # cleared
    assert fm["paths"][0] == str(active)
    assert (projects / str(active).replace("/", "-") / f"{sid}.jsonl").is_file()


def test_reinstate_refuses_non_archived(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    card = make_card(cards, "live", status="in-progress",
                     paths=[str(tmp_path / "active" / "x")])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    with pytest.raises(SystemExit):
        cc.cmd_reinstate(NS(card=str(card), json=False))


def test_reinstate_refuses_when_active_dest_exists(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    (repo / "active" / "thing").mkdir(parents=True)   # would clobber
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    with pytest.raises(SystemExit):
        cc.cmd_reinstate(NS(card=str(card), json=False))
    assert arch_folder.is_dir()                   # nothing moved


def test_delete_removes_folder_and_card_with_confirm(cc, tmp_path, monkeypatch, capsys):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    fake_transcript(projects, str(arch_folder))

    cc.cmd_delete(NS(card=str(card), confirm="thing", json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["deleted"] == [str(arch_folder)]
    assert not arch_folder.exists()              # folder gone
    assert not card.exists()                     # card note gone
    assert not (projects / str(arch_folder).replace("/", "-")).exists()  # transcripts gone


def test_delete_refuses_wrong_confirm(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    with pytest.raises(SystemExit):
        cc.cmd_delete(NS(card=str(card), confirm="wrong", json=False))
    assert card.exists() and arch_folder.is_dir()  # nothing removed


def test_delete_refuses_non_archived(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    card = make_card(cards, "live", status="in-progress")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    with pytest.raises(SystemExit):
        cc.cmd_delete(NS(card=str(card), confirm="live", json=False))
    assert card.exists()


# ── build_workspace: window.title injection ───────────────────────────────────
def test_build_workspace_injects_window_title(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CACHE", tmp_path / "cache")
    folder = tmp_path / "act"
    folder.mkdir()
    card = make_card(tmp_path / "Cards", "demo", title="My Card", paths=[str(folder)])
    ws, folders = cc.build_workspace(str(card), {"title": "My Card", "paths": [str(folder)]}, None)
    settings = json.loads(ws.read_text())["settings"]
    assert settings["window.title"] == "My Card — ${rootName}"
    assert "claudeCode.allowDangerouslySkipPermissions" not in settings


def test_build_workspace_dangerous_preserves_window_title(cc, tmp_path, monkeypatch):
    folder = tmp_path / "act"
    folder.mkdir()
    card = make_card(tmp_path / "Cards", "demo", title="My Card", paths=[str(folder)])
    monkeypatch.setattr(cc, "CACHE", tmp_path / "cache")
    ws, _ = cc.build_workspace(str(card), {"title": "My Card", "paths": [str(folder)]},
                               None, dangerous=True)
    settings = json.loads(ws.read_text())["settings"]
    assert settings["window.title"] == "My Card — ${rootName}"
    assert settings["claudeCode.allowDangerouslySkipPermissions"] is True
    assert settings["claudeCode.initialPermissionMode"] == "bypassPermissions"


# ── focus (osascript mocked; no real windows) ─────────────────────────────────
def test_focus_builds_osascript_with_card_title(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "demo", title="My Special Card")
    calls = {}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        if argv[0] == cc.HS:           # no Hammerspoon window matches → fall back
            R.stdout = "[]"
            return R()
        calls["argv"] = argv           # the AppleScript (osascript) call
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.cmd_focus(NS(card=str(card)))
    assert calls["argv"][0] == cc.OSASCRIPT
    assert calls["argv"][1] == "-e"
    assert "My Special Card" in calls["argv"][2]          # title embedded in script
    assert 'process "Code"' in calls["argv"][2]
    assert "AXRaise" in calls["argv"][2]
    assert "focused" in capsys.readouterr().out


def test_focus_failure_is_reported_not_raised(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "demo", title="My Card")

    def fake_run(argv, **kw):
        class R:
            stdout = ""
        if argv[0] == cc.HS:           # Hammerspoon enumerates no matching window
            R.returncode = 0
            R.stderr = ""
            R.stdout = "[]"
            return R()
        R.returncode = 1               # AppleScript fallback fails (no Accessibility)
        R.stderr = "not authorized to send Apple events"
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.cmd_focus(NS(card=str(card)))  # must not raise
    err = capsys.readouterr().err
    assert "could not raise the window" in err
    assert "Accessibility" in err


# ── slug_from_window_title (pure) ──────────────────────────────────────────────
def test_slug_from_window_title_basic(cc):
    assert cc.slug_from_window_title(
        "Session card board (Phase 2) — session-card-board (Workspace)"
    ) == "session-card-board"


def test_slug_from_window_title_multi_emdash_takes_last(cc):
    # Card title itself contains " — " → the slug is after the LAST separator.
    assert cc.slug_from_window_title(
        "Axon whitepaper — sign-off — axon-whitepaper-signoff (Workspace)"
    ) == "axon-whitepaper-signoff"


def test_slug_from_window_title_modified_suffix(cc):
    assert cc.slug_from_window_title(
        "Foo — determine-card-hiearchy (Workspace) — Modified"
    ) == "determine-card-hiearchy"
    # …and without the (Workspace) segment too.
    assert cc.slug_from_window_title(
        "Foo — determine-card-hiearchy — Modified"
    ) == "determine-card-hiearchy"


def test_slug_from_window_title_none_without_separator(cc):
    assert cc.slug_from_window_title("manually-opened-folder") is None
    assert cc.slug_from_window_title("") is None


# ── hs_code_windows / windows (hs subprocess mocked) ────────────────────────────
def _fake_hs(monkeypatch, cc, *, stdout="", stderr="", returncode=0, raises=None):
    """Monkeypatch subprocess.run as `hs` would behave (no real Hammerspoon)."""
    def fake_run(argv, **kw):
        assert argv[0] == cc.HS and argv[1] == "-c"
        if raises is not None:
            raise raises
        class R:
            pass
        R.stdout, R.stderr, R.returncode = stdout, stderr, returncode
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)


def test_hs_code_windows_parses_json(cc, monkeypatch):
    _fake_hs(monkeypatch, cc,
             stdout='[{"id":19146,"title":"X — session-card-board (Workspace)"}]')
    wins = cc.hs_code_windows()
    assert wins == [{"id": 19146, "title": "X — session-card-board (Workspace)"}]


def test_run_hs_closes_stdin(cc, monkeypatch):
    # `hs` blocks on an open stdin pipe when spawned non-interactively (board → cardctl
    # → hs), so _run_hs must pass stdin=DEVNULL or it times out.
    captured = {}

    def fake_run(argv, **kw):
        captured.update(kw)

        class R:
            stdout, stderr, returncode = "[]", "", 0

        return R()

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc._run_hs('return "x"')
    assert captured.get("stdin") == cc.subprocess.DEVNULL


def test_hs_code_windows_strips_hammerspoon_preamble(cc, monkeypatch):
    # Hammerspoon prepends a "-- Loading extension: json" line the first time
    # hs.json lazy-loads; the JSON must still parse.
    _fake_hs(monkeypatch, cc,
             stdout='-- Loading extension: json\n[{"id":21465,"title":"Determine Card Hiearchy — determine-card-hiearchy (Workspace)"}]')
    wins = cc.hs_code_windows()
    assert wins == [{"id": 21465, "title": "Determine Card Hiearchy — determine-card-hiearchy (Workspace)"}]


def test_hs_code_windows_raises_when_port_unreachable(cc, monkeypatch):
    _fake_hs(monkeypatch, cc, stderr="hs: can't access … message port")
    with pytest.raises(cc.HsUnavailable):
        cc.hs_code_windows()


def test_hs_code_windows_raises_on_missing_binary(cc, monkeypatch):
    _fake_hs(monkeypatch, cc, raises=FileNotFoundError())
    with pytest.raises(cc.HsUnavailable):
        cc.hs_code_windows()


def test_windows_json_maps_matched_and_unmatched(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    matched = make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    _fake_hs(monkeypatch, cc, stdout=json.dumps([
        {"id": 19146, "title": "Board — session-card-board (Workspace)"},
        {"id": 222, "title": "no-card-here — unknown-slug (Workspace)"},
        {"id": 333, "title": "a manually opened folder"},   # no separator → slug None
    ]))
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    w = {r["id"]: r for r in out["windows"]}
    assert w[19146]["slug"] == "session-card-board"
    assert w[19146]["filePath"] == str(matched.resolve())
    assert w[222]["slug"] == "unknown-slug" and w[222]["filePath"] is None
    assert w[333]["slug"] is None and w[333]["filePath"] is None


def test_windows_json_engine_unavailable_is_available_false(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": tmp_path / "Cards"})
    _fake_hs(monkeypatch, cc, stderr="hs: can't access … message port")
    cc.cmd_windows(NS(json=True))  # must exit 0 (return), not raise
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is False
    assert out["windows"] == []
    assert out["error"]


# ── focus: id-upgrade with AppleScript fallback (subprocess mocked) ─────────────
def test_focus_by_id_when_window_matches(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        class R:
            returncode = 0
            stderr = ""
        # First call: enumerate windows. Second: focus by id.
        if "allWindows" in argv[2]:
            R.stdout = json.dumps([{"id": 19146,
                                    "title": "Board — session-card-board (Workspace)"}])
        else:
            assert "hs.window.get(19146)" in argv[2]   # focuses the matched id
            R.stdout = "ok"
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.cmd_focus(NS(card=str(card)))
    out = capsys.readouterr().out
    assert "by id" in out
    # Never reached osascript (AppleScript) — both calls were to hs.
    assert all(argv[0] == cc.HS for argv in calls)


def test_focus_falls_back_to_applescript_when_no_window_matches(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    seen = {"osascript": False}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        if argv[0] == cc.HS:
            R.stdout = json.dumps([{"id": 1, "title": "Other — other-slug (Workspace)"}])
        elif argv[0] == cc.OSASCRIPT:
            seen["osascript"] = True
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.cmd_focus(NS(card=str(card)))
    assert seen["osascript"] is True               # fell back to AXRaise-by-title
    assert "focused" in capsys.readouterr().out


def test_focus_falls_back_to_applescript_when_hs_unavailable(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    seen = {"osascript": False}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        if argv[0] == cc.HS:
            R.stderr = "hs: can't access … message port"   # engine unavailable
        elif argv[0] == cc.OSASCRIPT:
            seen["osascript"] = True
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    cc.cmd_focus(NS(card=str(card)))
    assert seen["osascript"] is True               # AppleScript fallback used
    assert "focused" in capsys.readouterr().out


# ── new (auto activity folder) ─────────────────────────────────────────────────
def _new_ns(slug, **kw):
    """NS for cmd_new with every field defaulted (mirrors the argparser)."""
    base = dict(slug=slug, title="A title", summary=None, latest=None, path=None,
                session=None, jira=None, area=None, program=None,
                status="in-progress", type="project", domain="work",
                make_folder=False, no_folder=False, force=False)
    base.update(kw)
    return NS(**base)


def _wire_new(cc, tmp_path, monkeypatch):
    """Point CARDS_DIRS + ACTIVE_ROOTS at temp dirs; return (cards, active)."""
    cards = tmp_path / "vault" / "Cards"
    active = tmp_path / "repo" / "active"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards, "personal": tmp_path / "p" / "Cards"})
    monkeypatch.setattr(cc, "ACTIVE_ROOTS", {"work": active, "personal": tmp_path / "p" / "active"})
    return cards, active


def test_new_default_creates_activity_folder_as_primary(cc, tmp_path, monkeypatch, capsys):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("my-thing", title="My Thing"))
    card = cards / "my-thing.md"
    fm, _ = cc.read_card(str(card))
    activity = active / "my-thing"
    assert fm["paths"][0] == str(activity)          # activity folder is primary
    assert activity.is_dir()                        # …and it was created
    assert (activity / "README.md").is_file()       # with a stub README
    assert "created activity folder" in capsys.readouterr().out


def test_new_path_entries_appended_after_activity_and_not_created(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    existing = tmp_path / "monorepo"
    existing.mkdir()
    missing = tmp_path / "nope"
    cc.cmd_new(_new_ns("linker", path=[str(existing), str(missing)]))
    fm, _ = cc.read_card(str(cards / "linker.md"))
    assert fm["paths"] == [str(active / "linker"), str(existing), str(missing)]
    assert (active / "linker").is_dir()             # activity folder created
    assert not missing.exists()                     # --path entries are never created


def test_new_no_folder_skips_auto_activity_folder(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    existing = tmp_path / "repo-only"
    existing.mkdir()
    cc.cmd_new(_new_ns("pointer", no_folder=True, path=[str(existing)]))
    fm, _ = cc.read_card(str(cards / "pointer.md"))
    assert fm["paths"] == [str(existing)]
    assert not (active / "pointer").exists()        # no auto activity folder


def test_new_no_folder_no_path_yields_empty_paths(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("empty", no_folder=True))
    fm, _ = cc.read_card(str(cards / "empty.md"))
    assert fm.get("paths") == []                    # explicit opt-out → allowed empty
    assert not (active / "empty").exists()


def test_new_domain_selects_active_root(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    p_active = tmp_path / "p" / "active"
    cc.cmd_new(_new_ns("pcard", domain="personal"))
    fm, _ = cc.read_card(str(tmp_path / "p" / "Cards" / "pcard.md"))
    assert fm["paths"][0] == str(p_active / "pcard")
    assert (p_active / "pcard").is_dir()


# ── set: the metadata writer ────────────────────────────────────────────────────
def _set_ns(card, **kw):
    base = dict(card=card, area=None, add_area=None, program=None,
                raised_at=None, add_tag=None, remove_tag=None,
                add_path=None, remove_path=None, customer=None)
    base.update(kw)
    return NS(**base)


def test_set_tags_block_form_preserved(cc):
    block = "---\ntype: project\ntags:\n  - area/work-ops\n  - type/reference\n---\nbody\n"
    out = cc.set_tags_in_text(block, ["area/v7", "type/reference", "kind/geo"])
    assert "tags:\n  - area/v7\n  - type/reference\n  - kind/geo\n" in out
    assert out.startswith("---\ntype: project\n")


def test_set_tags_inline_form_preserved(cc):
    inline = "---\ntitle: X\ntags: [area/work-ops]\n---\nbody\n"
    out = cc.set_tags_in_text(inline, ["area/work-ops", "kind/foo"])
    assert "tags: [area/work-ops, kind/foo]\n" in out


def test_set_tags_inserts_when_absent(cc):
    none = "---\ntitle: X\nstatus: backlog\n---\nbody\n"
    out = cc.set_tags_in_text(none, ["area/work-ops"])
    assert "tags: [area/work-ops]\n" in out
    assert out.count("---") == 2


def test_cmd_set_area_replaces_and_adds_program(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c", extra_body="")
    # seed an area tag to be replaced
    card.write_text(card.read_text().replace("status: in-progress",
                                             "status: in-progress\ntags: [area/docs]"))
    cc.cmd_set(_set_ns(str(card), area="area/v7", program="managing-ai-activities"))
    fm, _ = cc.read_card(str(card))
    assert "area/v7" in fm["tags"] and "area/docs" not in fm["tags"]
    assert cc.unwrap_wikilink(fm["program"]) == "managing-ai-activities"


def test_cmd_set_roundtrip_add_then_remove_is_identical(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    card.write_text(card.read_text().replace("status: in-progress",
                                             "status: in-progress\ntags: [area/work-ops]"))
    before = card.read_text()
    cc.cmd_set(_set_ns(str(card), add_tag=["kind/test"]))
    cc.cmd_set(_set_ns(str(card), remove_tag=["kind/test"]))
    assert card.read_text() == before


def test_cmd_set_refuses_outside_cards_dir(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    stray = tmp_path / "stray.md"
    stray.write_text("---\ntitle: X\n---\n")
    with pytest.raises(SystemExit):
        cc.cmd_set(_set_ns(str(stray), add_tag=["kind/x"]))


# ── set: paths axis (#14, --add-path / --remove-path) ────────────────────────────
def test_set_paths_in_text_replaces_block(cc):
    doc = "---\ntitle: X\npaths:\n  - /a/b\n  - /c/d\n---\nbody\n"
    out = cc.set_paths_in_text(doc, ["/a/b", "/c/d", "/e/f"])
    assert "paths:\n  - /a/b\n  - /c/d\n  - /e/f\n" in out
    assert out.endswith("---\nbody\n")


def test_set_paths_in_text_inserts_when_absent(cc):
    doc = "---\ntitle: X\nstatus: backlog\n---\nbody\n"
    out = cc.set_paths_in_text(doc, ["/a/b"])
    assert "paths:\n  - /a/b\n" in out
    assert out.count("---") == 2


def test_cmd_set_add_path_appends_after_primary(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    extra = (tmp_path / "vault").resolve()
    prim.mkdir(parents=True)
    extra.mkdir()
    card = make_card(cards, "c", paths=[str(prim)])
    cc.cmd_set(_set_ns(str(card), add_path=[str(extra)]))
    fm, _ = cc.read_card(str(card))
    assert fm["paths"] == [str(prim), str(extra)]   # primary preserved, append after


def test_cmd_set_add_path_idempotent(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    prim.mkdir(parents=True)
    card = make_card(cards, "c", paths=[str(prim)])
    before = card.read_text()
    cc.cmd_set(_set_ns(str(card), add_path=[str(prim)]))   # already present
    assert card.read_text() == before                       # no change


def test_cmd_set_add_path_warns_when_missing(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    prim.mkdir(parents=True)
    card = make_card(cards, "c", paths=[str(prim)])
    missing = str((tmp_path / "nope").resolve())
    cc.cmd_set(_set_ns(str(card), add_path=[missing]))
    fm, _ = cc.read_card(str(card))
    assert missing in fm["paths"]                            # still added
    assert "does not exist yet" in capsys.readouterr().err   # but warned


def test_cmd_set_remove_path(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    extra = (tmp_path / "vault").resolve()
    card = make_card(cards, "c", paths=[str(prim), str(extra)])
    cc.cmd_set(_set_ns(str(card), remove_path=[str(extra)]))
    fm, _ = cc.read_card(str(card))
    assert fm["paths"] == [str(prim)]


def test_cmd_set_remove_last_path_refused(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    card = make_card(cards, "c", paths=[str(prim)])
    before = card.read_text()
    with pytest.raises(SystemExit):
        cc.cmd_set(_set_ns(str(card), remove_path=[str(prim)]))
    assert card.read_text() == before                        # untouched


def test_cmd_set_remove_path_not_on_card_warns(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    prim = (tmp_path / "active" / "x").resolve()
    card = make_card(cards, "c", paths=[str(prim)])
    before = card.read_text()
    cc.cmd_set(_set_ns(str(card), remove_path=[str((tmp_path / "other").resolve())]))
    assert card.read_text() == before                        # no change
    assert "not on card" in capsys.readouterr().err


# ── lint: drift detection ───────────────────────────────────────────────────────
def _lint_ns(card=None, **kw):
    return NS(card=card, json=True, **kw)


def _findings(cc, tmp_path, capsys):
    cc.cmd_lint(_lint_ns())
    return {(f["code"], f["card"]) for f in json.loads(capsys.readouterr().out)}


def test_lint_flags_no_area_and_clean_card(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    bad = make_card(cards, "noarea")  # no tags → NO-AREA
    good = make_card(cards, "ok")
    good.write_text(good.read_text().replace("status: in-progress",
                                             "status: in-progress\ntags: [area/work-ops]"))
    found = _findings(cc, tmp_path, capsys)
    assert ("NO-AREA", "noarea.md") in found
    assert ("NO-AREA", "ok.md") not in found


def test_lint_bad_status_and_link_in_prose(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    c = make_card(cards, "c", status="wip")
    c.write_text(c.read_text().replace("status: wip",
                 'status: wip\ntags: [area/work-ops]\nlatest: "see [[other]]"'))
    found = _findings(cc, tmp_path, capsys)
    assert ("BAD-STATUS", "c.md") in found
    assert ("LINK-IN-PROSE", "c.md") in found


def test_lint_dangling_link_and_basename_collision(cc, tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    cards = vault / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    # a real program note so a *resolvable* link doesn't dangle
    (vault / "Programs").mkdir(parents=True)
    (vault / "Programs" / "real-prog.md").write_text("# real\n")
    c = make_card(cards, "c")
    c.write_text(c.read_text().replace("status: in-progress",
                 'status: in-progress\ntags: [area/work-ops]\nprogram: "[[ghost-prog]]"'))
    # basename collision: a note sharing the card's stem elsewhere in the vault
    (vault / "dup.md").write_text("# dup\n")
    make_card(cards, "dup")
    found = _findings(cc, tmp_path, capsys)
    assert ("DANGLING-LINK", "c.md") in found
    assert any(code == "BASENAME-COLLISION" for code, _ in found)


def test_lint_standing_language_is_heuristic(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    c = make_card(cards, "c", title="The ongoing thing")
    c.write_text(c.read_text().replace("status: in-progress",
                                       "status: in-progress\ntags: [area/work-ops]"))
    cc.cmd_lint(_lint_ns())
    f = [x for x in json.loads(capsys.readouterr().out) if x["code"] == "STANDING-LANGUAGE"]
    assert f and f[0]["severity"] == "heuristic"


# ── customer edge (#13 Phase 1) ─────────────────────────────────────────────────
def test_cmd_set_customer_writes_link_property(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    cc.cmd_set(_set_ns(str(card), customer="sce"))
    fm, _ = cc.read_card(str(card))
    assert cc.unwrap_wikilink(fm["customer"]) == "sce"


def test_card_to_dict_customer_scalar_list_and_absent(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    c1 = make_card(cards, "one")
    c1.write_text(c1.read_text().replace("status: in-progress",
                  'status: in-progress\ncustomer: "[[sce]]"'))
    assert cc.card_to_dict(str(c1), "t")["customer"] == ["sce"]
    c2 = make_card(cards, "two")
    c2.write_text(c2.read_text().replace("status: in-progress",
                  'status: in-progress\ncustomer:\n  - "[[sce]]"\n  - "[[nged]]"'))
    assert cc.card_to_dict(str(c2), "t")["customer"] == ["sce", "nged"]
    c3 = make_card(cards, "three")
    assert cc.card_to_dict(str(c3), "t")["customer"] == []


def test_lint_dangling_customer(cc, tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    cards = vault / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    (vault / "Customers" / "sce").mkdir(parents=True)
    (vault / "Customers" / "sce" / "sce.md").write_text("# sce\n")
    c = make_card(cards, "c")
    c.write_text(c.read_text().replace("status: in-progress",
                 'status: in-progress\ntags: [area/work-ops]\ncustomer: "[[ghost]]"'))
    assert ("DANGLING-LINK", "c.md") in _findings(cc, tmp_path, capsys)
    c.write_text(c.read_text().replace('[[ghost]]', '[[sce]]'))
    assert ("DANGLING-LINK", "c.md") not in _findings(cc, tmp_path, capsys)
