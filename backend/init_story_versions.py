
import sqlite3

conn = sqlite3.connect("lotia.db")

conn.execute("PRAGMA foreign_keys = ON")

conn.execute("""
CREATE TABLE IF NOT EXISTS story_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    editor_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (story_id) REFERENCES stories(id),
    FOREIGN KEY (editor_id) REFERENCES users(id),

    UNIQUE (story_id, version_number),

    CHECK (status IN ('draft', 'pending', 'approved', 'rejected'))
)
""")

conn.commit()
conn.close()

print("StoryVersions 表创建成功！")
