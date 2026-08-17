-- 礼物事件表（最终落库数据，已去重）
CREATE TABLE IF NOT EXISTS gift_events (
    id              BIGSERIAL PRIMARY KEY,
    message_id      VARCHAR(64)  NOT NULL,
    room_id         BIGINT       NOT NULL,
    sender_uid      BIGINT       NOT NULL,
    sender_nickname VARCHAR(64),
    gift_id         INT          NOT NULL,
    gift_name       VARCHAR(64),
    gift_count      INT          NOT NULL DEFAULT 1,
    gift_price      INT,
    total_price     INT,
    gift_value      NUMERIC(10,2),
    total_value     NUMERIC(10,2),
    receive_uid     BIGINT,
    hit_score       INT,
    sent_at         TIMESTAMP    NOT NULL,
    received_at     TIMESTAMP    NOT NULL,
    port            SMALLINT,
    created_at      TIMESTAMP    DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gift_events_msg_id ON gift_events (message_id);
CREATE INDEX IF NOT EXISTS idx_gift_events_room_time ON gift_events (room_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_gift_events_sender    ON gift_events (sender_uid);

-- 礼物信息表（价值换算依据）
-- id_type 区分三种 ID 命名空间，数字可能重复：
--   gfid = dgb 消息中的真实礼物 ID
--   pid  = pandora 活动图片 ID（pid_* 键）
--   pgid = 活动礼物图片 ID（pgid_* 键）
CREATE TABLE IF NOT EXISTS gift_catalog (
    id_type      VARCHAR(8)    NOT NULL DEFAULT 'gfid',
    gift_id      INT           NOT NULL,
    gift_name    VARCHAR(64)   NOT NULL,
    price_yu     NUMERIC(10,2),
    value_rmb    NUMERIC(10,2),
    updated_at   TIMESTAMP     DEFAULT now(),
    PRIMARY KEY (id_type, gift_id)
);

-- 弹幕消息表：见 danmu_messages.sql（单独文件，幂等，可单独执行）
