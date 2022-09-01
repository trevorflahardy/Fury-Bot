CREATE TABLE IF NOT EXISTS profane_words (
    id SERIAL PRIMARY KEY,
    word TEXT UNIQUE
)

CREATE SCHEMA infractions;

CREATE TABLE IF NOT EXISTS infractions.time (
    guild_id BIGINT UNIQUE,
    type TEXT,
    time INT -- In seconds,
)

CREATE TABLE IF NOT EXISTS infractions.settings (
    guild_id BIGINT UNIQUE,
    notification_channel_id BIGINT,
    moderators BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    moderator_role_ids BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    valid_links TEXT[] DEFAULT ARRAY[]::TEXT[],
    ignored_channel_ids BIGINT[] DEFAULT ARRAY[]::BIGINT[]
)
