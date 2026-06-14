-- Migration 035: Add citation accuracy and recall@k metrics to eval results
-- Phase 4.2 and 4.4 of RAG Enhancement Plan

ALTER TABLE rag_eval_results
    ADD COLUMN IF NOT EXISTS citation_accuracy_score NUMERIC,
    ADD COLUMN IF NOT EXISTS recall_at_k NUMERIC;

ALTER TABLE rag_eval_runs
    ADD COLUMN IF NOT EXISTS avg_citation_accuracy_score NUMERIC DEFAULT 0,
    ADD COLUMN IF NOT EXISTS avg_recall_at_k NUMERIC DEFAULT 0;
