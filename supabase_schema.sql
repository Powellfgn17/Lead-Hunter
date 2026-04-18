-- ============================================
-- Lead Hunting Agent — Supabase Schema
-- ============================================
-- Run this in Supabase SQL Editor to create the leads table.

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main leads table
CREATE TABLE IF NOT EXISTS leads (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  nom             TEXT NOT NULL,
  adresse         TEXT NOT NULL,
  telephone       TEXT,
  email           TEXT,
  ville           TEXT NOT NULL,
  niche           TEXT NOT NULL,
  score           INTEGER CHECK (score BETWEEN 1 AND 10),
  url_maps        TEXT,
  statut          TEXT DEFAULT 'nouveau' CHECK (statut IN ('nouveau', 'contacté', 'converti', 'rejeté')),
  has_website     BOOLEAN DEFAULT FALSE,
  nb_avis         INTEGER DEFAULT 0,
  dernier_avis    TEXT,
  reseaux_sociaux JSONB DEFAULT '{}',
  source          TEXT DEFAULT 'agent',
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),

  -- Contrainte d'unicité pour l'upsert
  UNIQUE(nom, adresse)
);

-- Index pour recherche rapide par ville + niche
CREATE INDEX IF NOT EXISTS idx_leads_ville_niche ON leads(ville, niche);

-- Index pour filtrer par score
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);

-- Index pour filtrer par statut
CREATE INDEX IF NOT EXISTS idx_leads_statut ON leads(statut);

-- Trigger pour auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trigger_leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- Row Level Security (optionnel mais recommandé)
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

-- Politique permettant toutes les opérations via service_role key
CREATE POLICY "Service role full access" ON leads
  FOR ALL
  USING (true)
  WITH CHECK (true);
