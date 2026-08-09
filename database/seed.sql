-- Seed: TMDB canonical genre list (19 genres)
-- These come from /genre/movie/list and are the only genre taxonomy used in the system

INSERT INTO genres (id, name) VALUES
    (28,    'Action'),
    (12,    'Adventure'),
    (16,    'Animation'),
    (35,    'Comedy'),
    (80,    'Crime'),
    (99,    'Documentary'),
    (18,    'Drama'),
    (10751, 'Family'),
    (14,    'Fantasy'),
    (36,    'History'),
    (27,    'Horror'),
    (10402, 'Music'),
    (9648,  'Mystery'),
    (10749, 'Romance'),
    (878,   'Science Fiction'),
    (10770, 'TV Movie'),
    (53,    'Thriller'),
    (10752, 'War'),
    (37,    'Western')
ON CONFLICT (id) DO NOTHING;

-- Seed admin user (password: Cinemate@Admin1 — change immediately in production)
-- bcrypt hash of "Cinemate@Admin1"
INSERT INTO users (email, username, hashed_password, full_name, role, onboarding_done)
VALUES (
    'admin@cinemate.io',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGEAHSuGtJhPjRq6MJ1K0nE8HMC',
    'Cinemate Admin',
    'ADMIN',
    TRUE
) ON CONFLICT DO NOTHING;
