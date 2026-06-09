package protocol

import "time"

// Party 描述 WebSocket envelope 中的通信参与方。
type Party struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

// AckMeta 描述客户端是否要求 ack，以及当前 ack 的阶段。
type AckMeta struct {
	Mode     string `json:"mode"`
	Required bool   `json:"required"`
}

// WSEvent 是 Stage 5 Frontend <-> Gateway 统一的实时消息结构。
type WSEvent struct {
	SchemaVersion string         `json:"schema_version"`
	EventID       string         `json:"event_id"`
	SessionID     string         `json:"session_id"`
	TaskID        string         `json:"task_id,omitempty"`
	TraceID       string         `json:"trace_id,omitempty"`
	Type          string         `json:"type"`
	Kind          string         `json:"kind"`
	Seq           int64          `json:"seq,omitempty"`
	Timestamp     string         `json:"timestamp"`
	Sender        Party          `json:"sender"`
	Receiver      Party          `json:"receiver"`
	Status        string         `json:"status"`
	InReplyTo     string         `json:"in_reply_to,omitempty"`
	Ack           *AckMeta       `json:"ack,omitempty"`
	Payload       map[string]any `json:"payload"`
}

// ArtifactAction 定义 artifact 卡片上的前端动作。
type ArtifactAction struct {
	Action  string             `json:"action"`
	Label   string             `json:"label"`
	Enabled bool               `json:"enabled"`
	Target  *ArtifactActionRef `json:"target,omitempty"`
}

type ArtifactActionRef struct {
	URL  string `json:"url,omitempty"`
	Path string `json:"path,omitempty"`
	Tab  string `json:"tab,omitempty"`
}

type CardProducer struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

// ArtifactCard 对应 Stage 5 artifact-card-schema-spec。
type ArtifactCard struct {
	SchemaVersion string           `json:"schema_version"`
	CardID        string           `json:"card_id"`
	ArtifactID    string           `json:"artifact_id"`
	SessionID     string           `json:"session_id"`
	TaskID        string           `json:"task_id"`
	CardType      string           `json:"card_type"`
	Title         string           `json:"title"`
	Summary       string           `json:"summary"`
	Status        string           `json:"status"`
	CreatedAt     string           `json:"created_at"`
	UpdatedAt     string           `json:"updated_at"`
	Producer      CardProducer     `json:"producer"`
	Badges        []string         `json:"badges"`
	Actions       []ArtifactAction `json:"actions"`
	Content       map[string]any   `json:"content"`
}

type HTTPError struct {
	Code    string         `json:"code"`
	Message string         `json:"message"`
	Details map[string]any `json:"details,omitempty"`
}

// HTTPEnvelope 统一 REST 返回体，便于前端和答辩材料统一口径。
type HTTPEnvelope struct {
	RequestID string     `json:"request_id"`
	Data      any        `json:"data"`
	Error     *HTTPError `json:"error,omitempty"`
}

type SessionSubscribePayload struct {
	ResumeFromSeq   int64 `json:"resume_from_seq"`
	IncludeSnapshot bool  `json:"include_snapshot"`
}

type ChatMessagePayload struct {
	MessageID   string `json:"message_id,omitempty"`
	Role        string `json:"role,omitempty"`
	Format      string `json:"format,omitempty"`
	Content     string `json:"content"`
	StreamChunk bool   `json:"stream_chunk,omitempty"`
}

type AckPayload struct {
	AckEventID string `json:"ack_event_id"`
	AckMode    string `json:"ack_mode"`
	Accepted   bool   `json:"accepted"`
	Reason     string `json:"reason,omitempty"`
}

type ApprovalRequiredPayload struct {
	ApprovalID string   `json:"approval_id"`
	Reason     string   `json:"reason"`
	TaskID     string   `json:"task_id"`
	Options    []string `json:"options"`
}

func NowISO() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}
