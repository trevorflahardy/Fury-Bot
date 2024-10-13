CREATE SCHEMA IF NOT EXISTS invite_tracker;

CREATE TABLE IF NOT EXISTS invite_tracker.invites (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL, -- The guild the invite is for
    user_id BIGINT NOT NULL, -- The user who created the invite
    invite_code VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE, -- The time the invite was created
    expires_at TIMESTAMP WITH TIME ZONE, -- The time the invite expires (can be NULL)
    uses INT NOT NULL DEFAULT 0, -- The number of times the invite has been used
    UNIQUE(guild_id, invite_code)
);

-- Keeps track of the users who have used a specific invite. This allows
-- the bot to track which member has joined using which invite.
CREATE TABLE IF NOT EXISTS invite_tracker.invite_uses (
    id SERIAL PRIMARY KEY,
    invite_id INTEGER REFERENCES invite_tracker.invites(id) ON DELETE CASCADE, -- The invite that was used
    user_id BIGINT NOT NULL, -- The user who used the invite
    joined_at TIMESTAMP WITH TIME ZONE, -- The time the user joined
    UNIQUE(invite_id, user_id)
);