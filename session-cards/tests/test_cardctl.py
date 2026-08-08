"""cardctl test suite.

Covers the pure logic and the file-touching commands against temp dirs / fixtures —
never the real vaults or ~/.claude/projects. Module-level globals (CARDS_DIRS, PROJECTS)
are monkeypatched per test.
"""
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest

from conftest import NS


# ── helpers ─────────────────────────────────────────────────────────────────
def make_card(cards_dir, slug, *, status="in-progress", paths=(), session=None,
              title="A card", extra_body=""):
    cards_dir.mkdir(parents=True, exist_ok=True)
    fm = ["type: project", f"title: {title}", f"status: {status}"]
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


# ── parse_fm / read_card hardening (#22) ──────────────────────────────────────
def test_parse_fm_inline_comment_after_inline_list(cc):
    fm = cc.parse_fm("tags: [area/tools] # note\n")
    assert fm["tags"] == ["area/tools"]  # list, not the scalar "[area/tools] # note"


def test_parse_fm_inline_comment_after_scalar(cc):
    fm = cc.parse_fm("status: done # finished\n")
    assert fm["status"] == "done"


def test_parse_fm_inline_comment_after_block_item(cc):
    fm = cc.parse_fm("paths:\n  - /x/y # keep\n")
    assert fm["paths"] == ["/x/y"]


def test_parse_fm_quoted_value_keeps_hash(cc):
    fm = cc.parse_fm('summary: "a # b"\n')
    assert fm["summary"] == '"a # b"'  # comment not clipped inside quotes


def test_parse_fm_quoted_value_trailing_comment_clipped(cc):
    fm = cc.parse_fm('summary: "a # b" # note\n')
    assert fm["summary"] == '"a # b"'


def test_parse_fm_bare_hash_value_untouched(cc):
    fm = cc.parse_fm("colour: #fff\n")
    assert fm["colour"] == "#fff"  # no whitespace before '#' → not a comment


def test_parse_fm_whole_line_comment_still_ignored(cc):
    fm = cc.parse_fm("# just a comment\nstatus: backlog\n")
    assert fm == {"status": "backlog"}


def test_read_card_dies_on_unterminated_frontmatter(cc, tmp_path, capsys):
    card = tmp_path / "broken.md"
    card.write_text("---\ntitle: T\nstatus: backlog\nbody without closing fence\n")
    with pytest.raises(SystemExit):
        cc.read_card(str(card))
    assert "unterminated frontmatter" in capsys.readouterr().err


def test_read_card_body_thematic_break_ok(cc, tmp_path):
    card = tmp_path / "ok.md"
    card.write_text("---\ntitle: T\nstatus: backlog\n---\nbody\n\n---\n\nmore body\n")
    fm, text = cc.read_card(str(card))
    assert fm["title"] == "T" and "more body" in text


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
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
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
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
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
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "x-card", paths=[str(tmp_path / "active" / "x")])
    cc.cmd_link(NS(card=str(card), session="dead-beef", current=False, cwd=None, force=False))
    assert "sessionId: dead-beef" in card.read_text()


def _set_mtime(projects, cwd, sid, when):
    os.utime(projects / cwd.replace("/", "-") / f"{sid}.jsonl", (when, when))


def test_link_current_scoped_to_card_paths_not_global_newest(cc, tmp_path, monkeypatch):
    """#30: a newer transcript in an unrelated project must not win --current —
    neither the pin nor the ## Sessions history line."""
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    other = tmp_path / "active" / "unrelated"
    other.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    mine = fake_transcript(projects, str(folder))
    stray = fake_transcript(projects, str(other))
    _set_mtime(projects, str(folder), mine, 1_000)
    _set_mtime(projects, str(other), stray, 2_000)   # globally newest, wrong card

    cc.cmd_link(NS(card=str(card), session=None, current=True, cwd=None, force=False))
    text = card.read_text()
    assert f"sessionId: {mine}" in text
    assert stray not in text                          # no pin AND no history line


def test_link_current_picks_newest_across_all_card_paths(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    primary = tmp_path / "active" / "x"
    worktree = tmp_path / "worktrees" / "x-slice"
    primary.mkdir(parents=True)
    worktree.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(primary), str(worktree)])
    older = fake_transcript(projects, str(primary))
    newer = fake_transcript(projects, str(worktree))
    _set_mtime(projects, str(primary), older, 1_000)
    _set_mtime(projects, str(worktree), newer, 2_000)

    cc.cmd_link(NS(card=str(card), session=None, current=True, cwd=None, force=False))
    assert f"sessionId: {newer}" in card.read_text()


def test_link_default_search_finds_a_session_in_a_non_primary_path(cc, tmp_path, monkeypatch):
    """The CLI default used to look only at `paths[0]`, so a card whose sessions all ran in
    a linked repo/worktree died with "no sessions found under <folder>" while the session
    sat one path along. It now scopes exactly like `--current`."""
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    primary = tmp_path / "active" / "x"          # no transcripts here at all
    worktree = tmp_path / "worktrees" / "x-slice"
    primary.mkdir(parents=True)
    worktree.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(primary), str(worktree)])
    sid = fake_transcript(projects, str(worktree))

    cc.cmd_link(NS(card=str(card), session=None, current=False, cwd=None, force=False))
    assert f"sessionId: {sid}" in card.read_text()


def test_link_default_search_picks_newest_across_paths(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    primary = tmp_path / "active" / "x"
    worktree = tmp_path / "worktrees" / "x-slice"
    primary.mkdir(parents=True)
    worktree.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(primary), str(worktree)])
    older = fake_transcript(projects, str(primary))
    newer = fake_transcript(projects, str(worktree))
    _set_mtime(projects, str(primary), older, 1_000)
    _set_mtime(projects, str(worktree), newer, 2_000)

    cc.cmd_link(NS(card=str(card), session=None, current=False, cwd=None, force=False))
    assert f"sessionId: {newer}" in card.read_text()


def test_link_default_search_dies_when_no_path_has_a_session(cc, tmp_path, monkeypatch, capsys):
    """The error path of the default search: folders exist but hold no transcripts. Salvaged
    from `cardctl-customer-edge` before deleting it — the `--current` equivalent was already
    covered, this one wasn't, and the message must name every folder looked in, not just the
    first, or it sends you hunting in the wrong place."""
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    primary = tmp_path / "active" / "x"
    worktree = tmp_path / "worktrees" / "x-slice"
    primary.mkdir(parents=True)
    worktree.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(primary), str(worktree)])  # no transcripts

    with pytest.raises(SystemExit):
        cc.cmd_link(NS(card=str(card), session=None, current=False, cwd=None, force=False))
    err = capsys.readouterr().err
    assert str(primary) in err and str(worktree) in err


def test_card_session_origins_shared_by_both_link_paths(cc, tmp_path):
    """The helper both branches use — `--cwd` wins, missing folders are dropped."""
    real = tmp_path / "real"
    real.mkdir()
    fm = {"paths": [str(real), str(tmp_path / "gone")]}
    assert cc.card_session_origins(fm) == [str(real)]
    assert cc.card_session_origins(fm, str(real)) == [str(real)]
    assert cc.card_session_origins(fm, str(tmp_path / "gone")) == []
    assert cc.card_session_origins({}) == []


def test_link_current_with_cwd_scopes_to_that_cwd(cc, tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    folder = tmp_path / "active" / "x"
    elsewhere = tmp_path / "active" / "y"
    folder.mkdir(parents=True)
    elsewhere.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    in_paths = fake_transcript(projects, str(folder))
    in_cwd = fake_transcript(projects, str(elsewhere))
    _set_mtime(projects, str(folder), in_paths, 2_000)    # newer, but out of scope
    _set_mtime(projects, str(elsewhere), in_cwd, 1_000)

    cc.cmd_link(NS(card=str(card), session=None, current=True,
                   cwd=str(elsewhere), force=False))
    assert f"sessionId: {in_cwd}" in card.read_text()


def test_link_current_dies_when_card_folder_has_no_transcripts(cc, tmp_path, monkeypatch, capsys):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    card = make_card(cards, "x-card", paths=[str(folder)])
    fake_transcript(projects, str(tmp_path / "active" / "unrelated-dir"))
    before = card.read_text()

    with pytest.raises(SystemExit):
        cc.cmd_link(NS(card=str(card), session=None, current=True, cwd=None, force=False))
    assert "no session transcripts under" in capsys.readouterr().err
    assert card.read_text() == before                 # untouched


def test_link_current_dies_when_card_has_no_folders(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "x-card", paths=[str(tmp_path / "does-not-exist")])

    with pytest.raises(SystemExit):
        cc.cmd_link(NS(card=str(card), session=None, current=True, cwd=None, force=False))
    assert "no folder to scope --current to" in capsys.readouterr().err


def test_link_refuses_markdown_outside_cards_dirs(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    loose = tmp_path / "loose.md"
    loose.write_text("---\ntitle: T\nstatus: backlog\n---\nbody\n")
    before = loose.read_text()
    with pytest.raises(SystemExit):
        cc.cmd_link(NS(card=str(loose), session="dead-beef", current=False, cwd=None, force=False))
    assert "not inside a configured Cards/ folder" in capsys.readouterr().err
    assert loose.read_text() == before  # untouched


def test_link_refuses_missing_card(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    with pytest.raises(SystemExit):
        cc.cmd_link(NS(card=str(tmp_path / "Cards" / "ghost.md"),
                       session="dead-beef", current=False, cwd=None, force=False))
    assert "no such card" in capsys.readouterr().err


# ── note (the "— what it did" writer; A3.2) ─────────────────────────────────────
def _note_ns(card, note, session=None):
    return NS(card=str(card), note=note, session=session)


def _card_with_history(cards, sid, date="05 Aug 2026", note=""):
    tail = f" — {note}" if note else ""
    return make_card(cards, "hist", session=sid), f"- `{sid}` — {date}{tail}\n"


def test_note_writes_the_what_it_did_on_the_pinned_entry(cc, tmp_path, monkeypatch, capsys):
    """The last hand-edit in the system: `link` writes the id and date, and the note was
    left to whoever was editing the card body directly."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card, entry = _card_with_history(cards, sid)
    card.write_text(card.read_text() + entry)

    cc.cmd_note(_note_ns(card, "shipped the note writer"))
    body = card.read_text().split("## Sessions", 1)[1]
    assert f"- `{sid}` — 05 Aug 2026 — shipped the note writer" in body
    assert "noted" in capsys.readouterr().out


def test_note_preserves_the_date_link_wrote(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card, entry = _card_with_history(cards, sid, date="02 Jul 2026")
    card.write_text(card.read_text() + entry)
    cc.cmd_note(_note_ns(card, "a note"))
    assert "02 Jul 2026" in card.read_text()


def test_note_replaces_an_existing_note_rather_than_appending(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card, entry = _card_with_history(cards, sid, note="first take")
    card.write_text(card.read_text() + entry)
    cc.cmd_note(_note_ns(card, "second take"))
    body = card.read_text()
    assert "second take" in body and "first take" not in body


def test_note_empty_clears_it_but_keeps_id_and_date(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card, entry = _card_with_history(cards, sid, note="remove me")
    card.write_text(card.read_text() + entry)
    cc.cmd_note(_note_ns(card, ""))
    assert f"- `{sid}` — 05 Aug 2026\n" in card.read_text()
    assert "remove me" not in card.read_text()


def test_note_targets_an_older_entry_with_session(cc, tmp_path, monkeypatch):
    """Filling in the stint you just displaced — the case the convention actually asks for."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    pinned = "11111111-2222-3333-4444-555555555555"
    older = "99999999-8888-7777-6666-555555555555"
    card = make_card(cards, "hist", session=pinned)
    card.write_text(card.read_text() + f"- `{pinned}` — 08 Aug 2026\n"
                                       f"- `{older}` — 02 Jul 2026\n")
    cc.cmd_note(_note_ns(card, "did the earlier half", session=older))
    body = card.read_text()
    assert f"- `{older}` — 02 Jul 2026 — did the earlier half" in body
    assert f"- `{pinned}` — 08 Aug 2026\n" in body          # untouched


def test_note_leaves_other_lines_byte_identical(cc, tmp_path, monkeypatch):
    """The history is hand-readable markdown that also holds lines cardctl can't parse."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card = make_card(cards, "hist", session=sid)
    card.write_text(card.read_text() + f"- `{sid}` — 05 Aug 2026\n"
                                       "- a hand-written line cardctl doesn't parse\n"
                                       "  continued prose under it\n")
    before = card.read_text().splitlines()
    cc.cmd_note(_note_ns(card, "x"))
    after = card.read_text().splitlines()
    assert len(before) == len(after)
    assert after[-2:] == before[-2:]                        # the unparsed lines survive


def test_note_dies_when_the_session_has_no_entry(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "hist", session="11111111-2222-3333-4444-555555555555")
    with pytest.raises(SystemExit):
        cc.cmd_note(_note_ns(card, "nothing to attach to"))
    assert "no `## Sessions` entry" in capsys.readouterr().err


def test_note_dies_when_nothing_is_pinned(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "hist")                          # no sessionId
    with pytest.raises(SystemExit):
        cc.cmd_note(_note_ns(card, "text"))
    assert "no pinned session" in capsys.readouterr().err


@pytest.mark.parametrize("bad,msg", [
    ("outside", "not inside a configured Cards/ folder"),
    ("missing", "no such card"),
])
def test_note_guards_match_the_other_writers(cc, tmp_path, monkeypatch, capsys, bad, msg):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    if bad == "outside":
        target = tmp_path / "loose.md"
        target.write_text("---\ntitle: T\n---\n")
    else:
        target = tmp_path / "Cards" / "ghost.md"
    with pytest.raises(SystemExit):
        cc.cmd_note(_note_ns(target, "text"))
    assert msg in capsys.readouterr().err


# ── unpin (clear the pin, keep the history) ─────────────────────────────────────
def test_unpin_clears_session_id_and_keeps_history(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    sid = "11111111-2222-3333-4444-555555555555"
    card = make_card(cards, "dormant", session=sid)
    # make_card's extra_body lands *above* ## Sessions, so log the entry where cardctl
    # writes it — under the heading — to prove unpin leaves the history alone.
    card.write_text(card.read_text() + f"- `{sid}` — 2026-07-20 — did a thing\n")

    cc.cmd_unpin(NS(card=str(card)))
    fm, text = cc.read_card(str(card))
    assert "sessionId" not in fm                       # pin gone
    assert f"- `{sid}`" in text.split("## Sessions", 1)[1]   # history intact
    assert "unpinned" in capsys.readouterr().out


def test_unpin_already_unpinned_is_a_noop_not_an_error(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "never-pinned")
    before = card.read_text()

    cc.cmd_unpin(NS(card=str(card)))                  # no SystemExit
    assert card.read_text() == before                 # byte-identical
    assert "already unpinned" in capsys.readouterr().out


def test_unpin_refuses_markdown_outside_cards_dirs(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    loose = tmp_path / "loose.md"
    loose.write_text("---\ntitle: T\nstatus: backlog\nsessionId: dead-beef\n---\nbody\n")
    before = loose.read_text()
    with pytest.raises(SystemExit):
        cc.cmd_unpin(NS(card=str(loose)))
    assert "not inside a configured Cards/ folder" in capsys.readouterr().err
    assert loose.read_text() == before                 # untouched


def test_unpin_refuses_missing_card(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": tmp_path / "Cards"})
    with pytest.raises(SystemExit):
        cc.cmd_unpin(NS(card=str(tmp_path / "Cards" / "ghost.md")))
    assert "no such card" in capsys.readouterr().err


def test_unpin_then_link_repins(cc, tmp_path, monkeypatch):
    """unpin is the inverse of link, not a one-way door."""
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    folder = tmp_path / "active" / "x"
    folder.mkdir(parents=True)
    card = make_card(cards, "round-trip", paths=[str(folder)], session="old-pin")
    sid = fake_transcript(projects, str(folder))

    cc.cmd_unpin(NS(card=str(card)))
    assert "sessionId" not in cc.read_card(str(card))[0]
    cc.cmd_link(NS(card=str(card), session=None, current=False, cwd=None, force=False))
    assert cc.read_card(str(card))[0]["sessionId"] == sid


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
def _git_repo(path, branch="main"):
    """A real throwaway git repo on `branch` — the guard shells out to git, so fake it honestly."""
    path.mkdir(parents=True, exist_ok=True)
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(path)}
    def git(*a):
        subprocess.run(["git", "-C", str(path), *a], check=True, env=env,
                       capture_output=True, text=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (path / "f").write_text("x")
    git("add", "."); git("commit", "-qm", "init")
    if branch != "main":
        git("checkout", "-q", "-b", branch)
    return path


def test_guard_allows_deploy_from_main(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "REPO", _git_repo(tmp_path / "r"))
    cc.guard_deploy_source(force=False)          # no SystemExit


def test_guard_refuses_deploy_from_a_feature_branch(cc, tmp_path, monkeypatch, capsys):
    """The 6 Aug near-miss: the fallback REPO sat on cardctl-customer-edge."""
    monkeypatch.setattr(cc, "REPO", _git_repo(tmp_path / "r", branch="cardctl-customer-edge"))
    with pytest.raises(SystemExit):
        cc.guard_deploy_source(force=False)
    err = capsys.readouterr().err
    assert "cardctl-customer-edge" in err        # names the branch
    assert "--force" in err                      # names the escape hatch


def test_guard_force_warns_but_proceeds(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "REPO", _git_repo(tmp_path / "r", branch="wip"))
    cc.guard_deploy_source(force=True)           # no SystemExit
    assert "warning" in capsys.readouterr().err


def test_guard_refuses_detached_head(cc, tmp_path, monkeypatch, capsys):
    repo = _git_repo(tmp_path / "r")
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin", "HOME": str(repo)}
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                         text=True, env=env).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", sha], check=True, env=env,
                   capture_output=True)
    monkeypatch.setattr(cc, "REPO", repo)
    with pytest.raises(SystemExit):
        cc.guard_deploy_source(force=False)
    assert "undeterminable" in capsys.readouterr().err


def test_guard_refuses_when_source_is_not_a_git_checkout(cc, tmp_path, monkeypatch):
    """Can't name the source → can't claim it's releasable."""
    monkeypatch.setattr(cc, "REPO", tmp_path / "not-a-repo")
    (tmp_path / "not-a-repo").mkdir()
    with pytest.raises(SystemExit):
        cc.guard_deploy_source(force=False)


def test_cmd_deploy_is_actually_guarded_before_writing(cc, tmp_path, monkeypatch, capsys):
    """Wiring test: the refusal must happen before any surface is touched."""
    repo = _git_repo(tmp_path / "r", branch="feature")
    (repo / "deploy").mkdir()
    monkeypatch.setattr(cc, "REPO", repo)
    monkeypatch.setattr(cc, "DEPLOY_SRC", repo / "deploy")
    bin_dir = tmp_path / "bin"
    monkeypatch.setattr(cc, "BIN", bin_dir)
    with pytest.raises(SystemExit):
        cc.cmd_deploy(NS(domain="all", apply=True, force=False))
    assert not bin_dir.exists()                  # nothing written
    assert "refusing to deploy" in capsys.readouterr().err


def test_every_deploy_surface_source_exists(cc):
    """A surface whose fragment has been deleted breaks `deploy` at run time, in both
    live vaults. Caught here instead: retiring the meta-bind buttons removed a fragment,
    and the surface list had to lose its entry in the same change."""
    missing = [(label, src) for label, _dest, _kind, src in cc.DEPLOY_SURFACES
               if not (cc.DEPLOY_SRC / src).exists()]
    assert missing == []


def test_deploy_surfaces_no_longer_include_meta_bind(cc):
    """R14: launching is the board's job, so the in-note button surface is gone, not
    deployed empty — deploy never deletes, so an empty fragment would leave the buttons
    in place forever."""
    labels = [label for label, *_ in cc.DEPLOY_SURFACES]
    assert not any("meta-bind" in label for label in labels), labels


def test_shell_commands_fragment_keeps_only_the_palette_launch(cc):
    """The one deliberately-kept entry: a keyboard route into a card if the board is down."""
    frag = json.loads((cc.DEPLOY_SRC / "fragments/shellcommands.commands.json").read_text())
    assert [c["id"] for c in frag] == ["mnosc79dtm"]
    assert "-d" not in frag[0]["platform_specific_commands"]["default"]


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


def test_set_status_rejects_archived(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "demo", status="in-progress")
    before = card.read_text()
    with pytest.raises(SystemExit):
        cc.cmd_set_status(NS(card=str(card), status="archived"))
    assert "cardctl archive" in capsys.readouterr().err  # message points at the real command
    assert card.read_text() == before  # frontmatter untouched


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


# ── parse_sessions / session history in list --json (#41) ──────────────────────
SID_A = "aaaaaaaa-1111-2222-3333-444444444444"
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"


def sessions_card(cards_dir, slug, lines, heading="## Sessions"):
    """A card whose `## Sessions` section holds `lines` verbatim, followed by
    another section (so parsing must stop at the boundary)."""
    card = make_card(cards_dir, slug)
    card.write_text(card.read_text().replace(
        "## Sessions\n",
        heading + "\n\n" + "".join(ln + "\n" for ln in lines)
        + "\n## Notes\n\n- `not-a-session` — prose under a later heading\n", 1))
    return card


def test_parse_sessions_happy_path_order_and_fields(cc):
    text = ("---\ntitle: T\n---\n\n## Sessions\n\n"
            f"- `{SID_A}` — 02 Jul 2026 — Implemented slice 5 — with a dash inside.\n"
            f"- `{SID_B}` — 28 Jun 2026 — Earlier work.\n")
    got = cc.parse_sessions(text)
    assert got == [
        {"id": SID_A, "date": "02 Jul 2026",
         "context": "Implemented slice 5 — with a dash inside."},
        {"id": SID_B, "date": "28 Jun 2026", "context": "Earlier work."},
    ]  # card order preserved (newest first, per the link convention)


def test_parse_sessions_tolerates_handwritten_variants(cc):
    text = ("## Sessions\n"
            f"- `{SID_A}` — 28 Jun 2026: colon before the context\n"
            f"- `{SID_B}` — 28 Jun 2026\n")  # date only — link writes this shape
    got = cc.parse_sessions(text)
    assert got[0]["date"] == "28 Jun 2026"
    assert got[0]["context"] == "colon before the context"
    assert got[1] == {"id": SID_B, "date": "28 Jun 2026", "context": ""}


def test_parse_sessions_skips_malformed_lines(cc):
    text = ("## Sessions\n"
            "- plain prose bullet, no uuid\n"
            "- `docs/CLAUDE.md` — a backticked non-uuid\n"
            "- `aaaaaaaa-1111` — truncated uuid\n"
            f"- `{SID_A}` — 02 Jul 2026 — the one good line\n"
            "stray non-bullet text\n")
    got = cc.parse_sessions(text)
    assert [e["id"] for e in got] == [SID_A]


def test_parse_sessions_missing_heading_yields_empty(cc):
    assert cc.parse_sessions("---\ntitle: T\n---\n\nbody, no sessions heading\n") == []


def test_parse_sessions_stops_at_next_heading(cc):
    text = ("## Sessions\n"
            f"- `{SID_A}` — 02 Jul 2026 — in section\n"
            "## Notes\n"
            f"- `{SID_B}` — 02 Jul 2026 — outside section\n")
    assert [e["id"] for e in cc.parse_sessions(text)] == [SID_A]


def test_list_json_sessions_shape_and_resolution(cc, tmp_path, monkeypatch, capsys):
    """JSON shape locked: each entry is exactly {id, date, context, resumable,
    projectDir}; projectDir comes from the transcript's cwd record (the worktree
    the session ran in), never the card's own paths."""
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    worktree = str((tmp_path / "worktrees" / "repo-slice-5").resolve())
    fake_transcript(projects, worktree, sid=SID_A)
    sessions_card(cards, "c", [
        f"- `{SID_A}` — 02 Jul 2026 — ran in a worktree",
        f"- `{SID_B}` — 28 Jun 2026 — transcript since deleted",
    ])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_list(NS(json=True))
    got = json.loads(capsys.readouterr().out)[0]["sessions"]
    assert got == [
        {"id": SID_A, "date": "02 Jul 2026", "context": "ran in a worktree",
         "resumable": True, "projectDir": worktree},
        {"id": SID_B, "date": "28 Jun 2026", "context": "transcript since deleted",
         "resumable": False, "projectDir": None},
    ]


def test_list_json_sessions_projectdir_none_without_cwd_record(cc, tmp_path, monkeypatch, capsys):
    projects = tmp_path / "projects"
    monkeypatch.setattr(cc, "PROJECTS", projects)
    cards = tmp_path / "Cards"
    folder = str((tmp_path / "active" / "x").resolve())
    fake_transcript(projects, folder, sid=SID_A, cwd_in_record=False)
    sessions_card(cards, "c", [f"- `{SID_A}` — 02 Jul 2026 — cwd-less transcript"])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_list(NS(json=True))
    e = json.loads(capsys.readouterr().out)[0]["sessions"][0]
    assert e["resumable"] is True    # the file exists…
    assert e["projectDir"] is None   # …but its cwd can't be recovered


def test_list_json_sessions_empty_without_entries(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    cards = tmp_path / "Cards"
    make_card(cards, "bare")  # heading present, no entries
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    cc.cmd_list(NS(json=True))
    assert json.loads(capsys.readouterr().out)[0]["sessions"] == []


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


def test_set_fm_field_replace_is_byte_for_byte(cc):
    doc = ('---\ntype: project\ntitle: "T: a card"\nstatus: backlog\n'
           'foreign: kept # as-is\n---\nbody\n')
    out = cc.set_fm_field(doc, "status", "done")
    assert out == doc.replace("status: backlog", "status: done")


def test_set_fm_field_delete_absent_inserts_nothing(cc):
    doc = "---\ntitle: T\n---\nbody\n"
    assert cc.set_fm_field(doc, "archivedAt", None) == doc


def test_set_fm_field_duplicate_keys_first_wins_rest_dropped(cc):
    doc = "---\ntitle: T\nstatus: backlog\nstatus: done\n---\nbody\n"
    out = cc.set_fm_field(doc, "status", "on-hold")
    assert out == "---\ntitle: T\nstatus: on-hold\n---\nbody\n"


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


# ── slice 3: atomicity (preflight, frontmatter-last, containment, scoped staging) ──
def _archive_prefix():
    import datetime
    return datetime.date.today().strftime("%Y-%m-")


def _head(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_archive_dies_on_destination_collision_tracked(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, folder = _git_repo_with_folder(tmp_path, "active", "thing")
    target = repo / "archive" / f"{_archive_prefix()}thing"
    target.mkdir(parents=True)                    # collision
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="in-progress", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    head = _head(repo)

    with pytest.raises(SystemExit):
        cc.cmd_archive(NS(card=str(card), json=False))
    assert "already exists" in capsys.readouterr().err
    # no mutation: folder in place (not nested into target), frontmatter untouched, no commit
    assert folder.is_dir() and not (target / "thing").exists()
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "in-progress" and "archivedAt" not in fm
    assert _head(repo) == head


def test_archive_dies_on_destination_collision_untracked(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, _ = _git_repo_with_folder(tmp_path, "active", "other")
    loose = repo / "active" / "loose"             # never committed
    loose.mkdir(parents=True)
    (loose / "notes.md").write_text("draft\n")
    target = repo / "archive" / f"{_archive_prefix()}loose"
    target.mkdir(parents=True)                    # collision
    cards = tmp_path / "Cards"
    card = make_card(cards, "loose", status="in-progress", paths=[str(loose)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    head = _head(repo)

    with pytest.raises(SystemExit):
        cc.cmd_archive(NS(card=str(card), json=False))
    assert "already exists" in capsys.readouterr().err
    # the old mv fallback would have NESTED loose inside the existing target
    assert loose.is_dir() and not (target / "loose").exists()
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "in-progress" and "archivedAt" not in fm
    assert _head(repo) == head


def test_archive_dies_when_repo_is_not_git(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    folder = _active_folder(tmp_path, "nogit")    # plain dir, no git init
    cards = tmp_path / "Cards"
    card = make_card(cards, "nogit", status="in-progress", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    with pytest.raises(SystemExit):
        cc.cmd_archive(NS(card=str(card), json=False))
    assert "not a git repository" in capsys.readouterr().err
    assert folder.is_dir()
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "in-progress" and "archivedAt" not in fm


def test_archive_frontmatter_last_on_move_failure(cc, tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, folder = _git_repo_with_folder(tmp_path, "active", "thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="in-progress", paths=[str(folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    def boom(*a, **kw):
        raise subprocess.CalledProcessError(128, ["git", "mv", "x", "y"])
    monkeypatch.setattr(cc, "_move_card_folder", boom)

    with pytest.raises(SystemExit):
        cc.cmd_archive(NS(card=str(card), json=False))
    err = capsys.readouterr().err
    assert "git" in err and "exit 128" in err            # names the failing step
    assert "completed so far" in err                     # residual state reported
    assert "NOT updated" in err
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "in-progress" and "archivedAt" not in fm


def test_reinstate_frontmatter_last_on_move_failure(cc, tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    card.write_text(card.read_text().replace(
        "status: archived\n", "status: archived\narchivedAt: 2026-06-30T09:20:14+08:00\n"))
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    def boom(*a, **kw):
        raise subprocess.CalledProcessError(1, ["git", "mv"])
    monkeypatch.setattr(cc, "_move_card_folder", boom)

    with pytest.raises(SystemExit):
        cc.cmd_reinstate(NS(card=str(card), json=False))
    assert "still archived" in capsys.readouterr().err
    fm, _ = cc.read_card(str(card))
    assert fm["status"] == "archived" and fm["archivedAt"]   # untouched


def test_archive_untracked_folder_uses_move_plus_add_fallback(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, _ = _git_repo_with_folder(tmp_path, "active", "other")
    loose = repo / "active" / "loose"             # never committed → git mv fails
    loose.mkdir(parents=True)
    (loose / "notes.md").write_text("draft\n")
    cards = tmp_path / "Cards"
    card = make_card(cards, "loose", status="in-progress", paths=[str(loose)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_archive(NS(card=str(card), json=True))
    out = json.loads(capsys.readouterr().out)
    target = repo / "archive" / f"{_archive_prefix()}loose"
    assert out["moved"][0]["to"] == str(target)
    assert target.is_dir() and not loose.exists()
    committed = _git(repo, "show", "--name-only", "--format=%s", "HEAD").stdout
    assert "Archive: loose" in committed and "notes.md" in committed


def test_delete_untracked_fallback_stages_only_deleted_path(cc, tmp_path, monkeypatch, capsys):
    """git rm refuses a folder with local modifications → fallback path. The scoped
    `git add -A -- <rel>` must not sweep unrelated dirty files into the commit."""
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, arch_folder = _git_repo_with_folder(tmp_path, "archive", "2026-06-thing")
    unrelated = repo / "unrelated.md"
    unrelated.write_text("tracked\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add unrelated")
    (arch_folder / "README.md").write_text("modified\n")   # makes git rm refuse
    unrelated.write_text("dirty edit — must NOT ride into the Delete commit\n")
    cards = tmp_path / "Cards"
    card = make_card(cards, "thing", status="archived", paths=[str(arch_folder)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_delete(NS(card=str(card), confirm="thing", json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["deleted"] == [str(arch_folder)]
    assert not arch_folder.exists() and not card.exists()
    committed = _git(repo, "show", "--name-only", "--format=%s", "HEAD").stdout
    assert "Delete: 2026-06-thing" in committed
    assert "unrelated.md" not in committed
    assert unrelated.read_text().startswith("dirty edit")  # still dirty on disk


def test_delete_fully_untracked_folder_skips_empty_commit(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, _ = _git_repo_with_folder(tmp_path, "archive", "2026-06-other")
    loose = repo / "archive" / "2026-06-loose"    # never committed
    loose.mkdir(parents=True)
    (loose / "notes.md").write_text("draft\n")
    cards = tmp_path / "Cards"
    card = make_card(cards, "loose", status="archived", paths=[str(loose)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    head = _head(repo)

    cc.cmd_delete(NS(card=str(card), confirm="loose", json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["deleted"] == [str(loose)]
    assert not loose.exists() and not card.exists()
    assert _head(repo) == head                    # nothing to commit → no commit


def test_reconcile_collision_skips_and_batch_continues(cc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cc, "PROJECTS", tmp_path / "projects")
    repo, f_a = _git_repo_with_folder(tmp_path, "active", "aaa")
    f_b = repo / "active" / "bbb"
    f_b.mkdir(parents=True)
    (f_b / "README.md").write_text("# bbb\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add bbb")
    prefix = _archive_prefix()
    (repo / "archive" / f"{prefix}aaa").mkdir(parents=True)   # collision for aaa only
    cards = tmp_path / "Cards"
    make_card(cards, "aaa", status="archived", paths=[str(f_a)])
    make_card(cards, "bbb", status="archived", paths=[str(f_b)])
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})

    cc.cmd_reconcile(NS(apply=True))
    out = capsys.readouterr().out
    assert f"SKIP (destination exists): {repo / 'archive' / (prefix + 'aaa')}" in out
    assert f_a.is_dir()                                       # aaa left alone
    assert not f_b.exists()                                   # bbb still filed
    assert (repo / "archive" / f"{prefix}bbb").is_dir()


# ── build_workspace: window.title injection ───────────────────────────────────
def test_build_workspace_injects_window_title(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CACHE", tmp_path / "cache")
    folder = tmp_path / "act"
    folder.mkdir()
    card = make_card(tmp_path / "Cards", "demo", title="My Card", paths=[str(folder)])
    ws, folders = cc.build_workspace(str(card), {"title": "My Card", "paths": [str(folder)]}, None)
    settings = json.loads(ws.read_text())["settings"]
    assert settings["window.title"] == "My Card — ${rootName}"


# ── build_workspace: bypass is always armed, never forced (slice 9a) ──────────
def test_build_workspace_always_arms_never_forces(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CACHE", tmp_path / "cache")
    folder = tmp_path / "act"
    folder.mkdir()
    card = make_card(tmp_path / "Cards", "demo", title="My Card", paths=[str(folder)])
    ws, _ = cc.build_workspace(str(card), {"title": "My Card", "paths": [str(folder)]}, None)
    settings = json.loads(ws.read_text())["settings"]
    assert settings["claudeCode.allowDangerouslySkipPermissions"] is True
    assert "claudeCode.initialPermissionMode" not in settings


# ── focus (osascript mocked; no real windows) ─────────────────────────────────
def test_focus_builds_osascript_with_card_title(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
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
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [])  # window not open
    cc.cmd_focus(NS(card=str(card)))
    assert calls["argv"][0] == cc.OSASCRIPT
    assert calls["argv"][1] == "-e"
    assert "My Special Card" in calls["argv"][2]          # title embedded in script
    assert 'process "Code"' in calls["argv"][2]
    assert "AXRaise" in calls["argv"][2]
    assert "focused" in capsys.readouterr().out


def test_focus_failure_is_reported_not_raised(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
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
    def no_code():
        raise cc.CodeUnavailable("code (VS Code CLI) not found")
    monkeypatch.setattr(cc, "vscode_status_windows", no_code)
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



def _no_native(monkeypatch, cc):
    """Disable the zero-spawn fast path (#51) so a test exercises the spawned
    engines (`code --status` + Hammerspoon)."""
    def raise_native():
        raise cc.NativeUnavailable("disabled in test")
    monkeypatch.setattr(cc, "native_windows", raise_native)


def test_hs_code_windows_parses_json(cc, monkeypatch):
    _fake_hs(monkeypatch, cc,
             stdout='[{"id":19146,"title":"X — session-card-board (Workspace)","focused":true}]')
    wins = cc.hs_code_windows()
    assert wins == [{"id": 19146, "title": "X — session-card-board (Workspace)",
                     "focused": True}]


def test_hs_code_windows_defaults_focused_false_when_absent(cc, monkeypatch):
    # Output from a snippet without the focused flag still parses (focused → False).
    _fake_hs(monkeypatch, cc, stdout='[{"id":1,"title":"T — t (Workspace)"}]')
    assert cc.hs_code_windows() == [{"id": 1, "title": "T — t (Workspace)",
                                     "focused": False}]


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
    assert wins == [{"id": 21465, "title": "Determine Card Hiearchy — determine-card-hiearchy (Workspace)",
                     "focused": False}]


def test_hs_code_windows_raises_when_port_unreachable(cc, monkeypatch):
    _fake_hs(monkeypatch, cc, stderr="hs: can't access … message port")
    with pytest.raises(cc.HsUnavailable):
        cc.hs_code_windows()


def test_hs_code_windows_raises_on_missing_binary(cc, monkeypatch):
    _fake_hs(monkeypatch, cc, raises=FileNotFoundError())
    with pytest.raises(cc.HsUnavailable):
        cc.hs_code_windows()


def test_windows_json_maps_matched_and_unmatched(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    cards = tmp_path / "Cards"
    matched = make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [
        "Board — session-card-board (Workspace)",
        "no-card-here — unknown-slug (Workspace)",
        "a manually opened folder",                          # no separator → slug None
    ])
    _fake_hs(monkeypatch, cc, stdout=json.dumps([
        {"id": 19146, "title": "Board — session-card-board (Workspace)"},
        {"id": 222, "title": "no-card-here — unknown-slug (Workspace)"},
        {"id": 333, "title": "a manually opened folder"},
    ]))
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    w = {r["id"]: r for r in out["windows"]}
    assert w[19146]["slug"] == "session-card-board"
    assert w[19146]["filePath"] == str(matched.resolve())
    assert w[222]["slug"] == "unknown-slug" and w[222]["filePath"] is None
    assert w[333]["slug"] is None and w[333]["filePath"] is None


def test_windows_json_cross_space_window_has_null_id(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # The core of #47: VS Code reports windows on every Mission Control space,
    # Hammerspoon only the current one — off-space windows must still be listed,
    # with id null (nothing for focus-by-id to target).
    cards = tmp_path / "Cards"
    here = make_card(cards, "on-this-space", title="Here")
    away = make_card(cards, "on-other-space", title="Away")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [
        "Here — on-this-space (Workspace)",
        "Away — on-other-space (Workspace)",
    ])
    _fake_hs(monkeypatch, cc, stdout=json.dumps([
        {"id": 40691, "title": "Here — on-this-space (Workspace)"},
    ]))
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    w = {r["slug"]: r for r in out["windows"]}
    assert w["on-this-space"]["id"] == 40691
    assert w["on-this-space"]["filePath"] == str(here.resolve())
    assert w["on-other-space"]["id"] is None                 # invisible to AX
    assert w["on-other-space"]["filePath"] == str(away.resolve())


def test_windows_json_id_attaches_by_slug_when_titles_disagree(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # The engines can disagree on the dirty-window suffix ("… — Modified") —
    # the id must still attach via the slug.
    cards = tmp_path / "Cards"
    make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [
        "Board — session-card-board (Workspace)",
    ])
    _fake_hs(monkeypatch, cc, stdout=json.dumps([
        {"id": 7, "title": "Board — session-card-board (Workspace) — Modified"},
    ]))
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["windows"][0]["id"] == 7


def test_windows_json_degrades_to_hs_when_code_cli_unavailable(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # `code` CLI missing → the Hammerspoon-only (current-space) view, still available.
    cards = tmp_path / "Cards"
    matched = make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    def no_code():
        raise cc.CodeUnavailable("code (VS Code CLI) not found")
    monkeypatch.setattr(cc, "vscode_status_windows", no_code)
    _fake_hs(monkeypatch, cc, stdout=json.dumps([
        {"id": 19146, "title": "Board — session-card-board (Workspace)"},
    ]))
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    assert out["windows"][0]["id"] == 19146
    assert out["windows"][0]["filePath"] == str(matched.resolve())


def test_windows_json_engine_unavailable_is_available_false(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # available:false only when every engine is down.
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": tmp_path / "Cards"})
    def no_code():
        raise cc.CodeUnavailable("code (VS Code CLI) not found")
    monkeypatch.setattr(cc, "vscode_status_windows", no_code)
    _fake_hs(monkeypatch, cc, stderr="hs: can't access … message port")
    cc.cmd_windows(NS(json=True))  # must exit 0 (return), not raise
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is False
    assert out["windows"] == []
    assert out["error"]


# ── vscode_status_windows / _run_code (`code` CLI mocked) ───────────────────────
def _fake_code_status(monkeypatch, cc, *, stdout="", stderr="", returncode=0, raises=None):
    """Monkeypatch _run_code as `code --status` would behave."""
    def fake_run_code(argv_tail, timeout):
        assert argv_tail == ["--status"]
        if raises is not None:
            raise raises
        return stdout, stderr, returncode
    monkeypatch.setattr(cc, "_run_code", fake_run_code)


def test_vscode_status_windows_parses_window_lines(cc, monkeypatch):
    _fake_code_status(monkeypatch, cc, stdout=(
        "Version:          Code 1.101.2\n"
        "Workspace Stats: \n"
        "|  Window (Board (Phase 2) — session-card-board (Workspace))\n"
        "|  Window (Away — on-other-space (Workspace))\n"
        "|    Folder (session-card-board): 3 files\n"
    ))
    assert cc.vscode_status_windows() == [
        "Board (Phase 2) — session-card-board (Workspace)",  # inner parens survive
        "Away — on-other-space (Workspace)",
    ]


def test_vscode_status_windows_empty_when_no_windows(cc, monkeypatch):
    _fake_code_status(monkeypatch, cc, stdout="Version:          Code 1.101.2\n")
    assert cc.vscode_status_windows() == []


def test_vscode_status_windows_propagates_engine_failure(cc, monkeypatch):
    _fake_code_status(monkeypatch, cc,
                      raises=cc.CodeUnavailable("code (VS Code CLI) not found"))
    with pytest.raises(cc.CodeUnavailable):
        cc.vscode_status_windows()


def test_vscode_status_windows_raises_on_nonzero_exit(cc, monkeypatch):
    _fake_code_status(monkeypatch, cc, returncode=1, stderr="boom")
    with pytest.raises(cc.CodeUnavailable):
        cc.vscode_status_windows()


def test_run_code_raises_on_missing_binary(cc, monkeypatch):
    def fake_popen(argv, **kw):
        raise FileNotFoundError()
    monkeypatch.setattr(cc.subprocess, "Popen", fake_popen)
    with pytest.raises(cc.CodeUnavailable):
        cc._run_code(["--status"], timeout=5)


def test_run_code_spawns_own_process_group(cc, monkeypatch):
    # start_new_session=True is what makes killpg reach the Electron grandchild
    # the `code` bash wrapper spawns without exec (#49).
    captured = {}

    class FakeProc:
        pid = 1
        returncode = 0
        def communicate(self, timeout=None):
            return "out", ""

    def fake_popen(argv, **kw):
        captured.update(kw)
        assert argv[0] == cc.CODE and argv[1:] == ["--status"]
        return FakeProc()
    monkeypatch.setattr(cc.subprocess, "Popen", fake_popen)
    assert cc._run_code(["--status"], timeout=5) == ("out", "", 0)
    assert captured.get("start_new_session") is True
    assert captured.get("stdin") == cc.subprocess.DEVNULL


def test_run_code_kills_process_group_on_timeout(cc, monkeypatch):
    # The core of #49: on timeout the WHOLE process group must be SIGKILLed
    # (not just the wrapper), and the post-kill reap must not block.
    killed = {}
    calls = {"communicate": 0}

    class FakeProc:
        pid = 4242
        returncode = -9
        def communicate(self, timeout=None):
            calls["communicate"] += 1
            if timeout is not None:
                raise cc.subprocess.TimeoutExpired(cmd="code", timeout=timeout)
            return "", ""                      # reap after the group is dead
    monkeypatch.setattr(cc.subprocess, "Popen", lambda *a, **kw: FakeProc())
    monkeypatch.setattr(cc.os, "killpg",
                        lambda pgid, sig: killed.update(pgid=pgid, sig=sig))
    with pytest.raises(cc.CodeUnavailable, match="timed out"):
        cc._run_code(["--status"], timeout=1)
    assert killed == {"pgid": 4242, "sig": cc.signal.SIGKILL}
    assert calls["communicate"] == 2           # timed-out wait + post-kill reap


# ── native windows (storage.json × CGWindowList — both mocked) ──────────────────
def test_file_uri_to_path_decodes_and_rejects(cc):
    assert cc._file_uri_to_path(
        "file:///Users/steve/.cache/session-cards/my%20card.code-workspace"
    ) == "/Users/steve/.cache/session-cards/my card.code-workspace"
    assert cc._file_uri_to_path("vscode-remote://x/y") is None
    assert cc._file_uri_to_path(None) is None


def _write_storage(tmp_path, opened):
    storage = tmp_path / "storage.json"
    storage.write_text(json.dumps({"windowsState": {"openedWindows": opened}}))
    return storage


def test_vscode_state_windows_parses_workspace_folder_and_empty(cc, tmp_path, monkeypatch):
    storage = _write_storage(tmp_path, [
        {"workspaceIdentifier":
            {"configURIPath": "file:///Users/x/.cache/session-cards/my-card.code-workspace"},
         "uiState": {"mode": 1, "x": 71, "y": -1368, "width": 2930, "height": 1368}},
        {"folder": "file:///Users/x/active/some-task",
         "uiState": {"mode": 1, "x": 0, "y": 0, "width": 800, "height": 600}},
        {"backupPath": "/tmp/b", "uiState": {"mode": 1}},   # empty window, no geometry
    ])
    monkeypatch.setattr(cc, "VSCODE_STORAGE", storage)
    assert cc._vscode_state_windows() == [
        {"slug": "my-card", "bounds": (71.0, -1368.0, 2930.0, 1368.0)},
        {"slug": "some-task", "bounds": (0.0, 0.0, 800.0, 600.0)},
        {"slug": None, "bounds": None},
    ]


def test_vscode_state_windows_raises_when_unreadable(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "VSCODE_STORAGE", tmp_path / "missing.json")
    with pytest.raises(cc.NativeUnavailable):
        cc._vscode_state_windows()


def test_vscode_state_windows_raises_without_windows_state(cc, tmp_path, monkeypatch):
    storage = tmp_path / "storage.json"
    storage.write_text(json.dumps({"theme": "dark"}))
    monkeypatch.setattr(cc, "VSCODE_STORAGE", storage)
    with pytest.raises(cc.NativeUnavailable):
        cc._vscode_state_windows()


def test_native_windows_maps_cards_and_attaches_ids_by_geometry(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    board = make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    monkeypatch.setattr(cc, "_vscode_state_windows", lambda: [
        {"slug": "session-card-board", "bounds": (71.0, -1368.0, 2930.0, 1368.0)},
        {"slug": "no-card-for-this", "bounds": (0.0, 0.0, 800.0, 600.0)},
        {"slug": None, "bounds": None},                     # empty window
    ])
    monkeypatch.setattr(cc, "_cg_code_windows", lambda: [
        {"id": 40691, "bounds": (71.0, -1368.0, 2930.0, 1368.0)},
        {"id": 123, "bounds": (0.0, 0.0, 800.0, 600.0)},
        {"id": 456, "bounds": (5.0, 5.0, 640.0, 480.0)},    # the empty window
    ])
    rows = cc.native_windows()
    assert rows == [
        {"id": 40691, "title": "Board — session-card-board (Workspace)",
         "slug": "session-card-board", "filePath": str(board.resolve())},
        {"id": 123, "title": "no-card-for-this",
         "slug": "no-card-for-this", "filePath": None},
        {"id": None, "title": "(empty window)", "slug": None, "filePath": None},
    ]


def test_native_windows_raises_on_count_mismatch(cc, monkeypatch):
    # A window closed since the last state flush (closes are not flushed) —
    # the persisted list over-reports and must NOT be trusted.
    monkeypatch.setattr(cc, "_vscode_state_windows", lambda: [
        {"slug": "a", "bounds": None}, {"slug": "b", "bounds": None},
    ])
    monkeypatch.setattr(cc, "_cg_code_windows", lambda: [
        {"id": 1, "bounds": (0.0, 0.0, 1.0, 1.0)},
    ])
    with pytest.raises(cc.NativeUnavailable, match="window server"):
        cc.native_windows()


def test_native_windows_ambiguous_geometry_gets_null_id(cc, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": tmp_path / "Cards"})
    same = (0.0, 0.0, 800.0, 600.0)
    monkeypatch.setattr(cc, "_vscode_state_windows", lambda: [
        {"slug": "a", "bounds": same}, {"slug": "b", "bounds": same},
    ])
    monkeypatch.setattr(cc, "_cg_code_windows", lambda: [
        {"id": 1, "bounds": same}, {"id": 2, "bounds": same},
    ])
    rows = cc.native_windows()
    assert [r["id"] for r in rows] == [None, None]   # can't tell them apart


def test_windows_json_uses_native_fast_path_without_spawning(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    board = make_card(cards, "session-card-board", title="Board")
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": cards})
    monkeypatch.setattr(cc, "_vscode_state_windows", lambda: [
        {"slug": "session-card-board", "bounds": (0.0, 0.0, 800.0, 600.0)},
    ])
    monkeypatch.setattr(cc, "_cg_code_windows", lambda: [
        {"id": 7, "bounds": (0.0, 0.0, 800.0, 600.0)},
    ])

    def no_spawn(*a, **kw):
        raise AssertionError("native fast path must not spawn a subprocess")
    monkeypatch.setattr(cc.subprocess, "run", no_spawn)
    monkeypatch.setattr(cc.subprocess, "Popen", no_spawn)
    cc.cmd_windows(NS(json=True))
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    assert out["windows"] == [{"id": 7,
                               "title": "Board — session-card-board (Workspace)",
                               "slug": "session-card-board",
                               "filePath": str(board.resolve())}]


def test_focus_cross_space_check_uses_native_fast_path(cc, tmp_path, monkeypatch, capsys):
    # The reopen guard takes its open-window list from native_windows() when the
    # fast path answers — no `code --status` involved.
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    cache = tmp_path / "cache"
    cache.mkdir()
    ws = cache / "session-card-board.code-workspace"
    ws.write_text("{}")
    monkeypatch.setattr(cc, "CACHE", cache)
    monkeypatch.setattr(cc, "native_windows", lambda: [
        {"id": None, "title": "Board — session-card-board (Workspace)",
         "slug": "session-card-board", "filePath": str(card.resolve())},
    ])
    seen = {"reopen": None}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = "[]"                          # hs: no current-space match
        assert argv[0] == cc.HS
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    def fake_run_code(argv_tail, timeout):
        assert argv_tail != ["--status"], "fast path must not fall back to --status"
        seen["reopen"] = argv_tail
        return "", "", 0
    monkeypatch.setattr(cc, "_run_code", fake_run_code)
    cc.cmd_focus(NS(card=str(card)))
    assert seen["reopen"] == [str(ws)]
    assert "another space" in capsys.readouterr().out


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
    _no_native(monkeypatch, cc)
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
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [])  # window not open
    cc.cmd_focus(NS(card=str(card)))
    assert seen["osascript"] is True               # fell back to AXRaise-by-title
    assert "focused" in capsys.readouterr().out


def test_focus_falls_back_to_applescript_when_hs_unavailable(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
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
    monkeypatch.setattr(cc, "vscode_status_windows", lambda: [])  # window not open
    cc.cmd_focus(NS(card=str(card)))
    assert seen["osascript"] is True               # AppleScript fallback used
    assert "focused" in capsys.readouterr().out


def test_focus_reopens_workspace_for_cross_space_window(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # #47: Hammerspoon (AX) can't see a window on another Mission Control space.
    # When VS Code itself reports the window open and the cached workspace exists,
    # focus upgrades to `code <ws>` (raises the existing window there) — no AppleScript.
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    cache = tmp_path / "cache"
    cache.mkdir()
    ws = cache / "session-card-board.code-workspace"
    ws.write_text("{}")
    monkeypatch.setattr(cc, "CACHE", cache)
    seen = {"reopen": None, "osascript": False}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        if argv[0] == cc.HS:
            R.stdout = "[]"                        # current space: no match
        elif argv[0] == cc.OSASCRIPT:
            seen["osascript"] = True
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    def fake_run_code(argv_tail, timeout):
        if argv_tail == ["--status"]:
            return "|  Window (Board — session-card-board (Workspace))\n", "", 0
        seen["reopen"] = argv_tail                 # the workspace reopen
        return "", "", 0
    monkeypatch.setattr(cc, "_run_code", fake_run_code)
    cc.cmd_focus(NS(card=str(card)))
    assert seen["reopen"] == [str(ws)]
    assert seen["osascript"] is False              # never reached AppleScript
    assert "another space" in capsys.readouterr().out


def test_focus_does_not_reopen_when_window_not_open(cc, tmp_path, monkeypatch, capsys):
    _no_native(monkeypatch, cc)
    # A cached workspace file alone must NOT trigger a reopen — `focus` never
    # opens a closed workspace. Falls through to AppleScript instead.
    cards = tmp_path / "Cards"
    card = make_card(cards, "session-card-board", title="Board")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "session-card-board.code-workspace").write_text("{}")
    monkeypatch.setattr(cc, "CACHE", cache)
    seen = {"reopen": False, "osascript": False}

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        if argv[0] == cc.HS:
            R.stdout = "[]"
        elif argv[0] == cc.OSASCRIPT:
            seen["osascript"] = True
        return R()
    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    def fake_run_code(argv_tail, timeout):
        if argv_tail == ["--status"]:
            return "|  Window (Other — other-card (Workspace))\n", "", 0
        seen["reopen"] = True
        return "", "", 0
    monkeypatch.setattr(cc, "_run_code", fake_run_code)
    cc.cmd_focus(NS(card=str(card)))
    assert seen["reopen"] is False
    assert seen["osascript"] is True


# ── new (auto activity folder) ─────────────────────────────────────────────────
def _new_ns(slug, **kw):
    """NS for cmd_new with every field defaulted (mirrors the argparser)."""
    base = dict(slug=slug, title="A title", summary=None, latest=None, path=None,
                session=None, jira=None, area=None, program=None,
                status="in-progress", type="project", domain="work", strict=False,
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


@pytest.mark.parametrize("title", [
    "White paper: Data sources and partitioning",   # colon → invalid YAML unquoted
    "Trailing space and #hash",
    "Plain title",
])
def test_new_quotes_title_so_punctuation_survives_the_round_trip(cc, tmp_path, monkeypatch, title):
    """A colon in --title used to be written bare, producing `title: a: b` — invalid YAML
    that breaks Obsidian's frontmatter parse. Titles are quoted like summary/latest, and
    read back through the same unquote() every consumer (list --json, which) uses."""
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("wp-card", title=title))
    raw, _ = cc.read_card(str(cards / "wp-card.md"))
    assert raw["title"].startswith('"') and raw["title"].endswith('"')   # written quoted
    assert cc.unquote(raw["title"]) == title                            # and reads back intact


def test_new_title_with_colon_is_valid_yaml_for_obsidian(cc, tmp_path, monkeypatch):
    """The actual reported symptom: Obsidian parses the frontmatter as real YAML, so a
    colon in the title must not break that parse. Asserted with a real YAML parser
    rather than cardctl's own scalar reader."""
    yaml = pytest.importorskip("yaml")
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    title = "White paper: Data sources and partitioning"
    cc.cmd_new(_new_ns("wp-yaml", title=title))
    fm_block = (cards / "wp-yaml.md").read_text().split("---\n")[1]
    assert yaml.safe_load(fm_block)["title"] == title


def _seed_area(cards_dir, slug, area):
    """An existing card carrying `area/<area>` — the only evidence an area is real."""
    cards_dir.mkdir(parents=True, exist_ok=True)
    (cards_dir / f"{slug}.md").write_text(
        f"---\ntype: project\ntitle: T\nstatus: in-progress\ntags: [area/{area}]\npaths:\n  - \n---\n")


def test_new_warns_when_the_area_is_used_by_no_existing_card(cc, tmp_path, monkeypatch, capsys):
    """A4.4: `area/tool` for `area/tools` is well-formed, passes every check, and silently
    mints a rival facet only `lint` notices later. The board's picker closes this for the
    create form; CLI-made cards had nothing."""
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    _seed_area(cards, "existing", "tools")
    cc.cmd_new(_new_ns("typo-card", area="tool"))
    err = capsys.readouterr().err
    assert "not used by any existing card" in err
    assert "Did you mean: tools?" in err              # the near-miss is the whole point
    fm, _ = cc.read_card(str(cards / "typo-card.md"))
    assert "area/tool" in fm["tags"]                  # advisory: it still creates it


def test_new_is_quiet_when_the_area_already_exists(cc, tmp_path, monkeypatch, capsys):
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    _seed_area(cards, "existing", "tools")
    cc.cmd_new(_new_ns("good-card", area="tools"))
    assert "not used by any existing card" not in capsys.readouterr().err


def test_new_strict_refuses_an_unknown_area(cc, tmp_path, monkeypatch, capsys):
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    _seed_area(cards, "existing", "tools")
    with pytest.raises(SystemExit):
        cc.cmd_new(_new_ns("typo-card", area="tool", strict=True))
    assert "refusing to create a new area facet" in capsys.readouterr().err
    assert not (cards / "typo-card.md").exists()


def test_new_warns_but_still_allows_a_genuinely_first_card_in_an_area(cc, tmp_path, monkeypatch):
    """Advisory by default on purpose: the first card in a new area must not be blocked by a
    check whose only evidence is 'nobody has used this yet'."""
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("pioneer", area="brand-new"))
    fm, _ = cc.read_card(str(cards / "pioneer.md"))
    assert "area/brand-new" in fm["tags"]


def test_known_areas_spans_both_domains(cc, tmp_path, monkeypatch):
    """Areas are one taxonomy across work and personal — a work card shouldn't be told
    `area/home` is unknown."""
    work = tmp_path / "work" / "Cards"
    personal = tmp_path / "personal" / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": work, "personal": personal})
    _seed_area(work, "w", "tools")
    _seed_area(personal, "p", "home")
    assert cc.known_areas() == ["home", "tools"]


def test_cmd_set_area_warns_on_an_unknown_facet_too(cc, tmp_path, monkeypatch, capsys):
    """`set --area` mints a facet just as readily as `new` does."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    _seed_area(cards, "existing", "tools")
    card = make_card(cards, "c")
    cc.cmd_set(_set_ns(str(card), area="tool"))
    assert "not used by any existing card" in capsys.readouterr().err


def test_new_writes_no_button_bar(cc, tmp_path, monkeypatch):
    """R14: a card body is a record, not a control surface — launching is the board's job.
    Without this, every new card would re-seed the retired Meta Bind buttons and the
    ~69-card sweep would undo itself one card at a time."""
    cards, _ = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("no-buttons", title="No Buttons"))
    body = (cards / "no-buttons.md").read_text().split("---\n", 2)[2]
    assert "BUTTON[" not in body
    assert not hasattr(cc, "BUTTON_BAR")     # the constant is gone, not just unused


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


def test_new_path_naming_auto_folder_yields_single_entry(cc, tmp_path, monkeypatch):
    # #39: --path pointing at the slug's own auto-created activity folder must not
    # write it into paths twice (a duplicate entry breaks the board fly-out downstream).
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("selfie", path=[str(active / "selfie")]))
    fm, _ = cc.read_card(str(cards / "selfie.md"))
    assert fm["paths"] == [str(active / "selfie")]


def test_new_path_naming_auto_folder_deduped_path_normalised(cc, tmp_path, monkeypatch):
    # The compare is path-normalised — a non-canonical spelling of the activity
    # folder (here via `..`) still collapses to the one entry.
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    roundabout = str(active / "twisty" / ".." / "twisty")
    cc.cmd_new(_new_ns("twisty", path=[roundabout]))
    fm, _ = cc.read_card(str(cards / "twisty.md"))
    assert fm["paths"] == [str(active / "twisty")]


def test_new_repeated_path_values_deduped(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    existing = tmp_path / "monorepo"
    existing.mkdir()
    cc.cmd_new(_new_ns("echoey", path=[str(existing), str(existing)]))
    fm, _ = cc.read_card(str(cards / "echoey.md"))
    assert fm["paths"] == [str(active / "echoey"), str(existing)]


def test_new_distinct_paths_survive_dedupe_in_order(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    a = tmp_path / "repo-a"
    b = tmp_path / "repo-b"
    a.mkdir(); b.mkdir()
    cc.cmd_new(_new_ns("varied", path=[str(a), str(b)]))
    fm, _ = cc.read_card(str(cards / "varied.md"))
    assert fm["paths"] == [str(active / "varied"), str(a), str(b)]


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


# ── new (input validation) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("slug", ["../x", "Foo Bar", "foo/bar", "foo_bar", "-lead", "trail-", ""])
def test_new_rejects_bad_slug(cc, tmp_path, monkeypatch, slug, capsys):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        cc.cmd_new(_new_ns(slug))
    assert "invalid slug" in capsys.readouterr().err
    assert not cards.exists()  # nothing created anywhere


def test_new_good_slug_still_creates(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("good-slug-2"))
    assert (cards / "good-slug-2.md").is_file()


def test_new_rejects_bad_status(cc, tmp_path, monkeypatch, capsys):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        cc.cmd_new(_new_ns("a-card", status="blocked"))
    assert "invalid status" in capsys.readouterr().err


def test_new_rejects_bad_type(cc, tmp_path, monkeypatch, capsys):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        cc.cmd_new(_new_ns("a-card", type="epic"))
    assert "invalid type" in capsys.readouterr().err


@pytest.mark.parametrize("card_type", ["project", "program", "bug", "idea", "decision"])
def test_new_accepts_all_card_types(cc, tmp_path, monkeypatch, card_type):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns(f"typed-{card_type}", type=card_type))
    fm, _ = cc.read_card(str(cards / f"typed-{card_type}.md"))
    assert fm["type"] == card_type


@pytest.mark.parametrize("area", ["tools", "area/tools"])
def test_new_normalises_area_tag(cc, tmp_path, monkeypatch, area):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("area-card", area=area))
    fm, _ = cc.read_card(str(cards / "area-card.md"))
    assert fm["tags"] == ["area/tools"]


def test_new_rejects_malformed_area(cc, tmp_path, monkeypatch, capsys):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        cc.cmd_new(_new_ns("a-card", area="area/Bad Slug"))
    assert "invalid --area" in capsys.readouterr().err


def test_new_force_recreate_passes_validation(cc, tmp_path, monkeypatch):
    cards, active = _wire_new(cc, tmp_path, monkeypatch)
    cc.cmd_new(_new_ns("re-card", area="tools"))
    cc.cmd_new(_new_ns("re-card", area="area/tools", force=True))  # --force re-create still validates + succeeds
    fm, _ = cc.read_card(str(cards / "re-card.md"))
    assert fm["tags"] == ["area/tools"]


# ── launch (archived refusal) ───────────────────────────────────────────────────
def test_launch_refuses_archived_card_before_any_subprocess(cc, tmp_path, monkeypatch, capsys):
    cards = tmp_path / "Cards"
    card = make_card(cards, "old-card", status="archived")

    def boom(*a, **kw):
        raise AssertionError("subprocess.run must not be reached for an archived card")
    monkeypatch.setattr(cc.subprocess, "run", boom)
    with pytest.raises(SystemExit):
        cc.cmd_launch(NS(card=str(card), new=False, pick=False, delay=0.0, session=None))
    assert "cardctl reinstate" in capsys.readouterr().err


# ── launch (window polling before the resume URI, #23) ──────────────────────────
def _launch_ns(card, **kw):
    base = dict(card=str(card), new=False, pick=False, delay=0.0, no_poll=False,
                resume=False)
    base.update(kw)
    return NS(**base)


def _launch_rig(cc, tmp_path, monkeypatch):
    """A pinned card + mocked build_workspace/subprocess/sleep for cmd_launch
    sequencing tests. Returns (card_path, calls) where calls records every
    subprocess argv (code / open / osascript).

    CACHE is redirected at a temp dir: it holds the `.launched` marker that decides
    whether VS Code has state to restore, so a real one would make these tests depend on
    (and pollute) the developer's own launch history. Each rig therefore starts as a
    never-launched workspace — the case where firing the URI is correct.
    """
    cards = tmp_path / "Cards"
    folder = tmp_path / "proj"
    folder.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(cc, "CACHE", cache)
    card = make_card(cards, "my-card", paths=[str(folder)], session="sid-123",
                     title="My Card")
    calls = []
    monkeypatch.setattr(cc.subprocess, "run", lambda argv, **kw: calls.append(list(argv)))
    monkeypatch.setattr(cc, "build_workspace",
                        lambda c, fm, sid: (tmp_path / "ws.code-workspace", [str(folder)]))
    monkeypatch.setattr(cc.time, "sleep", lambda s: None)
    return card, calls


def test_launch_fires_uri_once_card_window_frontmost(cc, tmp_path, monkeypatch):
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "Other — other-card (Workspace)", "focused": False},
        {"id": 2, "title": "My Card — my-card (Workspace)", "focused": True},
    ])
    cc.cmd_launch(_launch_ns(card, delay=5.0))
    assert [a for a in calls if a[0] == cc.OPEN] == [[cc.OPEN, cc.URI.format(sid="sid-123")]]


def test_launch_raises_unfocused_window_then_fires(cc, tmp_path, monkeypatch):
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    seq = [
        [{"id": 7, "title": "My Card — my-card (Workspace)", "focused": False}],
        [{"id": 7, "title": "My Card — my-card (Workspace)", "focused": True}],
    ]
    focused = []
    monkeypatch.setattr(cc, "hs_code_windows", lambda: seq.pop(0))
    monkeypatch.setattr(cc, "_focus_by_id", lambda wid: focused.append(wid) or True)
    cc.cmd_launch(_launch_ns(card, delay=5.0))
    assert focused == [7]                                  # raised by id, not hoped-for
    assert any(a[0] == cc.OPEN for a in calls)


def test_launch_times_out_cleanly_without_firing_uri(cc, tmp_path, monkeypatch, capsys):
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 9, "title": "Other — other-card (Workspace)", "focused": True},
    ])
    with pytest.raises(SystemExit):
        cc.cmd_launch(_launch_ns(card, delay=0.0))
    err = capsys.readouterr().err
    assert "my-card" in err and "--no-poll" in err
    assert not any(a[0] == cc.OPEN for a in calls)         # never fired blind
    assert any(a[0] == cc.CODE for a in calls)             # the window WAS opened


def test_launch_falls_back_to_fixed_delay_when_hs_unavailable(cc, tmp_path, monkeypatch, capsys):
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)

    def no_hs():
        raise cc.HsUnavailable("hs (Hammerspoon CLI) not found")
    monkeypatch.setattr(cc, "hs_code_windows", no_hs)
    sleeps = []
    monkeypatch.setattr(cc.time, "sleep", lambda s: sleeps.append(s))
    cc.cmd_launch(_launch_ns(card, delay=2.5))
    assert 2.5 in sleeps                                   # old fixed wait honoured
    assert any(a[0] == cc.OPEN for a in calls)             # URI still fired
    assert "Hammerspoon unavailable" in capsys.readouterr().out


def test_launch_no_poll_skips_hammerspoon(cc, tmp_path, monkeypatch):
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)

    def boom():
        raise AssertionError("hs must not be consulted with --no-poll")
    monkeypatch.setattr(cc, "hs_code_windows", boom)
    cc.cmd_launch(_launch_ns(card, no_poll=True))
    assert any(a[0] == cc.OPEN for a in calls)


def _open_calls(cc, calls):
    return [a for a in calls if a[0] == cc.OPEN]


def test_launch_does_not_fire_uri_on_a_relaunch(cc, tmp_path, monkeypatch):
    """THE duplicate bug (8 Aug). VS Code restores the card window's Claude tabs itself;
    firing the resume URI on top opened a second tab of the same session. Verified live:
    quit with one session open, reopen by hand → one session; launch from the board →
    two. Second and later launches must open the window and stop there."""
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "My Card — my-card (Workspace)", "focused": True}])

    cc.cmd_launch(_launch_ns(card))            # first launch: nothing to restore
    assert _open_calls(cc, calls) == [[cc.OPEN, cc.URI.format(sid="sid-123")]]

    calls.clear()
    cc.cmd_launch(_launch_ns(card))            # relaunch: VS Code restores it
    assert _open_calls(cc, calls) == []        # no URI → no duplicate
    assert any(a[0] == cc.CODE for a in calls)  # but the window still opens


def test_launch_marks_the_workspace_as_launched(cc, tmp_path, monkeypatch):
    card, _ = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "My Card — my-card (Workspace)", "focused": True}])
    ws = tmp_path / "ws.code-workspace"
    assert not cc.workspace_launched_before(ws)
    cc.cmd_launch(_launch_ns(card))
    assert cc.workspace_launched_before(ws)


def test_launch_resume_forces_the_uri_after_a_relaunch(cc, tmp_path, monkeypatch):
    """The escape hatch for when restore brought nothing back (tabs closed, state cleared).
    It must work in-editor — the previous answer was a terminal `claude --resume`, which is
    the friction this whole change exists to remove."""
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "My Card — my-card (Workspace)", "focused": True}])
    cc.cmd_launch(_launch_ns(card))
    calls.clear()

    cc.cmd_launch(_launch_ns(card, resume=True))
    assert _open_calls(cc, calls) == [[cc.OPEN, cc.URI.format(sid="sid-123")]]


def test_launch_new_still_fires_even_on_a_relaunch(cc, tmp_path, monkeypatch):
    """`--new` has nothing to restore by definition, so it is unaffected by the change."""
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "My Card — my-card (Workspace)", "focused": True}])
    cc.cmd_launch(_launch_ns(card))
    calls.clear()

    cc.cmd_launch(_launch_ns(card, new=True))
    assert _open_calls(cc, calls) == [[cc.OPEN, cc.URI_NEW]]


def test_relaunch_skips_the_window_poll_entirely(cc, tmp_path, monkeypatch):
    """Polling for the frontmost window existed only to make the URI land in the right
    place. With no URI to fire there is nothing to protect, so a relaunch must not consult
    Hammerspoon at all — which also removes the wrong-window race (A1.2) from the common
    path, not just mitigate it."""
    card, calls = _launch_rig(cc, tmp_path, monkeypatch)
    monkeypatch.setattr(cc, "hs_code_windows", lambda: [
        {"id": 1, "title": "My Card — my-card (Workspace)", "focused": True}])
    cc.cmd_launch(_launch_ns(card))

    def boom():
        raise AssertionError("hs must not be consulted when no URI will be fired")
    monkeypatch.setattr(cc, "hs_code_windows", boom)
    cc.cmd_launch(_launch_ns(card))            # no exception → never polled


def test_launch_delay_default_matches_docs(cc):
    # The argparse default and the cardctl.md launch doc must agree (#23 reconcile).
    root = Path(cc.__file__).resolve().parent
    m = re.search(r'"--delay",\s*type=float,\s*default=([\d.]+)',
                  (root / "cardctl").read_text())
    assert m, "couldn't find the --delay default in cardctl"
    assert f"default {float(m.group(1)):g}" in (root / "cardctl.md").read_text()


# ── set: the metadata writer ────────────────────────────────────────────────────
def _set_ns(card, **kw):
    base = dict(card=card, summary=None, latest=None, area=None, add_area=None, program=None,
                strict=False,
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


def test_cmd_set_summary_writes_the_field(cc, tmp_path, monkeypatch):
    """Closes the last hand-edit gap for `summary` (there was no writer at all)."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    card.write_text(card.read_text().replace("status: in-progress",
                                             'status: in-progress\nsummary: ""'))
    cc.cmd_set(_set_ns(str(card), summary="What this card is about"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["summary"]) == "What this card is about"


def test_cmd_set_summary_inserts_when_field_absent(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")                      # make_card writes no summary line
    cc.cmd_set(_set_ns(str(card), summary="Added later"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["summary"]) == "Added later"


@pytest.mark.parametrize("summary", [
    "White paper: data sources",       # colon — the cmd_new bug, same class
    "Costs #hash and 'quotes'",
    "",                                # explicit clear
])
def test_cmd_set_summary_is_quoted_so_prose_stays_valid_yaml(cc, tmp_path, monkeypatch, summary):
    yaml = pytest.importorskip("yaml")
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    cc.cmd_set(_set_ns(str(card), summary=summary))
    fm_block = card.read_text().split("---\n")[1]
    assert yaml.safe_load(fm_block)["summary"] == summary


def test_cmd_set_latest_writes_the_glance_line(cc, tmp_path, monkeypatch):
    """The last hand-edit exception in a single-writer system (A3.1). Unblocked once the
    convention was settled: `latest` is Steve's line, the AI's next step lives in the
    activity folder's HANDOFF.md."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    card.write_text(card.read_text().replace("status: in-progress",
                                             'status: in-progress\nlatest: ""'))
    cc.cmd_set(_set_ns(str(card), latest="Waiting on the SCE review"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["latest"]) == "Waiting on the SCE review"


def test_cmd_set_latest_inserts_when_field_absent(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")                      # make_card writes no latest line
    cc.cmd_set(_set_ns(str(card), latest="Added later"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["latest"]) == "Added later"


@pytest.mark.parametrize("latest", [
    "Shipped #64: no more duplicate sessions",   # colon + hash, the cmd_new bug class
    "Waiting on Kim's 'go ahead'",
    "",                                          # explicit clear
])
def test_cmd_set_latest_is_quoted_so_prose_stays_valid_yaml(cc, tmp_path, monkeypatch, latest):
    yaml = pytest.importorskip("yaml")
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    cc.cmd_set(_set_ns(str(card), latest=latest))
    fm_block = card.read_text().split("---\n")[1]
    assert yaml.safe_load(fm_block)["latest"] == latest


def test_cmd_set_latest_and_summary_are_independent(cc, tmp_path, monkeypatch):
    """Two different jobs on one card: what this *is* vs where it *stands*."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    cc.cmd_set(_set_ns(str(card), summary="What this is"))
    cc.cmd_set(_set_ns(str(card), latest="Where it stands"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["summary"]) == "What this is"
    assert cc.unquote(fm["latest"]) == "Where it stands"

    cc.cmd_set(_set_ns(str(card), latest="Moved on"))          # updating one leaves the other
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["summary"]) == "What this is"
    assert cc.unquote(fm["latest"]) == "Moved on"


def test_cmd_set_without_latest_leaves_it_alone(cc, tmp_path, monkeypatch):
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    card.write_text(card.read_text().replace("status: in-progress",
                                             'status: in-progress\nlatest: "keep me"'))
    cc.cmd_set(_set_ns(str(card), area="tools"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["latest"]) == "keep me"


def test_cmd_set_without_summary_leaves_it_alone(cc, tmp_path, monkeypatch):
    """`--summary` omitted must not blank an existing summary (None vs '' matters)."""
    cards = tmp_path / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"t": cards})
    card = make_card(cards, "c")
    card.write_text(card.read_text().replace("status: in-progress",
                                             'status: in-progress\nsummary: "keep me"'))
    cc.cmd_set(_set_ns(str(card), area="tools"))
    fm, _ = cc.read_card(str(card))
    assert cc.unquote(fm["summary"]) == "keep me"


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


def test_set_paths_in_text_drops_empty_placeholder(cc):
    doc = "---\ntitle: X\npaths:\n  - \n---\nbody\n"  # cmd_new's empty placeholder
    out = cc.set_paths_in_text(doc, ["/a/b"])
    assert out == "---\ntitle: X\npaths:\n  - /a/b\n---\nbody\n"


# ── writer round-trip (consolidated _edit_frontmatter, #22) ──────────────────────
def test_writer_roundtrip_preserves_foreign_fields_and_order(cc):
    doc = ('---\n'
           'type: project\n'
           'title: "T: with # both specials"\n'
           'status: backlog\n'
           'tags: [area/tools]\n'
           'program: "[[eng-arch]]"\n'
           'paths:\n'
           '  - /a/b\n'
           'sessionId: abc-123\n'
           '---\n'
           '\n## Sessions\n\n- one\n')
    out = cc.set_status_in_text(doc, "done")
    out = cc.set_tags_in_text(out, ["area/v7", "kind/geo"])
    out = cc.set_paths_in_text(out, ["/c/d", "/e/f"])
    out = cc.set_fm_field(out, "sessionId", "def-456")
    # everything else byte-for-byte, key order and quoting intact
    assert out == ('---\n'
                   'type: project\n'
                   'title: "T: with # both specials"\n'
                   'status: done\n'
                   'tags: [area/v7, kind/geo]\n'
                   'program: "[[eng-arch]]"\n'
                   'paths:\n'
                   '  - /c/d\n'
                   '  - /e/f\n'
                   'sessionId: def-456\n'
                   '---\n'
                   '\n## Sessions\n\n- one\n')
    # and it re-parses to the edited values
    fm = cc.parse_fm(out.split("---", 2)[1])
    assert (fm["status"], fm["tags"], fm["paths"], fm["sessionId"]) == \
        ("done", ["area/v7", "kind/geo"], ["/c/d", "/e/f"], "def-456")


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
    make_card(cards, "noarea")  # no tags → NO-AREA
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


def test_lint_card_stem_collision_across_domains(cc, tmp_path, monkeypatch, capsys):
    work = tmp_path / "work-vault" / "Cards"
    personal = tmp_path / "personal-vault" / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": work, "personal": personal})
    make_card(work, "dup")
    make_card(personal, "dup")
    make_card(work, "unique")
    cc.cmd_lint(_lint_ns())
    fs = [f for f in json.loads(capsys.readouterr().out)
          if f["code"] == "CARD-STEM-COLLISION"]
    assert len(fs) == 1 and fs[0]["severity"] == "error"
    d = fs[0]["detail"]
    assert "'dup'" in d and "work" in d and "personal" in d
    assert "'unique'" not in d


def test_lint_no_card_stem_collision_when_stems_distinct(cc, tmp_path, monkeypatch, capsys):
    work = tmp_path / "work-vault" / "Cards"
    personal = tmp_path / "personal-vault" / "Cards"
    monkeypatch.setattr(cc, "CARDS_DIRS", {"work": work, "personal": personal})
    make_card(work, "one")
    make_card(personal, "two")
    found = _findings(cc, tmp_path, capsys)
    assert not any(code == "CARD-STEM-COLLISION" for code, _ in found)


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
