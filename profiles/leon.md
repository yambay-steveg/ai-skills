do you have access to the # Leon's Skills
2
## Source

- SharePoint site: `ClaudeCodeSetup`
- Path: `Shared Documents/Skills for Claude/`
- Installation guide: `How-to-Install-Skills.pdf` (v1.2, 2026-03-09)

## Skills

### md-to-word (v1.9)

**Purpose:** Convert Markdown files to professionally styled Word documents (.docx) using customisable templates and pandoc.

**Key features:**
- YAML front matter for document metadata (title, type, issue date, revision)
- Template system with memo and legal templates (plus support for private templates)
- Auto-numbered headings (legal template)
- Cross-reference support (`{ref:id}` markers become Word REF fields)
- Content table styling (Yambay Standard style)
- Custom paragraph styles via pandoc fenced divs

**Dependencies:** python-docx, pyyaml, lxml, pandoc (Homebrew)

**Install path:** `~/.claude/skills/md-to-word/`

**Triggers:** User asks to convert markdown to Word, create a Word doc, export to docx, generate a styled document.

---

### files (v1.4)

**Purpose:** Unified file access across local storage, OneDrive sync, and SharePoint/Teams via Microsoft Graph API.

**Key features:**
- Multi-tier search: local filesystem, OneDrive sync folders, then cloud (Graph API)
- Download files from SharePoint URLs
- Upload files to SharePoint
- List SharePoint folder contents
- Parse Teams/SharePoint URLs to extract site and drive info
- User-specific config for paths, team IDs, and known sites

**Dependencies:** msal, requests, python-dotenv

**Install path:** `~/.claude/skills/files/`

**Config required:** `config/paths.json`, `config/teams.json`, `config/sites.json` (copy from `template/config/`)

**Triggers:** User asks to find/download/upload files, lists folder contents, pastes a Teams or SharePoint URL.

---

### email (v1.5)

**Purpose:** Search, compose, and reply to M365 email via Microsoft Graph API.

**Key features:**
- KQL-based email search (from, subject, date range, attachments)
- Attachment download
- Draft creation (HTML format, appears in Outlook Drafts)
- Reply and reply-all with quoted original message preserved
- Admin detection (auto-switches to admin app for Global Admins)
- Batch email support

**Dependencies:** msal, requests, python-dotenv

**Install path:** `~/.claude/skills/email/`

**Triggers:** User asks to find/search email, draft/compose email, reply to email.

## Testing Status

| Skill | Installed | Deps OK | Auth Tested | Functional Test |
|-------|-----------|---------|-------------|-----------------|
| md-to-word | Yes | Yes | N/A | Pending |
| files | Yes | Yes | Pass | Pending |
| email | Yes | Yes | Pass | Pass (search) |
