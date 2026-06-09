package store

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type Backend interface {
	AuthStore
	SessionStore
	EventStore
	TaskStore
	ArtifactStore
	ApprovalStore
	AgentDefinitionStore
	SessionFileStore     // deprecated: 向后兼容，新代码使用 WorkspaceFileIndexStore
	WorkspaceFileIndexStore
}

type Closer interface {
	Close() error
}

// NewDefaultStore 根据环境变量返回默认存储实现，生产默认走 SQLite。
func NewDefaultStore() (Backend, func() error, error) {
	backend := strings.TrimSpace(os.Getenv("GATEWAY_STORE_BACKEND"))
	if backend == "" {
		backend = "sqlite"
	}
	switch backend {
	case "memory":
		return NewMemoryStore(), func() error { return nil }, nil
	case "sqlite":
		dbPath := strings.TrimSpace(os.Getenv("GATEWAY_SQLITE_PATH"))
		if dbPath == "" {
			dbPath = filepath.Join("data", "gateway.db")
		}
		store, err := NewSQLiteStore(dbPath)
		if err != nil {
			return nil, nil, err
		}
		return store, store.Close, nil
	case "postgres":
		dsn := strings.TrimSpace(os.Getenv("GATEWAY_POSTGRES_DSN"))
		if dsn == "" {
			dsn = "postgres://agenthub:agenthub@localhost:5432/agenthub?sslmode=disable"
		}
		ctx := context.Background()
		store, err := NewPostgresStore(ctx, dsn)
		if err != nil {
			return nil, nil, err
		}
		return store, store.Close, nil
	default:
		return nil, nil, fmt.Errorf("unsupported gateway store backend: %s", backend)
	}
}
