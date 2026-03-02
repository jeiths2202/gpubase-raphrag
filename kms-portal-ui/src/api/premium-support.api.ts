/**
 * Premium Support API Client
 * LiveKit 기반 원격 전문가 화면 공유 세션 관리
 */
import client from './client';

// axios client already uses baseURL='/api/v1' from constants.ts
const BASE_URL = '/support';

export interface CreateSessionRequest {
  chat_context?: string;
}

export interface CreateSessionResponse {
  room_name: string;
  token: string;
  server_url: string;
  session_id: string;
}

export interface JoinSessionResponse {
  token: string;
  server_url: string;
  room_name: string;
  user_name: string;
  chat_context?: string;
}

export interface SessionInfo {
  session_id: string;
  room_name: string;
  user_id: string;
  user_name: string;
  status: 'waiting' | 'active' | 'ended';
  chat_context?: string;
  created_at: string;
  expert_id?: string;
  expert_name?: string;
}

export interface ExpertStatusResponse {
  status: 'available' | 'busy' | 'offline';
  available_experts: number;
  active_sessions: number;
  estimated_wait?: number;
}

export interface LiveKitHealthResponse {
  available: boolean;
  server_url: string;
  rooms_count: number;
}

export const premiumSupportApi = {
  createSession: (data: CreateSessionRequest) =>
    client.post<CreateSessionResponse>(`${BASE_URL}/create-session`, data),

  getExpertStatus: () =>
    client.get<ExpertStatusResponse>(`${BASE_URL}/expert-status`),

  getSessions: () =>
    client.get<SessionInfo[]>(`${BASE_URL}/sessions`),

  joinSession: (roomName: string) =>
    client.post<JoinSessionResponse>(`${BASE_URL}/join-session/${roomName}`),

  endSession: (data: { room_name: string; reason?: string }) =>
    client.post(`${BASE_URL}/end-session`, data),

  health: () =>
    client.get<LiveKitHealthResponse>(`${BASE_URL}/health`),
};
