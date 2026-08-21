ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS character_cue_json TEXT;
