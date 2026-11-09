# ADR-004: Data Privacy Boundaries, NDA Guardrails, and Fallback Extraction

## Status
Accepted (Inferred from codebase implementation: `backend/main.py`)

## Context
Automotive OEMs and tier-1 component buyers mandate strict Non-Disclosure Agreements (NDAs). Proprietary CAD dimensions, metallurgy specs, alloy grades, and annual volumes cannot be transmitted to external cloud LLM providers whose terms do not explicitly guarantee zero data retention (ZDR) and no-training commitments.

## Problem
Public LLM endpoints or third-party API aggregators (e.g., AgentRouter) forward prompt content upstream. Without verified commercial enterprise agreements, transmitting customer RFQ details breaches contractual confidentiality and intellectual property rights.

## Decision
1. Implement the `AI_NDA_APPROVED` environment flag (defaulting strictly to `false`).
2. When `AI_NDA_APPROVED=false`:
   - Real customer RFQ data is strictly barred from external AI gateway calls.
   - Assistant chat endpoints (`/api/assistant/chat`) reject queries referencing non-synthetic RFQs with HTTP 403 Forbidden.
   - File intake extraction (`/api/intake/file-extract`) defaults to local rule-based pattern extraction (`rule_extract`) using regex heuristics, completely bypassing external LLMs.
   - LLM processing is permitted only if the user explicitly confirms the upload contains synthetic demo data (`demo_only=True`).
   - Historical routing suggestions fall back to deterministic token and attribute similarity scoring.
3. Grounding Constraint: When AI extraction runs, extracted fields must contain a `source_excerpt` that is an exact substring match from the source text. Discard any field not directly grounded in the text.
4. Transparency: The UI must clearly label extraction origins as either "AI model: <model>" or "local pattern extraction (Non-AI)".

## Alternatives Considered
1. **Unconditional AI Inference:** Rejected due to immediate client NDA breach risk.
2. **Self-hosted Local LLM (e.g., Ollama / vLLM):** Highly recommended for long-term on-premises deployment, but introduces heavy GPU hardware prerequisites for current evaluation.

## Advantages
- Absolute legal compliance and data protection for client confidential information.
- Zero-cost, zero-latency local fallback that functions reliably without an Internet connection or API keys.
- Elimination of LLM hallucination through exact substring citation enforcement.

## Disadvantages
- Regex heuristics in `rule_extract` cannot interpret complex natural language or irregular formatting as effectively as advanced LLMs.

## Consequences
External AI providers must be vetted and contracted with Enterprise Zero Data Retention before flipping `AI_NDA_APPROVED=true` in production environments.
