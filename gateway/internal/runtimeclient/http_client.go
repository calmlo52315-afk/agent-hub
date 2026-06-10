package runtimeclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// RunResult 对应 Runtime FastAPI 的完整输出，Gateway 只做读取和事件映射。
type RunResult struct {
	OK          bool                 `json:"ok"`
	TaskID      string               `json:"task_id"`
	TraceID     string               `json:"trace_id"`
	Messages    []map[string]any     `json:"messages"`
	Diagnostics []map[string]any     `json:"diagnostics"`
	Result      RuntimeResultPayload `json:"result"`
	Failure     map[string]any       `json:"failure,omitempty"`
}

type RuntimeResultPayload struct {
	Coding         map[string]any   `json:"coding"`
	CodingSubtasks []map[string]any `json:"coding_subtasks"`
	Review         ReviewPayload    `json:"review"`
	Artifact       ArtifactPayload  `json:"artifact"`
	TaskPlan       map[string]any   `json:"task_plan"`
	UsedSkills     []string         `json:"used_skills"`
}

type ReviewPayload struct {
	Agent          string           `json:"agent"`
	Role           string           `json:"role"`
	Pass           bool             `json:"pass"`
	Score          int              `json:"score"`
	Issues         []map[string]any `json:"issues"`
	Summary        map[string]any   `json:"summary"`
	FilesReviewed  int              `json:"files_reviewed"`
	Skipped        bool             `json:"skipped"`
	ApprovalRequired bool           `json:"approval_required"`
	ReviewSkill    string           `json:"review_skill,omitempty"`
}

type ArtifactPayload struct {
	Agent        string         `json:"agent"`
	Role         string         `json:"role"`
	ArtifactDir  string         `json:"artifact_dir"`
	CreatedFiles []string       `json:"created_files"`
	Summary      map[string]any `json:"summary"`
}

type SubmittedTask struct {
	RuntimeJobID string
	PollAfterMS  int
}

var (
	ErrPollTimeout      = errors.New("runtime poll timeout")
	ErrRuntimeCancelled = errors.New("runtime task cancelled")
)

type ProgressEvent struct {
	Kind    string
	Payload map[string]any
}

type WorkspaceSeedFile struct {
	Path    string `json:"path"`
	Content string `json:"content"`
}

type WorkspaceSeedResult struct {
	Seeded  int              `json:"seeded"`
	Skipped int              `json:"skipped"`
	Errors  []map[string]any `json:"errors"`
}

type WorkspaceFilesContentResult struct {
	Contents map[string]*string `json:"contents"`
	Errors   []map[string]any   `json:"errors"`
}

type Client interface {
	SubmitInstruction(ctx context.Context, instruction string, mentionedAgent string, reviewAgent string, sessionID string) (SubmittedTask, error)
	WaitForResult(ctx context.Context, submitted SubmittedTask) (RunResult, error)
	WaitForResultWithProgress(ctx context.Context, submitted SubmittedTask, onProgress func(ProgressEvent)) (RunResult, error)
	CancelTask(ctx context.Context, runtimeJobID string) error
	RunInstruction(ctx context.Context, instruction string, mentionedAgent string, sessionID string) (RunResult, error)
	SeedWorkspace(ctx context.Context, sessionID string, files []WorkspaceSeedFile) (WorkspaceSeedResult, error)
	ReadWorkspaceFilesContent(ctx context.Context, sessionID string, paths []string) (WorkspaceFilesContentResult, error)
	ReadWorkspaceFile(ctx context.Context, sessionID string, filePath string) (map[string]any, error)
	GetWorkspaceFiles(ctx context.Context, sessionID string) ([]map[string]any, error)
}

type RunInstructionRequest struct {
	Instruction    string `json:"instruction"`
	MentionedAgent string `json:"mentioned_agent,omitempty"`
	ReviewAgent    string `json:"review_agent,omitempty"`
	SessionID      string `json:"session_id,omitempty"`
}

type submitTaskResponse struct {
	TaskID      string `json:"task_id"`
	Status      string `json:"status"`
	PollAfterMS int    `json:"poll_after_ms"`
}

type taskStatusResponse struct {
	TaskID      string           `json:"task_id"`
	Status      string           `json:"status"`
	Completed   bool             `json:"completed"`
	PollAfterMS int              `json:"poll_after_ms"`
	Result      *RunResult       `json:"result"`
	Error       map[string]any   `json:"error"`
	Diagnostics []map[string]any `json:"diagnostics,omitempty"`
}

type runtimeErrorEnvelope struct {
	Detail any `json:"detail"`
}

// HTTPClient 通过 FastAPI 内部服务调用 Runtime，Gateway 不再直接 fork Python 进程。
type HTTPClient struct {
	BaseURL      string
	Token        string
	Client       *http.Client
	PollInterval time.Duration
	PollTimeout  time.Duration
}

func NewHTTPClient(baseURL string, token string, timeout time.Duration) *HTTPClient {
	return &HTTPClient{
		BaseURL:      strings.TrimRight(baseURL, "/"),
		Token:        token,
		Client:       &http.Client{Timeout: timeout},
		PollInterval: 500 * time.Millisecond,
		PollTimeout:  3 * time.Minute,
	}
}

func (c *HTTPClient) RunInstruction(ctx context.Context, instruction string, mentionedAgent string, sessionID string) (RunResult, error) {
	submitted, err := c.SubmitInstruction(ctx, instruction, mentionedAgent, "", sessionID)
	if err != nil {
		return RunResult{}, err
	}
	return c.WaitForResult(ctx, submitted)
}

func (c *HTTPClient) SubmitInstruction(ctx context.Context, instruction string, mentionedAgent string, reviewAgent string, sessionID string) (SubmittedTask, error) {
	body, err := json.Marshal(RunInstructionRequest{Instruction: instruction, MentionedAgent: mentionedAgent, ReviewAgent: reviewAgent, SessionID: sessionID})
	if err != nil {
		return SubmittedTask{}, fmt.Errorf("marshal runtime request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/internal/v1/tasks", strings.NewReader(string(body)))
	if err != nil {
		return SubmittedTask{}, fmt.Errorf("build runtime request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return SubmittedTask{}, fmt.Errorf("call runtime api: %w", err)
	}
	defer resp.Body.Close()

	var accepted submitTaskResponse
	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return SubmittedTask{}, fmt.Errorf("runtime api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}
	if err := json.NewDecoder(resp.Body).Decode(&accepted); err != nil {
		return SubmittedTask{}, fmt.Errorf("decode runtime submit response: %w", err)
	}
	return SubmittedTask{RuntimeJobID: accepted.TaskID, PollAfterMS: accepted.PollAfterMS}, nil
}

func (c *HTTPClient) WaitForResult(ctx context.Context, submitted SubmittedTask) (RunResult, error) {
	pollInterval := c.PollInterval
	if submitted.PollAfterMS > 0 {
		pollInterval = time.Duration(submitted.PollAfterMS) * time.Millisecond
	}
	pollCtx, cancel := context.WithTimeout(ctx, c.PollTimeout)
	defer cancel()

	for {
		statusResponse, err := c.pollTask(pollCtx, submitted.RuntimeJobID)
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) {
				return RunResult{}, ErrPollTimeout
			}
			return RunResult{}, err
		}
		if statusResponse.Completed {
			if statusResponse.Error != nil {
				if code, _ := statusResponse.Error["code"].(string); code == "runtime_task_cancelled" {
					return RunResult{}, ErrRuntimeCancelled
				}
				return RunResult{}, fmt.Errorf("runtime async task failed: %v", statusResponse.Error)
			}
			if statusResponse.Result == nil {
				return RunResult{}, fmt.Errorf("runtime async task completed without result")
			}
			return *statusResponse.Result, nil
		}
		wait := pollInterval
		if statusResponse.PollAfterMS > 0 {
			wait = time.Duration(statusResponse.PollAfterMS) * time.Millisecond
		}
		select {
		case <-pollCtx.Done():
			return RunResult{}, ErrPollTimeout
		case <-time.After(wait):
		}
	}
}

// WaitForResultWithProgress polls the runtime until completion, calling onProgress
// for each intermediate diagnostic event not seen before.
func (c *HTTPClient) WaitForResultWithProgress(ctx context.Context, submitted SubmittedTask, onProgress func(ProgressEvent)) (RunResult, error) {
	pollInterval := c.PollInterval
	if submitted.PollAfterMS > 0 {
		pollInterval = time.Duration(submitted.PollAfterMS) * time.Millisecond
	}
	pollCtx, cancel := context.WithTimeout(ctx, c.PollTimeout)
	defer cancel()

	seen := make(map[string]bool)
	for {
		statusResponse, err := c.pollTask(pollCtx, submitted.RuntimeJobID)
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) {
				return RunResult{}, ErrPollTimeout
			}
			return RunResult{}, err
		}

		// 转发新的事件给回调
		for _, diag := range statusResponse.Diagnostics {
			kind, _ := diag["kind"].(string)
			if kind == "" {
				continue
			}
			if seen[kind] {
				continue
			}
			seen[kind] = true
			onProgress(ProgressEvent{Kind: kind, Payload: diag})
		}

		if statusResponse.Completed {
			if statusResponse.Error != nil {
				if code, _ := statusResponse.Error["code"].(string); code == "runtime_task_cancelled" {
					return RunResult{}, ErrRuntimeCancelled
				}
				return RunResult{}, fmt.Errorf("runtime async task failed: %v", statusResponse.Error)
			}
			if statusResponse.Result == nil {
				return RunResult{}, fmt.Errorf("runtime async task completed without result")
			}
			return *statusResponse.Result, nil
		}

		wait := pollInterval
		if statusResponse.PollAfterMS > 0 {
			wait = time.Duration(statusResponse.PollAfterMS) * time.Millisecond
		}
		select {
		case <-pollCtx.Done():
			return RunResult{}, ErrPollTimeout
		case <-time.After(wait):
		}
	}
}

func (c *HTTPClient) SeedWorkspace(ctx context.Context, sessionID string, files []WorkspaceSeedFile) (WorkspaceSeedResult, error) {
	body, err := json.Marshal(map[string]any{"files": files})
	if err != nil {
		return WorkspaceSeedResult{}, fmt.Errorf("marshal seed request: %w", err)
	}

	url := fmt.Sprintf("%s/internal/v1/sessions/%s/workspace/seed", c.BaseURL, sessionID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(string(body)))
	if err != nil {
		return WorkspaceSeedResult{}, fmt.Errorf("build seed request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return WorkspaceSeedResult{}, fmt.Errorf("call runtime seed api: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return WorkspaceSeedResult{}, fmt.Errorf("runtime seed api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}

	var result WorkspaceSeedResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return WorkspaceSeedResult{}, fmt.Errorf("decode seed response: %w", err)
	}
	return result, nil
}

func (c *HTTPClient) ReadWorkspaceFilesContent(ctx context.Context, sessionID string, paths []string) (WorkspaceFilesContentResult, error) {
	body, err := json.Marshal(map[string]any{"paths": paths})
	if err != nil {
		return WorkspaceFilesContentResult{}, fmt.Errorf("marshal files-content request: %w", err)
	}

	url := fmt.Sprintf("%s/internal/v1/sessions/%s/workspace/files-content", c.BaseURL, sessionID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(string(body)))
	if err != nil {
		return WorkspaceFilesContentResult{}, fmt.Errorf("build files-content request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return WorkspaceFilesContentResult{}, fmt.Errorf("call runtime files-content api: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return WorkspaceFilesContentResult{}, fmt.Errorf("runtime files-content api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}

	var result WorkspaceFilesContentResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return WorkspaceFilesContentResult{}, fmt.Errorf("decode files-content response: %w", err)
	}
	return result, nil
}

func (c *HTTPClient) GetWorkspaceFiles(ctx context.Context, sessionID string) ([]map[string]any, error) {
	url := fmt.Sprintf("%s/internal/v1/sessions/%s/workspace/files", c.BaseURL, sessionID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("build workspace files request: %w", err)
	}
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call runtime workspace files api: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return nil, fmt.Errorf("runtime workspace files api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}

	var files []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&files); err != nil {
		return nil, fmt.Errorf("decode workspace files response: %w", err)
	}
	return files, nil
}

func (c *HTTPClient) ReadWorkspaceFile(ctx context.Context, sessionID string, filePath string) (map[string]any, error) {
	url := fmt.Sprintf("%s/internal/v1/sessions/%s/workspace/file?path=%s",
		c.BaseURL, sessionID, filePath)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("build workspace file request: %w", err)
	}
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call runtime workspace file api: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return nil, fmt.Errorf("runtime workspace file api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}

	var result map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode workspace file response: %w", err)
	}
	return result, nil
}

func (c *HTTPClient) CancelTask(ctx context.Context, runtimeJobID string) error {
	if strings.TrimSpace(runtimeJobID) == "" {
		return nil
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, c.BaseURL+"/internal/v1/tasks/"+runtimeJobID, nil)
	if err != nil {
		return fmt.Errorf("build runtime cancel request: %w", err)
	}
	req.Header.Set("X-Runtime-Token", c.Token)
	resp, err := c.Client.Do(req)
	if err != nil {
		return fmt.Errorf("call runtime cancel api: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return fmt.Errorf("runtime cancel api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}
	return nil
}

func (c *HTTPClient) pollTask(ctx context.Context, taskID string) (taskStatusResponse, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/internal/v1/tasks/"+taskID, nil)
	if err != nil {
		return taskStatusResponse{}, fmt.Errorf("build runtime poll request: %w", err)
	}
	req.Header.Set("X-Runtime-Token", c.Token)

	resp, err := c.Client.Do(req)
	if err != nil {
		return taskStatusResponse{}, fmt.Errorf("call runtime poll api: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		var runtimeErr runtimeErrorEnvelope
		_ = json.NewDecoder(resp.Body).Decode(&runtimeErr)
		return taskStatusResponse{}, fmt.Errorf("runtime poll api returned status %d: %v", resp.StatusCode, runtimeErr.Detail)
	}
	var statusResponse taskStatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&statusResponse); err != nil {
		return taskStatusResponse{}, fmt.Errorf("decode runtime poll response: %w", err)
	}
	return statusResponse, nil
}
