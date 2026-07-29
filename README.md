> **Repository layout.** This repository contains two parts of the Jeen AI Solution
> home assignment.
>
> - **Part 2** — Document Indexing & Retrieval. All files at the repository root.
>   Documented below.
> - **Part 3** — Multi-Agent Flow in Langflow. See [`part3/`](part3/), containing the
>   flow JSON export, an HTTP POST run output, and the demo video.

# Document Indexing & Retrieval

A Python module that ingests a PDF or DOCX file, extracts clean text, splits it
into chunks using one of three strategies, generates embeddings with the Gemini
API, stores them in PostgreSQL with pgvector, and supports semantic search over
the stored content.

The test corpus is Bank of Israel Proper Conduct of Banking Business Directive
367 on E-banking, chosen so that the module doubles as the retrieval layer for a
banker-facing assistant grounded in regulatory directives.

---

## Architecture

| File | Responsibility |
|---|---|
| `index_documents.py` | CLI entry point for ingestion |
| `search.py` | CLI entry point for semantic search |
| `extraction.py` | PDF and DOCX text extraction and normalisation |
| `chunking.py` | The three chunking strategies |
| `embeddings.py` | Gemini embedding calls, rate limiting, retry, normalisation |
| `db.py` | Connection, schema, insert, vector search |
| `config.py` | Environment variables and constants |
| `errors.py` | Exception types, one per handled failure mode |

The two CLI scripts contain no business logic beyond argument parsing and error
reporting. Each supporting module can be imported and tested on its own.

---

## Installation

Requires Python 3.10 or newer.

```bash
git clone <repository-url>
cd <repository-directory>

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Database

Any PostgreSQL instance with the `pgvector` extension available. Either a local
container:

```bash
docker run --name pg -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 -d pgvector/pgvector:pg17
```

or a hosted provider that supports pgvector. The extension itself is created
automatically on first run; only availability is required.

### Environment variables

Copy the template and fill in real values:

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | API key from Google AI Studio |
| `POSTGRES_URL` | Full PostgreSQL connection URL |

`.env` is listed in `.gitignore`. No credential appears in source code, and no
credential is ever printed by either CLI.

---

## Usage

### Indexing

```bash
python index_documents.py --file ./docs/example.pdf --strategy paragraph
```

| Flag | Default | Description |
|---|---|---|
| `--file` | required | Path to a `.pdf` or `.docx` file |
| `--strategy` | `paragraph` | `fixed`, `sentence`, `paragraph`, or `all` |
| `--chunk-size` | 1000 | Characters per chunk (`fixed` only) |
| `--overlap` | 150 | Overlapping characters (`fixed` only) |
| `--sentences-per-chunk` | 5 | Sentences per chunk (`sentence` only) |

`--strategy all` indexes the same document three times, once per strategy, which
is what makes the comparison below possible.

Re-indexing the same file under the same strategy replaces the previous rows
rather than duplicating them.

### Searching

```bash
python search.py --query "login issue"
```

| Flag | Default | Description |
|---|---|---|
| `--query` | required | Natural language query |
| `--top-k` | 5 | Number of results |
| `--strategy` | all | Restrict results to one chunking strategy |
| `--compare` | off | Show the best matches from each chunking strategy |
| `--full` | off | Print whole chunks instead of a preview |

---

## Sample output

### Indexing run

```
$ python index_documents.py --file ./docs/boi_ebanking_directive.pdf --strategy paragraph

Reading: ./docs/boi_ebanking_directive.pdf
  extracted 30,385 characters

Embedding model: gemini-embedding-001 at 1536 dimensions

  Strategy: paragraph
    54 chunks produced
    embedded 54/54
    removed 54 previously indexed chunks
    stored 54 chunks

Done. 54 chunks indexed from boi_ebanking_directive.pdf.

Current contents of the table:
  boi_ebanking_directive.pdf               fixed         36 chunks
  boi_ebanking_directive.pdf               paragraph     54 chunks
  boi_ebanking_directive.pdf               sentence      45 chunks
```

The same document produced 36, 45 and 54 chunks under the three strategies.

### Search run

```
$ python search.py --query "how should banks monitor for fraud in e-banking"

Query: "how should banks monitor for fraud in e-banking"

5 result(s)

  [1] similarity 0.7625
      file: boi_ebanking_directive.pdf  |  strategy: sentence  |  chunk #25  |  id 62
      The growth in e-banking activities raises concern of an increase in risks of
      fraud and embezzlement. As such, banking corporations are required to expand
      and increase the sophistication of the mechanism for monitoring anomalies in
      customers' accounts as well as in activities that are not anomalous ...

  [2] similarity 0.7523
      file: boi_ebanking_directive.pdf  |  strategy: paragraph  |  chunk #18  |  id 154
      inherent in e-banking, with the view that the customer's alertness is
      important in minimizing risks.

  [3] similarity 0.7214
      file: boi_ebanking_directive.pdf  |  strategy: fixed  |  chunk #21  |  id 22
      ats to e-banking that are exposed in Israel and worldwide. Alerts to customers
      (Sections 48-51) 43. A banking corporation is to make use of anomaly
      monitoring in order to alert customers to the extent necessary and to take
      immediate measures such as the suspension of a transaction ...

  [4] similarity 0.7184
      file: boi_ebanking_directive.pdf  |  strategy: sentence  |  chunk #26  |  id 63
      A banking corporation is to make use of anomaly monitoring in order to alert
      customers to the extent necessary and to take immediate measures such as the
      suspension of a transaction or of obtaining the customer's approval for a
      transaction before it is executed. Likewise, the banking corporation wil ...

  [5] similarity 0.7147
      file: boi_ebanking_directive.pdf  |  strategy: paragraph  |  chunk #28  |  id 164
      as high-risk, including, but not limited to, the activities classified as such
      in Section 42 of the Directive. 42. In addition, the monitoring mechanism is
      to be updated in line with the methods of fraud and threats to e-banking that
      are exposed in Israel and worldwide.
```

Full unedited output for all three runs is committed as `run_index.txt`,
`run_search.txt` and `run_compare.txt`.

---

## Comparing the three chunking strategies

The `split_strategy` column exists so the same document can be indexed under all
three strategies and the strategies compared directly:

```bash
python index_documents.py --file ./docs/boi_ebanking_directive.pdf --strategy all
python search.py --query "how should banks monitor for fraud in e-banking" --compare
```

### Best result from each strategy

| Strategy | Top similarity | What it returned |
|---|---|---|
| `sentence` | **0.7625** | A complete statement of the requirement: rising e-banking activity raises fraud risk, so banks must expand and increase the sophistication of anomaly-monitoring mechanisms |
| `paragraph` | 0.7523 | A fragment beginning mid-sentence: *"inherent in e-banking, with the view that the customer's alertness is important..."* |
| `fixed` | 0.7214 | A chunk beginning `ats to e-banking` — the word "threats" cut in half by the character boundary |

### What this shows

**Sentence chunking won on this document.** Its top result is self-contained and
directly answers the question. Grouping whole sentences kept the subject, the
reasoning and the obligation inside one chunk.

**Fixed-size chunking cut a word in half.** Its top result opens mid-word. The
150-character overlap meant the content still existed elsewhere and retrieval
succeeded, but the chunk that would be handed to a downstream model begins with
a word fragment. This is the predictable failure mode of splitting on character
count, visible directly in the output rather than argued for in the abstract.

**Paragraph chunking failed for a subtler reason.** Its top-ranked chunk is a
sentence fragment carrying almost no usable content, because PDF extraction
produced line-level breaks that do not correspond to the logical paragraphs of a
numbered legal directive. The strategy assumes the document has real paragraph
structure; this one, after extraction, does not.

### The result worth noting

**A higher similarity score did not mean a more useful chunk.**

Paragraph scored 0.7523 against fixed's 0.7214, yet returned far less usable
text. Within the paragraph strategy alone, the chunk ranked first (0.7523) is a
fragment, while the chunk ranked third (0.7082) is a complete, directly relevant
passage on anomaly monitoring and customer alerts.

Cosine similarity measures proximity in embedding space. It does not measure
whether a passage answers the question. A short fragment sharing vocabulary with
the query can outrank a complete passage that actually contains the answer.

The practical consequence: retrieval quality cannot be assessed from similarity
scores alone. It needs a labelled set of questions with known correct passages,
and a measurement of how often the correct passage is retrieved. Ranking by
distance is a starting point, not an evaluation.

### Choosing a strategy

For this document, sentence chunking. More generally, the choice depends on the
document, which is why the strategy is a parameter and why it is stored per
chunk rather than assumed.

---

## Database schema

```sql
CREATE TABLE document_chunks (
    id             SERIAL PRIMARY KEY,
    chunk_text     TEXT        NOT NULL,
    embedding      vector(1536) NOT NULL,
    filename       TEXT        NOT NULL,
    split_strategy TEXT        NOT NULL,
    chunk_index    INTEGER     NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX document_chunks_file_strategy_idx
    ON document_chunks (filename, split_strategy);
```

`chunk_index` is not required by the specification but is stored because it
allows a retrieved chunk to be located within its source document, and it makes
results reproducible.

---

## The three strategies

| Strategy | How it splits | Strength | Weakness |
|---|---|---|---|
| `fixed` | Every N characters, with overlap | Predictable chunk size and cost | Ignores meaning, cuts mid-word. The overlap exists so an idea straddling a boundary still appears whole somewhere |
| `sentence` | Groups of N sentences | Never cuts mid-sentence | Chunk length varies widely, so one chunk may carry far more content than another |
| `paragraph` | One chunk per paragraph | Most semantically coherent when the document has real paragraph structure | Entirely dependent on that structure surviving extraction |

---

## Error handling

Every failure below is caught and reported as a single readable line with exit
code 1. No stack traces reach the user.

| Failure | Message |
|---|---|
| Missing file | `Error: File not found: /Users/.../docs/YOUR_FILE.pdf` |
| Unsupported file type | `Error: Unsupported file type '.md'. Supported: .pdf, .docx` |
| Document with no extractable text | `Error: No extractable text found in <file>. If this is a scanned document it needs OCR first.` |
| Embedding failure | `Error: Embedding failed after 5 attempts: <reason>` |
| Database connection failure | `Error: Could not connect to PostgreSQL. Check POSTGRES_URL in .env, and that the database is reachable.` |
| Empty search results / missing table | `Error: Table 'document_chunks' does not exist. Index a document first with index_documents.py.` |
| Missing environment variable | `Error: GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in.` |

---

## Design notes

**Embedding dimensionality.** `gemini-embedding-001` returns 3072 dimensions by
default. pgvector's HNSW and IVFFlat indexes support at most 2000, so an
unmodified default makes index creation fail. The module requests 1536
dimensions explicitly and sets the column type to match. This was established by
measuring the returned vector length before writing the schema, rather than
assuming it.

**Normalisation.** The model's full-length output is unit length; a truncated
output is not. Every vector is re-normalised before storage. Without this,
cosine similarity scores are subtly wrong in a way that produces no error and no
visible symptom.

**Task types.** Document chunks are embedded with `RETRIEVAL_DOCUMENT` and
queries with `RETRIEVAL_QUERY`, so the model places a question near the passage
that answers it rather than near other questions.

**Rate limiting.** The free tier permits 100 embedding requests per minute.
Reacting to a 429 after the fact proved insufficient, because the server's
requested wait can be an order of magnitude longer than a naive exponential
backoff. The client now paces itself with a sliding-window limiter set below the
ceiling, and when a 429 does occur it reads the server's own retry delay from
the response rather than guessing.

**Vector transport.** Vectors are passed to PostgreSQL as pgvector text literals
and cast in SQL. This avoids an additional adapter dependency and keeps the wire
format explicit.

**Idempotent re-indexing.** Rows for a given filename and strategy are deleted
before insertion, so running the same command twice does not duplicate data.

---

## Limitations

**Right-to-left PDF extraction.** Hebrew and Arabic text in PDFs frequently
extracts with reversed character order or broken word boundaries, depending on
how the PDF was produced. This is a limitation of PDF text extraction generally,
not of this module. DOCX extraction is reliable for RTL text because the
structure is explicit rather than positional. Production use with Hebrew PDFs
would need a bidirectional-aware parser or an OCR pass, plus validation of the
extracted text before indexing.

**Paragraph structure in extracted PDFs.** As the comparison above shows,
paragraph chunking depends on the extracted text having genuine paragraph
breaks. Numbered legal documents often do not survive extraction with that
structure intact.

**Scanned documents.** A PDF containing only page images yields no text and is
rejected with a clear message. OCR is out of scope.

**Sentence splitting.** Uses a punctuation-based rule with no abbreviation
dictionary. A sentence ending in an abbreviation may split early. This is a
deliberate trade: an incomplete abbreviation list produces inconsistent errors,
whereas a simple rule produces predictable ones.

**Sequential embedding.** Chunks are embedded one call at a time with pacing and
retry, which is reliable but not fast. Production use would batch requests and
run on a paid tier.

**Retrieval evaluation.** The comparison above is a single query against a single
document. A real assessment needs a labelled set of questions with known correct
passages, measuring how often the correct passage is retrieved rather than
comparing similarity scores.
