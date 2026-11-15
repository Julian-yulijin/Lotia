
import sqlite3

conn = sqlite3.connect("lotia.db")

conn.execute("PRAGMA foreign_keys = ON")

conn.execute("""
CREATE TABLE IF NOT EXISTS story_version_locations (
    version_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,

    PRIMARY KEY (version_id, location_id),

    FOREIGN KEY (version_id) REFERENCES story_versions(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
)
""")

conn.commit()
conn.close()

print("StoryVersionLocations 表创建成功！")
