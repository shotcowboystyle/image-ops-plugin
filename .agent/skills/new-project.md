# New Image Project

Scaffold a project folder inside the registered image workspace.

## Procedure

### 1. Resolve the workspace

```bash
CONFIG="${CLAUDE_USER_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/claude-plugins}/image-ops/workspace.json"
test -f "$CONFIG" || { echo "No workspace registered — run workspace-setup first."; exit 1; }
# jq is the happy path. The fallback must be portable: `grep -oP` is GNU-only and
# errors out on macOS's BSD grep — the very case the fallback covers.
WS=$(jq -r .path "$CONFIG" 2>/dev/null) \
  || WS=$(sed -n 's/.*"path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG")
test -d "$WS" || { echo "Workspace path missing: $WS — run workspace-setup."; exit 1; }
```

### 2. Ask for project metadata

- **Name** — required. Slugify (lowercase, hyphens for spaces).
- **Version control** — ask; default **no**.

### 3. Create the layout

```bash
PROJ="$WS/$slug"
test -e "$PROJ" && { echo "Already exists: $PROJ"; exit 1; }
mkdir -p "$PROJ"/{source,working,exports,references,thumbnails} \
  || { echo "Could not create $PROJ — check permissions on $WS"; exit 1; }
```

| Folder         | Purpose                                                    |
|----------------|------------------------------------------------------------|
| `source/`      | Original images — never edited in place                    |
| `working/`     | In-progress edits, layered files (PSD, XCF, AFPHOTO)       |
| `exports/`     | Final deliverables (web JPEG/WebP, print TIFF, etc.)       |
| `references/`  | Mood boards, reference images, prompts                     |
| `thumbnails/`  | Small previews for indexing                                |

Write a `README.md` in the project root with the slug, the ISO date from `date +%Y-%m-%d`, and a notes section.

### 4. (Optional) git init

If the user wants version control, run `git init "$PROJ"` and add a `.gitignore` excluding `source/` and `exports/` if they're large. Nothing else in this skill touches git — do not commit, add a remote, or push.

### 5. Confirm

Print the project path. Offer to `cd` or open in a terminal.
