
import sqlite3

conn = sqlite3.connect("lotia.db")

conn.execute("PRAGMA foreign_keys = ON")

conn.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    result TEXT NOT NULL,
    comment TEXT,
    reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (version_id) REFERENCES story_versions(id),
    FOREIGN KEY (reviewer_id) REFERENCES users(id),

    CHECK (result IN ('approved', 'rejected'))
)
""")

conn.commit()
conn.close()

print("Reviews 表创建成功！")
