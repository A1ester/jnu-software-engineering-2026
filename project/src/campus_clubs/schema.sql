PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','staff'))
);
CREATE TABLE IF NOT EXISTS clubs (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
 id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id), user_id INTEGER NOT NULL REFERENCES users(id),
 role TEXT NOT NULL CHECK(role IN ('member','leader')), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL, UNIQUE(club_id,user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_leader ON memberships(club_id) WHERE role='leader' AND active=1;
CREATE TABLE IF NOT EXISTS applications (
 id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id), user_id INTEGER NOT NULL REFERENCES users(id),
 message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','cancelled')),
 reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_application ON applications(club_id,user_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS club_registrations (
 id INTEGER PRIMARY KEY, applicant_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL COLLATE NOCASE,
 description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT,
 club_id INTEGER REFERENCES clubs(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_club_name ON club_registrations(name) WHERE status='pending';
CREATE TABLE IF NOT EXISTS activities (
 id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id), title TEXT NOT NULL, theme TEXT NOT NULL,
 description TEXT NOT NULL, location TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 10000),
 registration_deadline TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
 waitlist_enabled INTEGER NOT NULL DEFAULT 0 CHECK(waitlist_enabled IN (0,1)),
 status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','Submitted','Approved','Rejected','Published','RegistrationOpen','RegistrationClosed','InProgress','Finished','Archived','Cancelled')),
 review_reason TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 CHECK(registration_deadline <= start_time AND start_time < end_time)
);
CREATE TABLE IF NOT EXISTS registrations (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), user_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('confirmed','waitlisted','cancelled')), checked_in INTEGER NOT NULL DEFAULT 0 CHECK(checked_in IN (0,1)),
 created_at TEXT NOT NULL, cancelled_at TEXT, checked_in_at TEXT,
 CHECK(checked_in=0 OR status='confirmed')
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_registration ON registrations(activity_id,user_id) WHERE status IN ('confirmed','waitlisted');
CREATE INDEX IF NOT EXISTS registration_queue ON registrations(activity_id,status,id);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), title TEXT NOT NULL,
 assignee_id INTEGER NOT NULL REFERENCES users(id), due_time TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','done')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, message TEXT NOT NULL,
 read INTEGER NOT NULL DEFAULT 0 CHECK(read IN (0,1)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_logs (
 id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, result TEXT NOT NULL, message TEXT NOT NULL,
 entity_type TEXT, entity_id INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), csrf_token TEXT NOT NULL,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS venues (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS venue_applications (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), venue_id INTEGER NOT NULL REFERENCES venues(id),
 start_time TEXT NOT NULL, end_time TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 reason TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT,
 CHECK(start_time<end_time)
);
CREATE INDEX IF NOT EXISTS approved_venue_intervals ON venue_applications(venue_id,status,start_time,end_time);
CREATE UNIQUE INDEX IF NOT EXISTS one_effective_venue_request ON venue_applications(activity_id,venue_id,start_time,end_time) WHERE status IN ('pending','approved');
CREATE TABLE IF NOT EXISTS materials (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 status TEXT NOT NULL DEFAULT 'requested' CHECK(status IN ('requested','preparing','ready')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), user_id INTEGER NOT NULL REFERENCES users(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(activity_id,user_id)
);
CREATE TABLE IF NOT EXISTS reports (
 id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL REFERENCES activities(id), user_id INTEGER NOT NULL REFERENCES users(id),
 reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','resolved')),
 resolution TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_by INTEGER REFERENCES users(id), resolved_at TEXT,
 UNIQUE(activity_id,user_id,reason)
);
