package app

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"agenthub/gateway/internal/auth"
	"agenthub/gateway/internal/runtimeclient"
	"agenthub/gateway/internal/store"
)

type stubRuntimeClient struct {
	mu         sync.Mutex
	submitted  []string
	cancelled  []string
	submitResp runtimeclient.SubmittedTask
	submitErr  error
	waitFunc   func(ctx context.Context, submitted runtimeclient.SubmittedTask) (runtimeclient.RunResult, error)
}

func (s *stubRuntimeClient) SubmitInstruction(ctx context.Context, instruction string) (runtimeclient.SubmittedTask, error) {
	s.mu.Lock()
	s.submitted = append(s.submitted, instruction)
	s.mu.Unlock()
	return s.submitResp, s.submitErr
}

func (s *stubRuntimeClient) WaitForResult(ctx context.Context, submitted runtimeclient.SubmittedTask) (runtimeclient.RunResult, error) {
	if s.waitFunc != nil {
		return s.waitFunc(ctx, submitted)
	}
	return runtimeclient.RunResult{}, nil
}

func (s *stubRuntimeClient) CancelTask(ctx context.Context, runtimeJobID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cancelled = append(s.cancelled, runtimeJobID)
	return nil
}

func (s *stubRuntimeClient) RunInstruction(ctx context.Context, instruction string) (runtimeclient.RunResult, error) {
	submitted, err := s.SubmitInstruction(ctx, instruction)
	if err != nil {
		return runtimeclient.RunResult{}, err
	}
	return s.WaitForResult(ctx, submitted)
}

func TestRequestTaskRetryRequiresApprovalAfterLimit(t *testing.T) {
	t.Setenv("GATEWAY_STORE_BACKEND", "memory")
	t.Setenv("RUNTIME_BASE_URL", "http://127.0.0.1:8001")
	repoRoot := filepath.Clean("../../..")
	gatewayApp, _, err := New(repoRoot)
	if err != nil {
		t.Fatalf("new app: %v", err)
	}
	defer func() { _ = gatewayApp.Close() }()

	principal := auth.Principal{ID: "demo-user", Role: "session_approver"}
	session, err := gatewayApp.CreateSession(principal, "retry test", "multi_agent", "")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}

	task := store.Task{
		TaskID:      "task_retry",
		SessionID:   session.SessionID,
		Title:       "retry task",
		Instruction: "retry me",
		Status:      "failed",
		RetryCount:  2,
		RetryLimit:  2,
		UpdatedAt:   time.Now().UTC(),
	}
	if err := gatewayApp.Store.CreateTask(task); err != nil {
		t.Fatalf("create task: %v", err)
	}

	data, err := gatewayApp.RequestTaskRetry(principal, task.TaskID, "manual retry", false)
	if !errors.Is(err, ErrApprovalRequired) {
		t.Fatalf("expected ErrApprovalRequired, got %v", err)
	}
	if data["status"] != "pending_approval" {
		t.Fatalf("unexpected data: %#v", data)
	}

	updatedTask, err := gatewayApp.Store.GetTask(task.TaskID)
	if err != nil {
		t.Fatalf("get updated task: %v", err)
	}
	if !updatedTask.WaitingForApproval {
		t.Fatalf("expected waiting_for_approval to be true")
	}
	if updatedTask.ApprovalID == "" {
		t.Fatalf("expected approval id to be generated")
	}
}

func TestSQLiteStorePersistsSessions(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "gateway.db")
	t.Setenv("GATEWAY_STORE_BACKEND", "sqlite")
	t.Setenv("GATEWAY_SQLITE_PATH", dbPath)
	t.Setenv("RUNTIME_BASE_URL", "http://127.0.0.1:8001")

	repoRoot := filepath.Clean("../../..")
	gatewayApp, _, err := New(repoRoot)
	if err != nil {
		t.Fatalf("new app: %v", err)
	}

	principal := auth.Principal{ID: "demo-user", Role: "session_approver"}
	created, err := gatewayApp.CreateSession(principal, "sqlite session", "multi_agent", "hello")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	if err := gatewayApp.Close(); err != nil {
		t.Fatalf("close app: %v", err)
	}

	if _, err := os.Stat(dbPath); err != nil {
		t.Fatalf("sqlite db should exist: %v", err)
	}

	gatewayApp2, _, err := New(repoRoot)
	if err != nil {
		t.Fatalf("re-open app: %v", err)
	}
	defer func() { _ = gatewayApp2.Close() }()

	session, err := gatewayApp2.GetSession(principal, created.SessionID)
	if err != nil {
		t.Fatalf("get session: %v", err)
	}
	if session.Title != "sqlite session" {
		t.Fatalf("unexpected session title: %s", session.Title)
	}
	events, err := gatewayApp2.ListSessionMessages(principal, created.SessionID, 0, 10)
	if err != nil {
		t.Fatalf("list messages: %v", err)
	}
	if len(events) == 0 {
		t.Fatalf("expected persisted session event")
	}
}

func TestExecuteTaskMarksTimedOut(t *testing.T) {
	t.Setenv("GATEWAY_STORE_BACKEND", "memory")
	repoRoot := filepath.Clean("../../..")
	gatewayApp, _, err := New(repoRoot)
	if err != nil {
		t.Fatalf("new app: %v", err)
	}
	defer func() { _ = gatewayApp.Close() }()

	gatewayApp.taskTimeout = 10 * time.Millisecond
	gatewayApp.Runtime = &stubRuntimeClient{
		submitResp: runtimeclient.SubmittedTask{RuntimeJobID: "runtime_job_timeout"},
		waitFunc: func(ctx context.Context, submitted runtimeclient.SubmittedTask) (runtimeclient.RunResult, error) {
			<-ctx.Done()
			return runtimeclient.RunResult{}, ctx.Err()
		},
	}

	principal := auth.Principal{ID: "demo-user", Role: "session_approver"}
	session, err := gatewayApp.CreateSession(principal, "timeout test", "multi_agent", "")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	task := store.Task{
		TaskID:       "task_timeout",
		SessionID:    session.SessionID,
		Title:        "timeout",
		Instruction:  "wait forever",
		Status:       "running",
		CurrentAgent: "coding",
		UpdatedAt:    time.Now().UTC(),
	}
	if err := gatewayApp.Store.CreateTask(task); err != nil {
		t.Fatalf("create task: %v", err)
	}
	go gatewayApp.executeTask(task)

	deadline := time.Now().Add(500 * time.Millisecond)
	for time.Now().Before(deadline) {
		current, err := gatewayApp.Store.GetTask(task.TaskID)
		if err == nil && current.Status == "timed_out" {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("expected task to become timed_out")
}

func TestCancelTaskCancelsRuntimeJob(t *testing.T) {
	t.Setenv("GATEWAY_STORE_BACKEND", "memory")
	repoRoot := filepath.Clean("../../..")
	gatewayApp, _, err := New(repoRoot)
	if err != nil {
		t.Fatalf("new app: %v", err)
	}
	defer func() { _ = gatewayApp.Close() }()

	stub := &stubRuntimeClient{
		submitResp: runtimeclient.SubmittedTask{RuntimeJobID: "runtime_job_cancel"},
		waitFunc: func(ctx context.Context, submitted runtimeclient.SubmittedTask) (runtimeclient.RunResult, error) {
			<-ctx.Done()
			return runtimeclient.RunResult{}, context.Canceled
		},
	}
	gatewayApp.Runtime = stub

	principal := auth.Principal{ID: "demo-user", Role: "session_approver"}
	session, err := gatewayApp.CreateSession(principal, "cancel test", "multi_agent", "")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	task := store.Task{
		TaskID:       "task_cancel",
		SessionID:    session.SessionID,
		Title:        "cancel",
		Instruction:  "cancel me",
		Status:       "running",
		CurrentAgent: "coding",
		UpdatedAt:    time.Now().UTC(),
	}
	if err := gatewayApp.Store.CreateTask(task); err != nil {
		t.Fatalf("create task: %v", err)
	}
	go gatewayApp.executeTask(task)
	time.Sleep(20 * time.Millisecond)

	if err := gatewayApp.CancelTask(principal, task.TaskID, "manual cancel"); err != nil {
		t.Fatalf("cancel task: %v", err)
	}
	current, err := gatewayApp.Store.GetTask(task.TaskID)
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if current.Status != "cancelled" {
		t.Fatalf("expected cancelled status, got %s", current.Status)
	}
	stub.mu.Lock()
	defer stub.mu.Unlock()
	if len(stub.cancelled) == 0 || stub.cancelled[0] != "runtime_job_cancel" {
		t.Fatalf("expected runtime cancel to be called with runtime_job_cancel, got %#v", stub.cancelled)
	}
}
