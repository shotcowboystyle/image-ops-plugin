#!/usr/bin/env python3
"""Generate the Claude Code layer from the portable `.agent/` source of truth.

`.agent/` is hand-edited and tool-neutral. Everything this script writes is
derived from it and must never be edited directly:

    AGENTS.md                     agent definition, skill bodies, command bodies
    skills/<name>/SKILL.md        YAML frontmatter + verbatim body
    commands/<name>.md            frontmatter + body
    .claude-plugin/plugin.json    plugin meta + explicit component arrays
    README.md                     the block between the generated markers

A command comes from one of two places:

    - a skill that declares a `command` block, generating a thin wrapper that
      invokes the skill; or
    - a standalone entry in the manifest's `commands` array, whose body lives at
      `.agent/commands/<name>.md`. Use this when the command carries its own
      prompt rather than delegating to a skill.

Run from the plugin root:

    python3 scripts/build.py            # write
    python3 scripts/build.py --check    # exit 1 if anything on disk is stale
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / ".agent"
MANIFEST = AGENT_DIR / "manifest.json"
AGENT_MD = AGENT_DIR / "agent.md"
SKILL_SRC = AGENT_DIR / "skills"
COMMAND_SRC = AGENT_DIR / "commands"

BEGIN = "<!-- BEGIN GENERATED: components -->"
END = "<!-- END GENERATED: components -->"

BANNER = (
    "<!-- GENERATED FILE — do not edit. Source: .agent/  "
    "Regenerate: python3 scripts/build.py -->"
)


# --------------------------------------------------------------------------
# load
# --------------------------------------------------------------------------

def load():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    plugin = data["plugin"]
    skills = data.get("skills", [])
    commands = data.get("commands", [])

    seen = set()
    for s in skills:
        name = s["name"]
        if name in seen:
            sys.exit(f"error: duplicate skill name: {name}")
        seen.add(name)
        body = SKILL_SRC / f"{name}.md"
        if not body.is_file():
            sys.exit(f"error: manifest lists '{name}' but {body.relative_to(ROOT)} is missing")
        for field in ("summary", "tools"):
            if not s.get(field):
                sys.exit(f"error: skill '{name}' is missing required field '{field}'")
        s["body"] = body.read_text(encoding="utf-8").strip()

    orphans = sorted(p.stem for p in SKILL_SRC.glob("*.md") if p.stem not in seen)
    if orphans:
        sys.exit("error: skill bodies with no manifest entry: " + ", ".join(orphans))

    cmd_seen = set()
    for c in commands:
        name = c["name"]
        if name in cmd_seen:
            sys.exit(f"error: duplicate command name: {name}")
        cmd_seen.add(name)
        if not c.get("description"):
            sys.exit(f"error: command '{name}' is missing required field 'description'")
        body = COMMAND_SRC / f"{name}.md"
        if not body.is_file():
            sys.exit(
                f"error: manifest lists command '{name}' but "
                f"{body.relative_to(ROOT)} is missing"
            )
        c["body"] = body.read_text(encoding="utf-8").strip()

    if COMMAND_SRC.is_dir():
        stray = sorted(p.stem for p in COMMAND_SRC.glob("*.md") if p.stem not in cmd_seen)
        if stray:
            sys.exit("error: command bodies with no manifest entry: " + ", ".join(stray))

    for s in skills:
        if s.get("command"):
            name = s["command"]["name"]
            if name in cmd_seen:
                sys.exit(
                    f"error: command '{name}' is declared both by skill "
                    f"'{s['name']}' and as a standalone command"
                )
            cmd_seen.add(name)

    return plugin, skills, commands


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def yaml_scalar(text):
    """Render a string as a YAML value, quoting only when it has to be quoted.

    A colon followed by a space, a leading indicator character, or leading and
    trailing whitespace all change how a plain scalar parses. JSON string syntax
    is a valid YAML double-quoted scalar, so it is used for the quoted form.
    """
    needs_quotes = (
        ": " in text
        or text.endswith(":")
        or text[:1] in "-?:,[]{}#&*!|>'\"%@`"
        or text != text.strip()
        or "\n" in text
    )
    return json.dumps(text, ensure_ascii=False) if needs_quotes else text


def description(skill):
    """Assemble the skill description shown to the model.

    `<summary>` on its own, or `<summary> Triggers - "a", "b".` when the skill
    declares triggers. The trailing clause uses a hyphen rather than a colon so
    the value stays a plain YAML scalar.
    """
    summary = skill["summary"].rstrip()
    triggers = skill.get("triggers") or []
    if not triggers:
        return summary
    if not summary.endswith("."):
        summary += "."
    quoted = ", ".join(f'"{t}"' for t in triggers)
    return f"{summary} Triggers - {quoted}."


def demote(markdown, levels):
    """Shift ATX headings deeper by `levels`, leaving fenced code blocks alone.

    Skill and command bodies are authored to stand alone, so they open at `#`.
    When they are inlined under a heading in AGENTS.md they have to sit below it.
    """
    out = []
    fence = None
    for line in markdown.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            out.append(line)
            continue
        if fence is None and stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            rest = stripped[hashes:]
            if rest.startswith(" ") or rest == "":
                out.append("#" * min(hashes + levels, 6) + rest)
                continue
        out.append(line)
    return "\n".join(out)


def split_title(body):
    """Return (title, body-without-its-leading-H1).

    Bodies open with their own H1 so they read standalone. AGENTS.md emits that
    title as the section heading instead, so the duplicate has to go.
    """
    lines = body.split("\n")
    if lines and lines[0].startswith("# "):
        rest = lines[1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        return lines[0][2:].strip(), "\n".join(rest)
    return None, body


def skill_md(skill):
    return "\n".join([
        "---",
        f"name: {skill['name']}",
        f"description: {yaml_scalar(description(skill))}",
        f"disable-model-invocation: {str(bool(skill.get('disableModelInvocation'))).lower()}",
        f"allowed-tools: {', '.join(skill['tools'])}",
        "---",
        "",
        skill["body"],
        "",
    ])


def command_frontmatter(cmd):
    lines = ["---", f"description: {yaml_scalar(cmd['description'])}"]
    if cmd.get("argumentHint"):
        lines.append(f"argument-hint: {yaml_scalar(cmd['argumentHint'])}")
    if cmd.get("tools"):
        lines.append(f"allowed-tools: {', '.join(cmd['tools'])}")
    lines.append("---")
    return lines


def skill_command_md(skill):
    cmd = skill["command"]
    body = cmd.get("body", "").strip() or "Arguments, if any, arrive in $ARGUMENTS."
    return "\n".join(
        command_frontmatter(cmd)
        + ["", f"Invoke the `{skill['name']}` skill.", "", body, ""]
    )


def standalone_command_md(cmd):
    return "\n".join(command_frontmatter(cmd) + ["", cmd["body"], ""])


def command_index(skills, commands):
    """Every command as (name, description, argumentHint), in a stable order."""
    out = [
        (s["command"]["name"], s["command"]["description"], s["command"].get("argumentHint"))
        for s in skills if s.get("command")
    ]
    out += [(c["name"], c["description"], c.get("argumentHint")) for c in commands]
    return sorted(out, key=lambda c: c[0])


def plugin_json(plugin, skills, commands):
    out = {
        "name": plugin["name"],
        "description": plugin["description"],
        "version": plugin["version"],
        "author": plugin["author"],
        "license": plugin["license"],
        "repository": plugin["repository"],
        "commands": [f"./commands/{c[0]}.md" for c in command_index(skills, commands)],
        "skills": [f"./skills/{s['name']}/" for s in skills],
        "keywords": plugin["keywords"],
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def agents_md(plugin, skills, commands):
    parts = [
        BANNER,
        "",
        AGENT_MD.read_text(encoding="utf-8").strip(),
        "",
        "## Skills",
        "",
        "Each skill below is a self-contained capability. Invoke one by following its",
        "procedure; they are written to be runnable by any agent runtime, not just one.",
        "",
    ]
    for s in skills:
        title, body = split_title(s["body"])
        parts += [
            f"### {title or s['name']}",
            "",
            f"**Name.** `{s['name']}`",
            "",
            f"**When to use.** {s['summary'].rstrip()}",
            "",
        ]
        if s.get("triggers"):
            parts += [f"**Triggers.** {', '.join(s['triggers'])}", ""]
        if s.get("requires"):
            parts += [f"**Requires.** `{'`, `'.join(s['requires'])}`", ""]
        parts += [demote(body, 2), "", "---", ""]

    if commands:
        parts += [
            "## Commands",
            "",
            "These carry their own instructions rather than delegating to a skill. A",
            "runtime without slash commands can run one by following its body directly.",
            "",
        ]
        for c in commands:
            title, body = split_title(c["body"])
            parts += [
                f"### {title or c['name']}",
                "",
                f"**Name.** `{c['name']}`",
                "",
                f"**What it does.** {c['description'].rstrip()}",
                "",
            ]
            if c.get("argumentHint"):
                parts += [f"**Arguments.** `{c['argumentHint']}`", ""]
            parts += [demote(body, 2), "", "---", ""]

    return "\n".join(parts).rstrip() + "\n"


def readme_block(plugin, skills, commands):
    lines = [BEGIN, "", "## Commands", ""]
    for name, desc, hint in command_index(skills, commands):
        suffix = f" {hint}" if hint else ""
        lines.append(f"- `/{plugin['name']}:{name}{suffix}` — {desc}")
    lines += ["", "## Skills", ""]
    for s in skills:
        lines.append(f"- **{s['name']}** — {s['summary'].rstrip()}")
    lines += ["", END]
    return "\n".join(lines)


def render(plugin, skills, commands):
    """Return {relative path: content} for every generated file."""
    files = {
        "AGENTS.md": agents_md(plugin, skills, commands),
        ".claude-plugin/plugin.json": plugin_json(plugin, skills, commands),
    }
    for s in skills:
        files[f"skills/{s['name']}/SKILL.md"] = skill_md(s)
        if s.get("command"):
            files[f"commands/{s['command']['name']}.md"] = skill_command_md(s)
    for c in commands:
        files[f"commands/{c['name']}.md"] = standalone_command_md(c)

    readme = ROOT / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            files["README.md"] = head + readme_block(plugin, skills, commands) + tail
        else:
            sys.exit(
                f"error: README.md is missing the generated markers.\n"
                f"  Add these two lines where the component index belongs:\n"
                f"    {BEGIN}\n    {END}"
            )
    return files


# --------------------------------------------------------------------------
# write / check
# --------------------------------------------------------------------------

def stale_paths(skills, commands):
    """Generated skill and command files that no longer have a manifest entry."""
    keep_skills = {s["name"] for s in skills}
    keep_cmds = {c[0] for c in command_index(skills, commands)}
    stale = []
    for d in sorted((ROOT / "skills").glob("*")):
        if d.is_dir() and d.name not in keep_skills:
            stale.append(d)
    for f in sorted((ROOT / "commands").glob("*.md")):
        if f.stem not in keep_cmds:
            stale.append(f)
    return stale


def main():
    check = "--check" in sys.argv[1:]
    plugin, skills, commands = load()
    files = render(plugin, skills, commands)

    drift = []
    for rel, content in sorted(files.items()):
        path = ROOT / rel
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        drift.append(rel)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    for path in stale_paths(skills, commands):
        drift.append(str(path.relative_to(ROOT)) + " (stale)")
        if not check:
            shutil.rmtree(path) if path.is_dir() else path.unlink()

    if check:
        if drift:
            print("stale generated files:", file=sys.stderr)
            for d in drift:
                print(f"  {d}", file=sys.stderr)
            print("\nrun: python3 scripts/build.py", file=sys.stderr)
            return 1
        print(f"up to date — {len(files)} generated files match .agent/")
        return 0

    if drift:
        print(f"wrote {len(drift)} file(s):")
        for d in drift:
            print(f"  {d}")
    else:
        print("nothing to do — already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
