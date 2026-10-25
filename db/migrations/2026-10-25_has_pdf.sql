-- Migration 2026-10-25: cot has_pdf cho web UI (khung xem PDF).
-- Chay 1 lan trong Supabase SQL Editor. Idempotent: chay lai khong loi.
ALTER TABLE papers ADD COLUMN IF NOT EXISTS has_pdf BOOLEAN NOT NULL DEFAULT false;
