# wellformed

**Invariant-preserving documents for agents that modify persistent state.**

A chat reply is ephemeral; a config file your agent just rewrote is not.
`wellformed` gives LLM agents three composable primitives for editing
structured documents reliably:

- `ValidatedDocument` — a document that is always well-formed and
  schema-valid by construction.
- `FixingLoop` — validate → repair → re-validate, format-agnostic and
  LLM-agnostic.
- `Checkpoint` — atomic rollback at file, multi-file, or directory
  granularity.

The core is pure Python with zero runtime dependencies. Formats are
added via plugins. XML and JSON ship today; the plugin API is public
and compact, so adding a new format is a short afternoon's work — see
[Writing a plugin](#writing-a-plugin) below.

## Installation

```bash
pip install wellformed              # core only
pip install wellformed[xml]         # with XML plugin (installs lxml)
pip install wellformed[json]        # with JSON plugin (installs jsonschema)
```

Requires Python 3.11 or newer.

## The 30-second quickstart (XML)

```python
from pathlib import Path
from wellformed import DocumentMutation, MutationFailedError
from wellformed.xml import XMLValidatedDocument, make_xml_schema_validator

XSD = make_xml_schema_validator(Path("schemas/note.xsd"))


class Note(XMLValidatedDocument):
    @classmethod
    def _validate_schema(cls, content):
        return XSD(content)

    @classmethod
    def _get_document_type(cls):
        return "note"

    @classmethod
    async def _repair(cls, content, errors, document_type):
        # Call your LLM of choice here. See "BYO LLM" below.
        ...


class AppendLine(DocumentMutation):
    async def execute(self, content, parsed):
        from lxml import etree
        child = etree.SubElement(parsed, "line")
        child.text = "added by the agent"
        return etree.tostring(parsed, encoding="unicode")


doc = await Note.load(Path("note.xml"))
checkpoint = doc.checkpoint()
try:
    new_doc = await doc.apply(AppendLine(name="append"))
    new_doc.save()
    checkpoint.discard()
except MutationFailedError:
    checkpoint.restore()
    raise
```

The fixing loop only runs when the mutation produces invalid content. If
the mutation is already valid, no LLM call is made. If the mutation
produces invalid content and the repair succeeds, the repaired content
is written. If repair fails, `MutationFailedError` is raised and your
code can roll back via the checkpoint.

## The 30-second quickstart (JSON)

The JSON plugin mirrors the XML one: same three hooks, same
`load` / `apply` / `checkpoint` flow. JSON parsing uses the stdlib
`json` module; schema validation uses
[jsonschema](https://python-jsonschema.readthedocs.io/) against the
2020-12 draft.

Given a minimal JSON Schema on disk at `schemas/note.schema.json`:

```json
{
  "type": "object",
  "required": ["type", "lines"],
  "properties": {
    "type": {"const": "note"},
    "lines": {"type": "array", "items": {"type": "string"}}
  }
}
```

```python
import json
from pathlib import Path
from wellformed import DocumentMutation, MutationFailedError
from wellformed.json import JSONValidatedDocument, make_json_schema_validator

SCHEMA = make_json_schema_validator(Path("schemas/note.schema.json"))


class Note(JSONValidatedDocument):
    @classmethod
    def _validate_schema(cls, content):
        return SCHEMA(content)

    @classmethod
    def _get_document_type(cls):
        return "note"

    @classmethod
    async def _repair(cls, content, errors, document_type):
        # Call your LLM of choice here. See "BYO LLM" below.
        ...


class AppendLine(DocumentMutation):
    async def execute(self, content, parsed):
        parsed["lines"].append("added by the agent")
        return json.dumps(parsed)


doc = await Note.load(Path("note.json"))
checkpoint = doc.checkpoint()
try:
    new_doc = await doc.apply(AppendLine(name="append"))
    new_doc.save()
    checkpoint.discard()
except MutationFailedError:
    checkpoint.restore()
    raise
```

The `parsed` argument passed to `execute` is the `json.loads` output
— a `dict` or `list`. Mutate it in place and return the re-serialized
string, exactly like the XML example returns `etree.tostring(parsed)`.

## Core concepts

**ValidatedDocument** — an always-valid wrapper. Once you hold an
instance, the content has passed parsing and schema validation. There
is no `.is_valid()` to forget to call.

**FixingLoop** — runs your `validate_fn` and `repair_fn` in a retry
loop with structured reporting (`SUCCESS` / `ALREADY_VALID` / `FAILED`
plus attempt count and remaining errors). The repair function is a
protocol — you bring your own implementation.

**Checkpoint** — captures the pre-mutation content so you can roll
back on failure. Three granularities:

- `Checkpoint` — single file.
- `MultiFileCheckpoint` — several files, restored in LIFO order.
- `DirectoryCheckpoint` — whole directory copied via `shutil`.

## Multi-file and directory checkpoints

The quickstarts above use `Checkpoint` — single file, one document.
Two related types cover the cases where one file is not enough.

### `MultiFileCheckpoint` — several files, atomically

When an agent edits two or more documents that must succeed together,
bundle their checkpoints under a `MultiFileCheckpoint`. If any
mutation in the group fails, `restore()` reverts every file whose
checkpoint is still active — in LIFO order, so edits are undone in
the reverse of the order they were applied.

```python
from wellformed import MultiFileCheckpoint

note_a = await Note.load(Path("team-a.note.json"))
note_b = await Note.load(Path("team-b.note.json"))

multi = MultiFileCheckpoint()
multi.add(note_a.checkpoint())
multi.add(note_b.checkpoint())

try:
    new_a = await note_a.apply(AppendLine(name="append-a"))
    new_a.save()
    new_b = await note_b.apply(AppendLine(name="append-b"))
    new_b.save()
    multi.discard()
except MutationFailedError:
    multi.restore()
    raise
```

If the second `apply()` fails, `multi.restore()` reverts
`team-a.note.json` (already saved) and leaves `team-b.note.json`
untouched (its checkpoint rewrites identical content). You never need
to reason about which files made it to disk and which did not.

### `DirectoryCheckpoint` — entire directory, including creates and deletes

Per-file checkpoints cannot cover files that did not exist when the
checkpoint was taken, or files the agent deletes. When an operation
regenerates a directory — rewriting some files, removing others,
adding new ones — snapshot the whole directory instead.
`DirectoryCheckpoint.create` copies the directory via
`shutil.copytree`; `restore()` removes the current directory and
moves the backup back into place.

```python
from wellformed import DirectoryCheckpoint

notes_dir = Path("notes/")
checkpoint = DirectoryCheckpoint.create(notes_dir)

try:
    await regenerate_notes(notes_dir)  # may add, modify, or delete files
    checkpoint.discard()                # on success: backup is removed
except MutationFailedError:
    checkpoint.restore()                # on failure: directory is restored
    raise
```

The trade-off is disk cost: `copytree` duplicates the directory for
the lifetime of the checkpoint, so this is best suited to
small-to-moderate trees. For large repositories, prefer a
`MultiFileCheckpoint` over the specific files you know you will
touch.

## An extended example: iterative repair and rollback

The quickstart is deliberately minimal. Here's a fuller example that
shows two behaviours in action:

1. **The fixing loop iterates.** A single repair attempt often fixes
   one error but leaves another — or introduces a fresh defect. The
   loop retries up to `max_fix_attempts` times, passing the latest
   errors to `_repair` on each round.
2. **Checkpoints roll back to the last known-good state** when a
   mutation can't be repaired. Successful edits are preserved; only
   the failing one is reverted.

The document is a small XML todo list. Each `<task>` has a required
`priority` attribute from `{low, medium, high}` and a `<title>` child.
We run two mutations against it: one produces an out-of-enum priority
(recoverable; demonstrates iterative repair) and one strips every
title (unrecoverable; demonstrates rollback).

Assume two files on disk alongside the script.

`todos.xsd` — the schema:

```xml
<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="todos">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="task" minOccurs="0" maxOccurs="unbounded">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="title" type="xs:string"/>
            </xs:sequence>
            <xs:attribute name="priority" use="required">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:enumeration value="low"/>
                  <xs:enumeration value="medium"/>
                  <xs:enumeration value="high"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:attribute>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

`todos.xml` — the initial document:

```xml
<todos>
  <task priority="high"><title>Ship wellformed v0.1</title></task>
  <task priority="medium"><title>Write the tutorial</title></task>
</todos>
```

And the Python:

```python
from pathlib import Path
from lxml import etree
from wellformed import DocumentMutation, MutationFailedError
from wellformed.xml import XMLValidatedDocument, make_xml_schema_validator

VALID_PRIORITIES = {"low", "medium", "high"}
XSD = make_xml_schema_validator(Path("todos.xsd"))


class TodoList(XMLValidatedDocument):
    """A validated XML todo-list document.

    By inheriting from XMLValidatedDocument, we get XML parsing for
    free (via the `_parse` method provided by the XML plugin). The
    base class's invariant propagates: once you hold a TodoList
    instance, its content is guaranteed to be well-formed XML that
    passes our XSD schema. Invalid content simply cannot be
    represented by this class — any operation that would produce it
    either repairs it or raises.

    The three hooks below are everything the library needs from us
    to extend the XML plugin into a concrete document type.
    """

    @classmethod
    def _validate_schema(cls, content):
        return XSD(content)

    @classmethod
    def _get_document_type(cls):
        return "todo-list"

    @classmethod
    async def _repair(cls, content, errors, document_type):
        """Naive two-pass repair strategy.

        A production implementation would typically delegate repair
        to an LLM. To keep this example runnable without network
        calls, we inspect content directly and apply deterministic
        fixes instead.

        Note two unused arguments:

        - `errors`: the list of validation messages produced by the
          last validation pass. An LLM-based repair would weave
          these into its prompt so the model knows what's wrong. A
          deterministic repair that inspects content directly — as
          this one does — can usually infer the needed fix without
          reading the error list.

        - `document_type`: the string returned by
          `_get_document_type` above. Useful as a prompt label
          ("Fix this todo-list: ...") or for dispatching when a
          single `_repair` function serves several document classes.
          We only have one document type here, so we don't need it.
        """
        try:
            root = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError:
            # If the content isn't parseable at all, we can't help
            # at this layer. Return unchanged; the fixing loop will
            # report a parse error on the next validation pass.
            return content

        # --- Strategy A: quarantine invalid priority values. ---
        # If a `priority` attribute holds a value outside the enum
        # (e.g. "High" with a capital H), move that value to a
        # non-schema `prio` attribute and drop `priority`.
        #
        # This CLEARS the enum-violation error but INTRODUCES a new
        # one: the task is now missing its required `priority`
        # attribute. That's deliberate — the fixing loop will re-run
        # us with the new errors, and Strategy B will then recover.
        bad_priority_tasks = [
            t for t in root.iter("task")
            if t.get("priority") is not None
            and t.get("priority") not in VALID_PRIORITIES
        ]
        if bad_priority_tasks:
            for t in bad_priority_tasks:
                t.set("prio", t.get("priority"))
                del t.attrib["priority"]
            return etree.tostring(root, encoding="unicode")

        # --- Strategy B: reinstate priority from the stash. ---
        # If a task lacks `priority`, look for a stashed value in
        # `prio`. Lowercase it; if the result is a valid enum
        # member, use it. Otherwise fall back to "medium". Either
        # way, drop the temporary `prio` attribute so the document
        # conforms to the schema again.
        missing_priority_tasks = [
            t for t in root.iter("task") if t.get("priority") is None
        ]
        if missing_priority_tasks:
            for t in missing_priority_tasks:
                stashed = t.get("prio", "")
                candidate = stashed.lower() if stashed else "medium"
                if candidate not in VALID_PRIORITIES:
                    candidate = "medium"
                t.set("priority", candidate)
                if "prio" in t.attrib:
                    del t.attrib["prio"]
            return etree.tostring(root, encoding="unicode")

        # Neither strategy applies. Returning content unchanged
        # makes the next validation pass report the same errors, so
        # the fixing loop will exhaust its attempts and raise.
        return content


# DocumentMutation subclasses describe *what* to change, not *how*
# to validate or repair. Each mutation's `execute` method is an
# async callable that receives the current content plus its parsed
# form (an lxml tree, here) and returns new content.
#
# Users write mutations naively — "just do the thing". `apply()`
# wraps every mutation in the fixing loop: if the produced content
# fails schema validation, `_repair` runs up to `max_fix_attempts`
# times before `apply()` raises `MutationFailedError`. This
# separation keeps each mutation focused on intent; the document
# class handles "make it valid again" on its behalf.

class BulkReprioritise(DocumentMutation):
    """Set every task's priority to `value`.

    When `value` is outside the enum (e.g. "High" capitalised), the
    resulting content fails validation and triggers the fixing loop.
    """

    def __init__(self, value: str):
        super().__init__(name=f"bulk-reprioritise-{value}")
        self.value = value

    async def execute(self, content, parsed):
        for task in parsed.iter("task"):
            task.set("priority", self.value)
        return etree.tostring(parsed, encoding="unicode")


class PurgeTitles(DocumentMutation):
    """Remove every <title>. Unrecoverable: the repair function has
    no way to invent task titles, so the fixing loop will exhaust
    its attempts."""

    def __init__(self):
        super().__init__(name="purge-titles")

    async def execute(self, content, parsed):
        for title in list(parsed.iter("title")):
            title.getparent().remove(title)
        return etree.tostring(parsed, encoding="unicode")


async def main():
    doc = await TodoList.load(Path("todos.xml"))

    # Mutation 1: produces priority="High" (capitalised, not in the
    # enum). The fixing loop runs two passes:
    #   Pass 1 — Strategy A stashes each bad value under `prio` and
    #            removes `priority`. The enum error goes away but a
    #            "priority attribute required" error appears.
    #   Pass 2 — Strategy B reads the stashed values, lowercases
    #            them, reinstates `priority="high"`, drops `prio`.
    #            The document is now valid.
    # `apply()` returns a new, valid TodoList. We save it and create
    # a checkpoint of this known-good state.
    doc = await doc.apply(BulkReprioritise("High"))
    doc.save()
    checkpoint = doc.checkpoint()

    # Mutation 2: removes every <title>. `_repair` has no strategy
    # for inventing titles, so all three attempts return unchanged
    # content. `apply()` raises `MutationFailedError`. We restore
    # the checkpoint; the file on disk is left exactly as it was
    # after the successful mutation 1.
    try:
        await doc.apply(PurgeTitles())
    except MutationFailedError:
        checkpoint.restore()
```

Running the example produces log output that traces both behaviours:
two fixing-loop iterations for mutation 1 (attempt 1 raises the error
count from 2 to 4 as Strategy A introduces its temporary defect;
attempt 2 succeeds), and three failed attempts for mutation 2 before
`MutationFailedError` fires and the checkpoint restores.

## LLM-agnostic: the repair function is a protocol

`_repair` is just an async callable. That means you can plug in any LLM
SDK — or no LLM at all. The same `Note` subclass above can be backed by
any of these:

```python
# --- Anthropic SDK ---
from anthropic import AsyncAnthropic
client = AsyncAnthropic()

async def repair(content, errors, document_type):
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": f"Fix this {document_type}:\n{content}\n\nErrors:\n{errors}"}],
    )
    return msg.content[0].text

# --- OpenAI SDK ---
from openai import AsyncOpenAI
client = AsyncOpenAI()

async def repair(content, errors, document_type):
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Fix this {document_type}:\n{content}\n\nErrors:\n{errors}"}],
    )
    return resp.choices[0].message.content

# --- Purely deterministic ---
async def repair(content, errors, document_type):
    # If the schema just needs a missing closing tag added, we don't
    # need an LLM — a regex fix does.
    if not content.rstrip().endswith("</note>"):
        return content + "</note>"
    return content
```

Interesting consequence: you can cascade. Try the cheap deterministic
fix first, only fall back to an LLM call if it doesn't resolve the
errors. `FixingLoop` gives you the attempt count so you can key on it.

## Without a schema: well-formedness alone

`_validate_schema` is a hook, not a requirement. Returning `[]` turns
the schema check into a no-op, so the only invariant the class still
enforces is that content parses successfully. The always-valid
invariant narrows from "well-formed **and** schema-valid" to
"well-formed" — which is all some formats (or some phases of a
project) ever need.

```python
from wellformed.xml import XMLValidatedDocument


class FreeFormXML(XMLValidatedDocument):
    @classmethod
    def _validate_schema(cls, content):
        return []  # no schema check; parsing is the only invariant

    @classmethod
    def _get_document_type(cls):
        return "free-form-xml"

    @classmethod
    async def _repair(cls, content, errors, document_type):
        # `errors` will only ever contain XML parse errors — mismatched
        # tags, unclosed entities, stray `&`, and so on. Repair
        # strategies here are syntactic, not semantic.
        ...
```

The trade-off: repair can fix a missing `</tag>`, but it has no way to
tell whether a structurally-valid document is semantically correct —
there is no schema to compare against. `Checkpoint` and `FixingLoop`
behave identically to the schema-backed case.

Typical use cases:

- **Formats with no standard schema.** User-authored XML notes,
  snippets, or bespoke markup that varies too much to pin down.
- **Schema not yet available.** Prototype phase, or a third-party
  format where the schema is missing, incomplete, or out of date.
- **Syntactic integrity is the contract.** Config files where
  "well-formed XML" is all downstream code relies on; semantic checks
  live elsewhere.
- **Driving `FixingLoop` directly.** Skip the `ValidatedDocument`
  wrapper entirely and pass `make_xml_wellformed_validator()` (from
  `wellformed.xml`) to `FixingLoop` to get retry-on-parse-error
  behaviour for any string content.

## Plugins

| Plugin               | Status  | Install                        |
|----------------------|---------|--------------------------------|
| XML (lxml)           | shipped | `pip install wellformed[xml]`  |
| JSON / JSON Schema   | shipped | `pip install wellformed[json]` |

## Writing a plugin

A plugin teaches `wellformed` to interpret a new format. The contract is
small: one base class, one exception, four methods. If your format has
a parser and some notion of "valid" that can be expressed as a list of
error strings, you can wrap it.

Good candidates include structured text formats (YAML, TOML, INI,
HCL), code representations (Python AST, tree-sitter syntax trees,
S-expressions), and domain-specific markup (Markdown with a validator,
protobuf text format, OpenAPI documents). The core machinery —
validation, fixing loops, checkpoints — works identically for all of
them.

### The shape of a plugin

A plugin is a single subdirectory under `wellformed/` with three files
that mirror the shipped examples in
[`src/wellformed/xml/`](src/wellformed/xml/) and
[`src/wellformed/json/`](src/wellformed/json/):

```
wellformed/
  yourformat/
    __init__.py     # import guard + re-exports
    document.py     # YourFormatValidatedDocument
    exceptions.py   # YourFormatParseError
    validators.py   # optional validator builders
```

### The four hooks

Subclass `ValidatedDocument[ParsedT]`, pick a concrete `ParsedT` for
your parsed representation (an AST node, a `dict`, a library object),
and implement:

- **`_parse(cls, content: str) -> ParsedT`** — parse text to the
  in-memory form. Raise a subclass of `DocumentParseError` (so callers
  can catch parse failures generically) with whatever location
  information your parser gives you. Most parsers surface `line` and
  `column`; pass them through.
- **`_validate_schema(cls, content: str) -> list[str]`** — return a
  list of schema-level error messages. Empty list means "valid". If
  your format has no schema, return `[]` and the invariant narrows to
  "well-formed" (see [Without a schema](#without-a-schema-well-formedness-alone)).
- **`_get_document_type(cls) -> str`** — a short identifier, used in
  log lines, error messages, and as a prompt label for LLM-backed
  repair functions.
- **`_repair(cls, content, errors, document_type) -> str`** — an
  async callable that takes the current (invalid) content and the
  errors from the last validation pass and returns repaired content.
  Can be an LLM call, a deterministic rule, or a hybrid — see
  [LLM-agnostic](#llm-agnostic-the-repair-function-is-a-protocol).

### Validator builders are optional

The XML and JSON plugins ship small factory functions
(`make_xml_schema_validator`, `make_json_schema_validator`, etc.) that
return a `ValidateFunction` bound to a schema file. These are
convenience, not contract — if your format has one obvious schema
dialect, ship one; if not, users can pass a callable directly. See
[`xml/validators.py`](src/wellformed/xml/validators.py) and
[`json/validators.py`](src/wellformed/json/validators.py).

### Packaging

Add your runtime dependencies as an optional extra in
`pyproject.toml` so the core stays dependency-free:

```toml
[project.optional-dependencies]
yourformat = ["your-parser>=1.0"]
```

Guard the import at the top of `wellformed/yourformat/__init__.py` so
users who haven't installed the extra get a clear error:

```python
try:
    import your_parser  # noqa: F401
except ImportError as e:
    raise ImportError(
        "wellformed.yourformat requires your-parser. "
        "Install with: pip install wellformed[yourformat]"
    ) from e
```

### Tests

Mirror [`tests/xml/`](tests/xml/) or [`tests/json/`](tests/json/):
guard the whole module with `pytest.importorskip("your_parser")`, add
a minimal `*ValidatedDocument` subclass as a fixture, and cover four
behaviours — load success, parse failure raises your
`*ParseError`, schema failure raises `SchemaValidationError`,
mutations via `apply()` round-trip correctly.

## Releasing

Versioning is managed with [bump-my-version](https://github.com/callowayproject/bump-my-version). It updates the version in `pyproject.toml`, commits the change, and creates a Git tag in one step.

```bash
# Install dev dependencies (includes bump-my-version)
uv sync --group dev

# Bump the patch version: 0.1.0 -> 0.1.1
uv run bump-my-version bump patch

# Bump the minor version: 0.1.1 -> 0.2.0
uv run bump-my-version bump minor

# Bump the major version: 0.2.0 -> 1.0.0
uv run bump-my-version bump major
```

To preview what a bump would do without changing anything:

```bash
uv run bump-my-version bump patch --dry-run --verbose
```

After bumping, push the commit and tag together:

```bash
git push && git push --tags
```

To build and publish to PyPI:

```bash
uv build
uv publish
```

## License

MIT.
