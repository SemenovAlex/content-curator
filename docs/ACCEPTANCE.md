# Live acceptance checks

Unit/integration tests do not depend on live publisher markup. Run these separately from the VPS after Chromium is installed.

```bash
cd /opt/content-curator
.venv/bin/python scripts/check_acceptance.py \
  --cli /opt/content-curator/.venv/bin/curator \
  --config /opt/content-curator/sources.yaml
```

Add `--source SOURCE_ID` to diagnose one source.

| Date | Source | Expected material |
|---|---|---|
| 2026-09-07 | `import_ai` | Import AI 472 |
| 2026-09-04 | `the_batch` | Inside Key Changes in Data Policies, Ox Alpha Revealed, Taking Custom Models Beyond Fine-Tuning |
| 2026-08-23 | `one_useful_thing` | An opinionated guide to which AI to use to do stuff |
| 2026-08-26 | `metr_research` | Brief independent investigation of agents’ behavior, reasoning and collaboration in the OpenAI / Hugging Face hacking incident |
| 2026-09-09 | `ahead_of_ai` | GPT-6 Astra, Looped Transformers, and Hidden Reasoning |
| 2026-09-04 | `gurobi_blog` | Switching from FICO Xpress to Gurobi |
| 2026-09-10 | `anthropic_research` | Measuring tactical intelligence targeting and conventional weapons capabilities of AI models |
| 2026-09-18 | `anthropic_news` | Partnering with Accenture on embedded evaluation |
| 2026-09-10 | `openai_research` | Build more natural voice experiences with GPT‑Live‑1 in the API |
| 2026-09-01 | `deepmind_blog` | Introducing agentic video understanding with Gemini |
| 2026-09-01 | `huggingface_blog` | Introducing @huggingface/kernels: 200+ WebGPU Kernels for Local AI |
| 2026-04-23 | `anthropic_engineering` | An update on recent Claude Code quality reports |
| 2026-09-01 | `deepmind_research` | Designing Proactive Thought Partners for Writing |

Negative checks:

- Anthropic Engineering must not attach featured `How we contain Claude across products` to unrelated dates.
- DeepMind Research must not return `Research`, `News`, `Explore research`, or landing pages as articles.
- OpenAI discovery must not request `/research/index/`.
- Substack feeds must not emit `XMLParsedAsHTMLWarning`.
- Import AI fragments must not create duplicates.
- Anthropic discovery must remain inside the configured section.
