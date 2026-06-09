package auth

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"agenthub/gateway/internal/store"
)

var ErrUnauthorized = errors.New("unauthorized")

// Principal 表示 Gateway 已鉴权的外部调用身份。
type Principal struct {
	ID   string `json:"id"`
	Role string `json:"role"`
}

// Service 负责 access token 和 ws ticket 的签发与校验。
type Service struct {
	store store.AuthStore
}

func NewService(authStore store.AuthStore) *Service {
	return &Service{store: authStore}
}

func (s *Service) BootstrapDemoPrincipal(principal Principal) (string, error) {
	token := "demo-access-token"
	record := store.AccessTokenRecord{
		Token:       token,
		PrincipalID: principal.ID,
		Role:        principal.Role,
		ExpiresAt:   time.Now().UTC().Add(365 * 24 * time.Hour),
	}
	return token, s.store.SaveAccessToken(record)
}

func (s *Service) AuthenticateBearer(header string) (Principal, error) {
	if header == "" {
		return Principal{}, ErrUnauthorized
	}
	token := strings.TrimSpace(strings.TrimPrefix(header, "Bearer "))
	if token == "" || token == header && !strings.HasPrefix(header, "Bearer ") {
		return Principal{}, ErrUnauthorized
	}
	record, err := s.store.GetAccessToken(token)
	if err != nil {
		return Principal{}, ErrUnauthorized
	}
	return Principal{ID: record.PrincipalID, Role: record.Role}, nil
}

func (s *Service) IssueWSTicket(principal Principal, sessionID string, ttl time.Duration) (string, time.Time, error) {
	ticket, err := newToken()
	if err != nil {
		return "", time.Time{}, err
	}
	expiresAt := time.Now().UTC().Add(ttl)
	record := store.WSTicketRecord{
		Ticket:      ticket,
		SessionID:   sessionID,
		PrincipalID: principal.ID,
		ExpiresAt:   expiresAt,
	}
	if err := s.store.SaveWSTicket(record); err != nil {
		return "", time.Time{}, err
	}
	return ticket, expiresAt, nil
}

func (s *Service) ConsumeWSTicket(ticket string) (Principal, string, error) {
	record, err := s.store.ConsumeWSTicket(ticket)
	if err != nil {
		return Principal{}, "", ErrUnauthorized
	}
	return Principal{ID: record.PrincipalID, Role: "session_approver"}, record.SessionID, nil
}

func newToken() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return hex.EncodeToString(buf), nil
}
