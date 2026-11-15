
import sqlite3

conn = sqlite3.connect("lotia.db")

conn.execute("PRAGMA foreign_keys = ON")

conn.execute("""
CREATE TABLE IF NOT EXISTS story_version_periods (
    version_id INTEGER NOT NULL,
    period_id INTEGER NOT NULL,

    PRIMARY KEY (version_id, period_id),

    FOREIGN KEY (version_id) REFERENCES story_versions(id),
    FOREIGN KEY (period_id) REFERENCES historical_periods(id)
)
""")

conn.commit()
conn.close()

print("StoryVersionPeriods 表创建成功！")
