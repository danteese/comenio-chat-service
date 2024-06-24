BEGIN TRANSACTION;

ALTER TABLE conversations RENAME to conversations_temp;

CREATE TABLE IF NOT EXISTS `conversations` (
  `id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
  `uuid` VARCHAR(255) default (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  `user_id` INTEGER NOT NULL,
  `created_at` TIMESTAMP DEFAULT(STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW')) NOT NULL
);

INSERT INTO conversations (id, user_id, created_at)
SELECT id, user_id, created_at
FROM conversations_temp;

DROP TABLE conversations_temp;

COMMIT;