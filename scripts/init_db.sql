-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'pilot', 'copilot', 'technician')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Flights table
CREATE TABLE IF NOT EXISTS flights (
    id SERIAL PRIMARY KEY,
    flight_no VARCHAR(20) NOT NULL,
    flight_date DATE NOT NULL,
    departure_airport VARCHAR(10) NOT NULL,
    arrival_airport VARCHAR(10) NOT NULL,
    sched_dep TIMESTAMPTZ NOT NULL,
    sched_arr TIMESTAMPTZ NOT NULL,
    actual_dep TIMESTAMPTZ,
    actual_arr TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Crew assignments table
CREATE TABLE IF NOT EXISTS crew_assignments (
    id SERIAL PRIMARY KEY,
    flight_id INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seat VARCHAR(20) NOT NULL CHECK (seat IN ('CAPTAIN', 'FIRST_OFFICER')),
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ
);

-- Partial unique index: only one active (end_time IS NULL) assignment per seat per flight
CREATE UNIQUE INDEX IF NOT EXISTS crew_assignments_flight_seat_active
    ON crew_assignments(flight_id, seat)
    WHERE end_time IS NULL;

-- Maintenance logs table
CREATE TABLE IF NOT EXISTS maintenance_logs (
    id SERIAL PRIMARY KEY,
    flight_id INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Flight operational notes table
CREATE TABLE IF NOT EXISTS flight_notes (
    id SERIAL PRIMARY KEY,
    flight_id INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
