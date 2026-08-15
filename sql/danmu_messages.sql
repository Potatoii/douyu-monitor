-- 弹幕消息表（chatmsg 落库，含特殊弹幕如 pandora 嵌套播报）
-- 单独执行: psql "postgresql://user:pass@host:5432/db" -f sql/danmu_messages.sql
CREATE TABLE IF NOT EXISTS danmu_messages (
    id              BIGSERIAL PRIMARY KEY,
    message_id      VARCHAR(128)  NOT NULL,
    room_id         BIGINT        NOT NULL,
    sender_uid      BIGINT        NOT NULL,
    sender_nickname VARCHAR(64),
    content         TEXT          NOT NULL,
    level           INT,
    sent_at         TIMESTAMP     NOT NULL,
    received_at     TIMESTAMP     NOT NULL,
    port            SMALLINT,
    btype           VARCHAR(32),
    created_at      TIMESTAMP     DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_danmu_msg_id    ON danmu_messages (message_id);
CREATE INDEX IF NOT EXISTS idx_danmu_room_time        ON danmu_messages (room_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_danmu_sender           ON danmu_messages (sender_uid);
