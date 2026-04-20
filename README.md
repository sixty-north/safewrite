# safewrite

**Invariant-preserving documents for agents that modify persistent state.**

A chat reply is ephemeral; a config file your agent just rewrote is not.
`safewrite` gives LLM agents three composable primitives for editing
structured documents reliably:

- `ValidatedDocument` — a document that is always well-formed and
  schema-valid by construction.
- `FixingLoop` — validate → repair → re-validate, format-agnostic and
  LLM-agnostic.
- `Checkpoint` — atomic rollback at file, multi-file, or directory
  granularity.

The core is pure Python with zero runtime dependencies. Formats are
added via plugins. XML ships today; JSON / YAML / AST are on the
roadmap.

## Installation

```bash
pip install safewrite              # core only
pip install safewrite[xml]         # with XML plugin (installs lxml)
```

Requires Python 3.11 or newer.

## The 30-second quickstart (XML)

```python
from pathlib import Path
from safewrite import DocumentMutation, MutationFailedError
from safewrite.xml import XMLValidatedDocument, make_xml_schema_validator

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

## BYO LLM: the repair function is a protocol

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

## Plugins

| Plugin               | Status  | Install                     |
|----------------------|---------|-----------------------------|
| XML (lxml)           | shipped | `pip install safewrite[xml]` |
| JSON / JSON Schema   | planned | —                           |
| YAML                 | planned | —                           |
| Python AST           | planned | —                           |

Writing a plugin is four methods: `_parse`, `_validate_schema`,
`_get_document_type`, `_repair`. See `src/safewrite/xml/document.py`
for the reference implementation.

## License

MIT.
